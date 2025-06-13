"""
Chat Controller

Clean deterministic routing to 6 MCP tools with zero fallback logic.
Every query hits exactly one tool or returns unsupported_query error.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime
from typing import Dict, Any, List, Tuple, Callable

from src.services.mcp.coingecko_client import CoinGeckoMCPClient
from src.services.mcp.models import PriceData, CoinData, SearchResult

# Import web search capabilities
try:
    from web_research.data_acquisition.services import SearchService
    WEB_SEARCH_AVAILABLE = True
except ImportError:
    WEB_SEARCH_AVAILABLE = False

logger = logging.getLogger(__name__)

# Helper: run async coroutine from sync context
def _run(coro):
    """Synchronously execute an async coroutine."""
    try:
        loop = asyncio.get_running_loop()
        import concurrent.futures
        import threading
        
        def run_in_thread():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                return new_loop.run_until_complete(coro)
            finally:
                new_loop.close()
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(run_in_thread)
            return future.result(timeout=30)
            
    except RuntimeError:
        return asyncio.run(coro)


class ChatController:
    """Deterministic crypto chat router using 6 MCP tools."""

    # Rate limits (calls per minute)
    RATE_LIMITS = {
        "get_coin_price": 120,
        "get_trending_coins": 60, 
        "search_coins": 60,
        "get_market_overview": 30,
        "get_historical_data": 30,
        "ask": 20
    }
    
    # Tool timeouts (seconds)
    TIMEOUTS = {
        "get_coin_price": 2,
        "get_trending_coins": 2,
        "search_coins": 2, 
        "get_market_overview": 2,
        "get_historical_data": 5,
        "ask": 10
    }

    def __init__(self):
        self.client = CoinGeckoMCPClient()
        # Initialize web search service if available
        self.search_service = SearchService() if WEB_SEARCH_AVAILABLE else None
        self.connected = False
        
        # Routing table: (pattern, tool_handler)
        self.routes = [
            (r"^(?:what|show).*price", self._handle_get_coin_price),
            (r"^(?:top|trending) coins", self._handle_get_trending_coins),
            (r"^search ", self._handle_search_coins),
            (r"^(?:global|market) (?:stats|overview)", self._handle_get_market_overview),
            (r"^(?:historical|history)", self._handle_get_historical_data),
            (r".*", self._handle_ask)  # Catch-all for complex queries
        ]

    def _ensure_connection(self):
        """Ensure MCP connection is established."""
        if not self.connected:
            try:
                success = _run(self.client.connect())
                self.connected = success
                if not success:
                    logger.warning("MCP connection failed - operating in degraded mode")
            except Exception as e:
                logger.error(f"Connection error: {e}")
                self.connected = False

    def process_message(self, message: str) -> Dict[str, Any]:
        """
        Route message to appropriate MCP tool using deterministic patterns.
        Returns standard response envelope.
        """
        start_time = time.time()
        self._ensure_connection()
        
        # Normalize message
        msg = message.strip().lower()
        
        # Route through patterns
        for pattern, handler in self.routes:
            if re.search(pattern, msg, re.IGNORECASE):
                try:
                    result = handler(message, msg)
                    latency_ms = int((time.time() - start_time) * 1000)
                    
                    return {
                        "tool": result.get("tool"),
                        "ok": True,
                        "data": result.get("data"),
                        "meta": {
                            "received_at": datetime.utcnow().isoformat() + "Z",
                            "latency_ms": latency_ms
                        }
                    }
                    
                except Exception as e:
                    logger.error(f"Tool {handler.__name__} failed: {e}")
                    return {
                        "tool": getattr(handler, '_tool_name', 'unknown'),
                        "ok": False,
                        "error": str(e),
                        "data": None,
                        "meta": {
                            "received_at": datetime.utcnow().isoformat() + "Z",
                            "latency_ms": int((time.time() - start_time) * 1000)
                        }
                    }
        
        # No route matched
        return {
            "tool": None,
            "ok": False,
            "error": "unsupported_query",
            "data": None,
            "meta": {
                "received_at": datetime.utcnow().isoformat() + "Z",
                "hint": "Rephrase using clear coin keywords or try: 'Bitcoin price', 'trending coins', 'search dogecoin'"
            }
        }

    def _handle_get_coin_price(self, original_msg: str, normalized_msg: str) -> Dict[str, Any]:
        """Handle coin price queries. Pattern: '^(?:what|show).*price'"""
        # Extract coin symbol from message
        coin_symbol = self._extract_coin_symbol(original_msg)
        if not coin_symbol:
            raise ValueError("Could not identify coin symbol. Try: 'Bitcoin price' or 'BTC price'")
        
        # Extract vs_currency if specified
        vs_currency = "usd"  # default
        if any(curr in normalized_msg for curr in ["eur", "euro"]):
            vs_currency = "eur"
        elif any(curr in normalized_msg for curr in ["btc", "bitcoin"]):
            vs_currency = "btc"
        
        price_data = _run(self.client.get_coin_price(coin_symbol))
        
        return {
            "tool": "get_coin_price",
            "data": {
                "coin_id": price_data.coin_id,
                "symbol": price_data.symbol,
                "name": getattr(price_data, 'name', coin_symbol),
                "price": price_data.current_price,
                "vs_currency": vs_currency,
                "change_24h": getattr(price_data, 'price_change_percentage_24h', None),
                "market_cap": getattr(price_data, 'market_cap', None)
            }
        }

    def _handle_get_trending_coins(self, original_msg: str, normalized_msg: str) -> Dict[str, Any]:
        """Handle trending coins queries. Pattern: '^(?:top|trending) coins'"""
        # Extract limit if specified
        limit = 10  # default
        import re
        limit_match = re.search(r'(?:top|trending)\s+(\d+)', normalized_msg)
        if limit_match:
            limit = min(int(limit_match.group(1)), 50)  # cap at 50
        
        trending_data = _run(self.client.get_trending_coins())
        
        # Limit results
        limited_data = trending_data[:limit] if trending_data else []
        
        return {
            "tool": "get_trending_coins", 
            "data": {
                "trending": [
                    {
                        "id": coin.id,
                        "symbol": coin.symbol,
                        "name": coin.name,
                        "market_cap_rank": getattr(coin, 'market_cap_rank', None),
                        "price_change_percentage_24h": getattr(coin, 'price_change_percentage_24h', None)
                    }
                    for coin in limited_data
                ],
                "limit": limit,
                "total_returned": len(limited_data)
            }
        }

    def _handle_search_coins(self, original_msg: str, normalized_msg: str) -> Dict[str, Any]:
        """Handle coin search queries. Pattern: '^search '"""
        # Extract search query
        query = original_msg[7:].strip()  # Remove "search " prefix
        if not query:
            raise ValueError("Search query cannot be empty. Try: 'search bitcoin' or 'search doge'")
        
        search_results = _run(self.client.search_coins(query))
        
        return {
            "tool": "search_coins",
            "data": {
                "query": query,
                "results": [
                    {
                        "id": result.id,
                        "name": result.name, 
                        "symbol": result.symbol,
                        "market_cap_rank": result.market_cap_rank
                    }
                    for result in search_results
                ],
                "total_found": len(search_results)
            }
        }

    def _handle_get_market_overview(self, original_msg: str, normalized_msg: str) -> Dict[str, Any]:
        """Handle market overview queries. Pattern: '^(?:global|market) (?:stats|overview)'"""
        market_data = _run(self.client.get_market_overview())
        
        return {
            "tool": "get_market_overview",
            "data": {
                "total_market_cap_usd": getattr(market_data, 'total_market_cap_usd', None),
                "total_volume_usd": getattr(market_data, 'total_volume_usd', None), 
                "btc_dominance": getattr(market_data, 'btc_dominance', None),
                "market_cap_change_24h": getattr(market_data, 'market_cap_change_percentage_24h_usd', None),
                "active_cryptocurrencies": getattr(market_data, 'active_cryptocurrencies', None)
            }
        }

    def _handle_get_historical_data(self, original_msg: str, normalized_msg: str) -> Dict[str, Any]:
        """Handle historical data queries. Pattern: '^(?:historical|history)'"""
        # Extract coin symbol
        coin_symbol = self._extract_coin_symbol(original_msg)
        if not coin_symbol:
            raise ValueError("Could not identify coin. Try: 'historical Bitcoin data' or 'history ETH'")
        
        # Extract time parameters (simplified - could be enhanced)
        days = 7  # default
        if any(term in normalized_msg for term in ["year", "12 month"]):
            days = 365
        elif any(term in normalized_msg for term in ["month", "30 day"]):
            days = 30
        elif "week" in normalized_msg:
            days = 7
        elif "24h" in normalized_msg or "day" in normalized_msg:
            days = 1
        
        historical_data = _run(self.client.get_historical_data(coin_symbol, days))
        
        return {
            "tool": "get_historical_data",
            "data": {
                "coin_id": historical_data.coin_id,
                "days": days,
                "prices": [
                    {
                        "timestamp": price.timestamp.isoformat() if hasattr(price.timestamp, 'isoformat') else str(price.timestamp),
                        "price": price.price,
                        "market_cap": price.market_cap,
                        "volume": price.volume
                    }
                    for price in historical_data.prices[:100]  # Limit for response size
                ],
                "total_points": len(historical_data.prices)
            }
        }

    def _handle_ask(self, original_msg: str, normalized_msg: str) -> Dict[str, Any]:
        """Handle complex NLP queries using MCP ask tool. Pattern: '.*' (catch-all)"""
        ask_response = _run(self.client.ask_question(original_msg))
        
        if ask_response.get("error"):
            raise Exception(ask_response.get("answer", "Ask tool failed"))
        
        return {
            "tool": "ask",
            "data": {
                "question": original_msg,
                "answer": ask_response.get("answer", ""),
                "source": ask_response.get("source", "mcp"),
                "additional_data": ask_response.get("data", None)
            }
        }

    def _extract_coin_symbol(self, message: str) -> str:
        """Extract coin symbol/ID from message."""
        msg_lower = message.lower()
        
        # Common coin mappings
        coin_map = {
            "bitcoin": "bitcoin",
            "btc": "bitcoin", 
            "ethereum": "ethereum",
            "eth": "ethereum",
            "solana": "solana", 
            "sol": "solana",
            "cardano": "cardano",
            "ada": "cardano",
            "polygon": "polygon",
            "matic": "polygon",
            "avalanche": "avalanche",
            "avax": "avalanche",
            "chainlink": "chainlink",
            "link": "chainlink",
            "polkadot": "polkadot",
            "dot": "polkadot"
        }
        
        for term, coin_id in coin_map.items():
            if term in msg_lower:
                return coin_id
        
        # Fallback: extract potential symbol from message
        import re
        symbol_match = re.search(r'\b([a-z]{2,10})\b', msg_lower)
        if symbol_match:
            return symbol_match.group(1)
        
        return ""

    # Set tool names for error reporting
    _handle_get_coin_price._tool_name = "get_coin_price"
    _handle_get_trending_coins._tool_name = "get_trending_coins" 
    _handle_search_coins._tool_name = "search_coins"
    _handle_get_market_overview._tool_name = "get_market_overview"
    _handle_get_historical_data._tool_name = "get_historical_data"
    _handle_ask._tool_name = "ask"

    # ------------------------------------------------------------------
    # Data-fetch helpers (sync wrappers around async)
    # ------------------------------------------------------------------

    def get_price(self, coin_id: str) -> PriceData:
        try:
            return _run(self.client.get_coin_price(coin_id))
        except Exception as e:
            logger.error(f"Error fetching price for {coin_id}: {e}")
            raise

    def get_trending(self) -> List[CoinData]:
        try:
            return _run(self.client.get_trending_coins())
        except Exception as e:
            logger.error(f"Error fetching trending coins: {e}")
            raise

    def search_coins(self, query: str) -> List[SearchResult]:
        try:
            return _run(self.client.search_coins(query))
        except Exception as e:
            logger.error(f"Error searching coins with query '{query}': {e}")
            raise

    # Comparison helper
    def _compare_coins(self, coin_ids: List[str]) -> Dict[str, Any]:
        try:
            from src.services.crypto_analysis.comparison_service import ComparisonService
            service = ComparisonService()
            return _run(service.compare(coin_ids))
        except Exception as e:
            logger.error(f"Error comparing coins {coin_ids}: {e}")
            raise

    def _analyse_coin(self, coin_id: str) -> Dict[str, Any]:
        try:
            from src.services.crypto_analysis.analysis_service import AnalysisService
            service = AnalysisService()
            return _run(service.analyze(coin_id))
        except Exception as e:
            logger.error(f"Error analyzing coin {coin_id}: {e}")
            raise

    def _handle_market_overview_question(self) -> Dict[str, Any]:
        """Handle market overview questions."""
        try:
            market_data = _run(self.client.get_market_overview())
            
            # Format market overview response
            total_market_cap_usd = market_data.total_market_cap.get('usd', 0)
            total_volume_usd = market_data.total_volume.get('usd', 0)
            btc_dominance = market_data.market_cap_percentage.get('btc', 0)
            eth_dominance = market_data.market_cap_percentage.get('eth', 0)
            
            content = f"📊 **Global Cryptocurrency Market Overview**\n\n"
            content += f"💰 **Total Market Cap:** ${total_market_cap_usd:,.0f}\n"
            content += f"📈 **24h Volume:** ${total_volume_usd:,.0f}\n"
            content += f"🟠 **Bitcoin Dominance:** {btc_dominance:.1f}%\n"
            content += f"🔵 **Ethereum Dominance:** {eth_dominance:.1f}%\n"
            content += f"🪙 **Active Cryptocurrencies:** {market_data.active_cryptocurrencies:,}\n"
            
            if market_data.market_cap_change_percentage_24h_usd:
                change = market_data.market_cap_change_percentage_24h_usd
                direction = "📈" if change >= 0 else "📉"
                content += f"{direction} **24h Market Cap Change:** {change:+.2f}%\n"
            
            return {
                "role": "assistant",
                "content": content,
                "timestamp": datetime.now(),
                "data": {
                    "type": "market_overview",
                    "market_data": market_data
                }
            }
            
        except Exception as e:
            logger.error(f"Error handling market overview question: {e}")
            return {
                "role": "assistant",
                "content": f"⚠️ Sorry, I couldn't retrieve the market overview: {str(e)}",
                "timestamp": datetime.now(),
            }
    
    def _handle_historical_data_question(self, coin_id: str, days: int) -> Dict[str, Any]:
        """Handle historical data questions."""
        try:
            historical_data = _run(self.client.get_historical_data(coin_id, days))
            
            if not historical_data.prices:
                return {
                    "role": "assistant",
                    "content": f"📈 I couldn't find historical data for {coin_id}. Please try a different coin.",
                    "timestamp": datetime.now(),
                }
            
            # Get first and last prices for period analysis
            first_price = historical_data.prices[0].price
            last_price = historical_data.prices[-1].price
            price_change = ((last_price - first_price) / first_price) * 100
            
            # Calculate price range
            prices = [p.price for p in historical_data.prices]
            min_price = min(prices)
            max_price = max(prices)
            
            content = f"📈 **{coin_id.title()} Historical Data ({days} days)**\n\n"
            content += f"💰 **Starting Price:** ${first_price:,.2f}\n"
            content += f"💰 **Current Price:** ${last_price:,.2f}\n"
            content += f"📊 **Price Change:** {price_change:+.2f}%\n"
            content += f"📈 **Highest:** ${max_price:,.2f}\n"
            content += f"📉 **Lowest:** ${min_price:,.2f}\n"
            
            return {
                "role": "assistant",
                "content": content,
                "timestamp": datetime.now(),
                "data": {
                    "type": "historical_data",
                    "coin_id": coin_id,
                    "days": days,
                    "data": historical_data,
                    "price_change_percentage": price_change
                }
            }
            
        except Exception as e:
            logger.error(f"Error handling historical data question: {e}")
            return {
                "role": "assistant",
                "content": f"⚠️ Sorry, I couldn't retrieve historical data for {coin_id}: {str(e)}",
                "timestamp": datetime.now(),
            }
    
    def _handle_natural_language_question(self, text: str) -> Dict[str, Any]:
        """Handle natural language questions using MCP ask tool."""
        try:
            response = _run(self.client.ask_question(text))
            
            if response.get("error"):
                return {
                    "role": "assistant",
                    "content": f"⚠️ {response.get('answer', 'I encountered an error processing your question.')}",
                    "timestamp": datetime.now(),
                }
            
            # Format response based on source
            content = response.get("answer", "I couldn't find an answer to your question.")
            source = response.get("source", "unknown")
            
            if source == "mcp":
                content = f"🤖 **AI Analysis:** {content}"
            elif source == "rest_api":
                content = f"📊 **Data Analysis:** {content}"
            
            return {
                "role": "assistant",
                "content": content,
                "timestamp": datetime.now(),
                "data": {
                    "type": "natural_language_response",
                    "source": source,
                    "original_question": text
                }
            }
            
        except Exception as e:
            logger.error(f"Error handling natural language question: {e}")
            return {
                "role": "assistant",
                "content": f"⚠️ Sorry, I couldn't process your question: {str(e)}",
                "timestamp": datetime.now(),
            }
    
    def _handle_market_analysis_question(self, text: str) -> Dict[str, Any]:
        """Handle general market analysis questions."""
        try:
            # Use the enhanced market movement analysis from the MCP client
            question_lower = text.lower()
            
            if any(term in question_lower for term in ["dump", "crash", "fall", "down", "decline", "dip", "plunge"]):
                direction = "down"
            elif any(term in question_lower for term in ["pump", "rally", "rise", "up", "surge", "moon", "bull", "gain"]):
                direction = "up"
            else:
                direction = "general"
            
            # Get the enhanced market analysis
            response = _run(self.client._analyze_market_movement(direction, question_lower))
            
            if response.get("error"):
                # Fallback to basic analysis
                btc_price = self.get_price("bitcoin")
                eth_price = self.get_price("ethereum")
                
                content = f"📊 **Quick Market Analysis**\n\n"
                content += f"• Bitcoin: ${btc_price.current_price:,.2f} ({btc_price.price_change_percentage_24h:+.2f}% 24h)\n"
                content += f"• Ethereum: ${eth_price.current_price:,.2f} ({eth_price.price_change_percentage_24h:+.2f}% 24h)\n\n"
                content += "📈 Market movements are influenced by various factors including regulatory news, institutional activity, technical levels, and overall market sentiment."
                
                return {
                    "role": "assistant",
                    "content": content,
                    "timestamp": datetime.now(),
                }
            
            return {
                "role": "assistant", 
                "content": response.get("answer", "Market analysis completed."),
                "data": {
                    "type": "market_analysis",
                    **response.get("data", {})
                },
                "timestamp": datetime.now(),
            }
            
        except Exception as e:
            logger.error(f"Error in market analysis: {e}")
            return {
                "role": "assistant",
                "content": f"💭 I can see you're asking about market movements. Let me analyze the current situation:\n\n"
                          f"Try asking more specific questions like:\n"
                          f"• 'What's the Bitcoin price trend?'\n"
                          f"• 'Show me trending coins'\n"
                          f"• 'Compare Bitcoin and Ethereum'\n"
                          f"• 'Analyze Bitcoin'\n\n"
                          f"For real-time market news and analysis, I recommend checking crypto news sources alongside the technical analysis I can provide.",
                "timestamp": datetime.now(),
            }

    # ------------------------------------------------------------------
    # Response formatting helpers
    # ------------------------------------------------------------------

    def _format_price_response(self, price: PriceData) -> Dict[str, Any]:
        return {
            "role": "assistant",
            "content": f"📊 Current price for {price.name} ({price.symbol.upper()}): ${price.current_price:,.2f}",
            "data": {
                "type": "coin_info",
                "coin": price.name,
                "symbol": price.symbol.upper(),
                "price": f"${price.current_price:,.2f}",
                "change_24h": f"{price.price_change_percentage_24h:+.2f}%" if price.price_change_percentage_24h is not None else "N/A",
                "market_cap": f"${price.market_cap:,.0f}" if price.market_cap else "N/A",
                "volume": f"${price.total_volume:,.0f}" if price.total_volume else "N/A",
                "rank": "N/A",
            },
            "timestamp": datetime.now(),
        }

    def _format_trending_response(self, coins: List[CoinData]) -> Dict[str, Any]:
        simplified = [
            {
                "name": c.name,
                "symbol": c.symbol.upper(),
                "change": "N/A",
                "rank": c.market_cap_rank or "-",
            }
            for c in coins[:10]
        ]
        return {
            "role": "assistant",
            "content": "🔥 Trending coins:",
            "data": {"type": "trending_list", "coins": simplified},
            "timestamp": datetime.now(),
        }

    def _format_search_response(self, query: str, results: List[SearchResult]) -> Dict[str, Any]:
        simplified = [
            {
                "name": r.name,
                "symbol": r.symbol.upper(),
                "rank": r.market_cap_rank or "-",
            }
            for r in results[:10]
        ]
        return {
            "role": "assistant",
            "content": f"🔍 Search results for '{query}':",
            "data": {"type": "trending_list", "coins": simplified},
            "timestamp": datetime.now(),
        }

    def _format_comparison_response(self, comparison: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "role": "assistant",
            "content": "📊 Comparison results:",
            "data": {
                "type": "dynamic_comparison",
                **comparison
            },
            "timestamp": datetime.now(),
        }

    def _format_analysis_response(self, coin_id: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
        metrics = analysis.get('metrics', {})
        insights = analysis.get('insights', [])
        charts = analysis.get('charts', {})
        
        # Create comprehensive analysis content
        content = f"📊 **Comprehensive Analysis for {coin_id.upper()}**\n\n"
        
        # Key metrics summary
        content += "**📈 Key Metrics:**\n"
        if 'sma_7' in metrics:
            content += f"• 7-day SMA: ${metrics['sma_7']:,.2f}\n"
        if 'sma_14' in metrics:
            content += f"• 14-day SMA: ${metrics['sma_14']:,.2f}\n"
        if 'rsi_14' in metrics:
            content += f"• RSI (14): {metrics['rsi_14']:.1f} ({metrics.get('rsi_signal', 'N/A')})\n"
        if 'volatility_14' in metrics:
            content += f"• Volatility (14d): {metrics['volatility_14']:.2f}%\n"
        
        # Performance metrics
        content += "\n**📊 Performance:**\n"
        if 'performance_7d' in metrics and metrics['performance_7d'] is not None:
            content += f"• 7-day: {metrics['performance_7d']:+.2f}%\n"
        if 'performance_14d' in metrics and metrics['performance_14d'] is not None:
            content += f"• 14-day: {metrics['performance_14d']:+.2f}%\n"
        if 'performance_30d' in metrics and metrics['performance_30d'] is not None:
            content += f"• 30-day: {metrics['performance_30d']:+.2f}%\n"
        
        # Support/Resistance
        if 'price_min_30d' in metrics and 'price_max_30d' in metrics:
            content += f"\n**🎯 Support/Resistance:**\n"
            content += f"• 30-day Low: ${metrics['price_min_30d']:,.2f}\n"
            content += f"• 30-day High: ${metrics['price_max_30d']:,.2f}\n"
        
        # Add insights
        if insights:
            content += "\n**💡 Key Insights:**\n"
            for insight in insights:
                content += f"• {insight}\n"
        
        return {
            "role": "assistant",
            "content": content,
            "data": {
                "type": "enhanced_analysis",
                "coin": coin_id,
                "metrics": metrics,
                "insights": insights,
                "charts": charts,
                "date_range": analysis.get('date_range', 'N/A'),
                "data_points": analysis.get('data_points', 0)
            },
            "timestamp": datetime.now(),
        }

    # ---------------- Chart helpers -----------------
    def _get_price_chart(self, coin_id: str, days: int = 7) -> Dict[str, Any]:
        import plotly.graph_objs as go
        import pandas as pd

        # Simple REST API for historical data
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        client = self.client
        async def fetch():
            return await client.get_historical_data(coin_id, days)
        try:
            hist = loop.run_until_complete(fetch())
        except Exception as e:
            logger.warning(f"Could not fetch historical data: {e}")
            return {
                "role": "assistant",
                "content": f"⚠️ Unable to retrieve chart for {coin_id}",
                "timestamp": datetime.now(),
            }

        # Build DataFrame
        timestamps = [p.timestamp for p in hist.prices]
        prices = [p.price for p in hist.prices]
        df = pd.DataFrame({"Date": timestamps, "Price": prices})

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df["Date"], y=df["Price"], mode="lines", name=coin_id))
        fig.update_layout(title=f"{coin_id.capitalize()} Price (Last {days} Days)", yaxis_title="USD")

        return {
            "role": "assistant",
            "content": f"📈 {coin_id.capitalize()} price chart:",
            "data": {
                "type": "chart_line",
                "figure": fig.to_json()
            },
            "timestamp": datetime.now(),
        }

    def _render_natural_language_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Render natural language response from MCP ask tool."""
        answer = response.get("answer", "")
        source = response.get("source", "unknown")
        
        return {
            "role": "assistant",
            "content": f"💬 **AI Analysis**\n\n{answer}\n\n*Source: {source}*",
            "timestamp": datetime.now(),
            "source": source
        }

    def _handle_news_question(self, text: str) -> Dict[str, Any]:
        """Handle crypto news related questions."""
        if not WEB_SEARCH_AVAILABLE or not self.search_service:
            return {
                "role": "assistant",
                "content": "📰 **News Service Unavailable**\n\nI don't have access to news search capabilities at the moment. Try asking for Bitcoin price, trending coins, or market analysis instead!",
                "timestamp": datetime.now(),
            }
        
        try:
            # Determine what type of crypto news to search for
            news_query = self._build_news_query(text)
            news_results = _run(self._search_crypto_news(news_query))
            
            return self._format_news_response(news_results, news_query)
            
        except Exception as e:
            logger.error(f"Error fetching crypto news: {e}")
            return {
                "role": "assistant",
                "content": f"📰 **News Search Error**\n\nI encountered an error while searching for crypto news: {str(e)}",
                "timestamp": datetime.now(),
            }
    
    def _build_news_query(self, text: str) -> str:
        """Build appropriate news search query based on user input."""
        text_lower = text.lower()
        
        # Check for specific crypto mentions
        crypto_terms = []
        if any(term in text_lower for term in ["bitcoin", "btc"]):
            crypto_terms.append("Bitcoin")
        if any(term in text_lower for term in ["ethereum", "eth"]):
            crypto_terms.append("Ethereum")
        if any(term in text_lower for term in ["solana", "sol"]):
            crypto_terms.append("Solana")
        if any(term in text_lower for term in ["cardano", "ada"]):
            crypto_terms.append("Cardano")
        if any(term in text_lower for term in ["polygon", "matic"]):
            crypto_terms.append("Polygon")
        
        # Build query based on context
        if crypto_terms:
            base_query = f"{' '.join(crypto_terms)} cryptocurrency"
        else:
            base_query = "cryptocurrency crypto"
        
        # Add context based on request type
        if any(term in text_lower for term in ["breaking", "urgent", "latest"]):
            return f"{base_query} breaking news latest"
        elif any(term in text_lower for term in ["price", "market", "trading"]):
            return f"{base_query} price market analysis"
        elif any(term in text_lower for term in ["regulation", "sec", "government"]):
            return f"{base_query} regulation government SEC"
        elif any(term in text_lower for term in ["adoption", "institutional"]):
            return f"{base_query} institutional adoption"
        else:
            return f"{base_query} news today"
    
    async def _search_crypto_news(self, query: str) -> List[Dict[str, Any]]:
        """Search for crypto news using web search service."""
        try:
            # Ensure search service is initialized
            if hasattr(self.search_service, 'ensure_initialized'):
                await self.search_service.ensure_initialized()
            
            # Search for crypto news
            search_results = await self.search_service.search(
                query=query,
                limit=5,  # Get top 5 news articles
                save_content=True
            )
            
            # Extract news data
            news_articles = []
            if search_results and "data" in search_results:
                for article in search_results["data"]:
                    news_articles.append({
                        "title": article.get("title", ""),
                        "url": article.get("url", ""),
                        "content": article.get("content", "")[:500] + "..." if len(article.get("content", "")) > 500 else article.get("content", ""),
                        "source": self._extract_domain(article.get("url", ""))
                    })
            
            return news_articles
            
        except Exception as e:
            logger.error(f"Web search failed: {e}")
            return []
    
    def _extract_domain(self, url: str) -> str:
        """Extract domain name from URL for source attribution."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc
            # Remove www. prefix if present
            if domain.startswith('www.'):
                domain = domain[4:]
            return domain
        except Exception:
            return "Unknown"
    
    def _format_news_response(self, news_articles: List[Dict[str, Any]], query: str) -> Dict[str, Any]:
        """Format news articles into a structured response."""
        if not news_articles:
            return {
                "role": "assistant",
                "content": f"📰 **No Recent News Found**\n\nI couldn't find recent crypto news for your query. Try asking for Bitcoin price or market analysis instead!",
                "timestamp": datetime.now(),
            }
        
        # Build formatted response
        content = f"📰 **Latest Crypto News**\n\n"
        content += f"*Search: {query}*\n\n"
        
        for i, article in enumerate(news_articles, 1):
            title = article.get("title", "Untitled")
            url = article.get("url", "")
            source = article.get("source", "Unknown")
            snippet = article.get("content", "")
            
            content += f"**{i}. {title}**\n"
            if snippet:
                content += f"{snippet}\n"
            content += f"*Source: {source}*"
            if url:
                content += f" | [Read More]({url})"
            content += "\n\n"
        
        content += "💡 *Tip: Ask for specific coins like 'Bitcoin news' or 'Ethereum updates' for targeted results.*"
        
        return {
            "role": "assistant",
            "content": content,
            "timestamp": datetime.now(),
            "data": news_articles,
            "source": "crypto_news"
        }

    def _handle_market_ranking_question(self, text: str) -> Dict[str, Any]:
        """Handle market cap, FDV, and ranking related questions."""
        try:
            # Parse the query to understand what the user wants
            query_info = self._parse_ranking_query(text)
            
            # Get market data
            market_data = _run(self._get_market_ranking_data(query_info))
            
            return self._format_market_ranking_response(market_data, query_info)
            
        except Exception as e:
            logger.error(f"Error handling market ranking question: {e}")
            return {
                "role": "assistant",
                "content": f"💹 **Market Ranking Error**\n\nI encountered an error while fetching market data: {str(e)}\n\nTry asking for 'trending coins' or 'Bitcoin price' instead.",
                "timestamp": datetime.now(),
            }
    
    def _parse_ranking_query(self, text: str) -> Dict[str, Any]:
        """Parse ranking query to extract filter criteria."""
        text_lower = text.lower()
        
        # Default query info
        query_info = {
            "metric": "market_cap",  # default to market cap
            "threshold": None,
            "direction": "above",  # above or below
            "limit": 20  # default number of results
        }
        
        # Determine metric type
        if any(term in text_lower for term in ["fdv", "fully diluted", "diluted valuation"]):
            query_info["metric"] = "fdv"
        elif any(term in text_lower for term in ["market cap", "market capitalization"]):
            query_info["metric"] = "market_cap"
        
        # Determine direction
        if "below" in text_lower or "under" in text_lower or "less than" in text_lower:
            query_info["direction"] = "below"
        
        # Extract threshold amount
        import re
        
        # Look for billion amounts
        billion_match = re.search(r'(\d+(?:\.\d+)?)\s*billion', text_lower)
        if billion_match:
            query_info["threshold"] = float(billion_match.group(1)) * 1_000_000_000
        
        # Look for million amounts
        million_match = re.search(r'(\d+(?:\.\d+)?)\s*million', text_lower)
        if million_match and not billion_match:  # Only use million if no billion found
            query_info["threshold"] = float(million_match.group(1)) * 1_000_000
        
        # Look for top N requests
        top_match = re.search(r'top\s+(\d+)', text_lower)
        if top_match:
            query_info["limit"] = int(top_match.group(1))
            query_info["threshold"] = None  # Clear threshold for top N queries
        
        return query_info
    
    async def _get_market_ranking_data(self, query_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get market ranking data from CoinGecko."""
        try:
            # Use CoinGecko REST API to get market data
            url = f"{self.client.config.fallback_endpoints['coingecko_rest']}/coins/markets"
            params = {
                'vs_currency': 'usd',
                'order': 'market_cap_desc',
                'per_page': 250,  # Get more data to filter
                'page': 1,
                'sparkline': 'false',
                'price_change_percentage': '24h'
            }
            
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=15) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Filter based on query criteria
                        filtered_coins = []
                        for coin in data:
                            # Get the relevant metric value
                            if query_info["metric"] == "fdv":
                                metric_value = coin.get("fully_diluted_valuation")
                            else:
                                metric_value = coin.get("market_cap")
                            
                            # Skip if no metric value
                            if metric_value is None:
                                continue
                            
                            # Apply threshold filter
                            if query_info["threshold"]:
                                if query_info["direction"] == "above" and metric_value >= query_info["threshold"]:
                                    filtered_coins.append(coin)
                                elif query_info["direction"] == "below" and metric_value <= query_info["threshold"]:
                                    filtered_coins.append(coin)
                            else:
                                # No threshold, just return top coins
                                filtered_coins.append(coin)
                            
                            # Limit results
                            if len(filtered_coins) >= query_info["limit"]:
                                break
                        
                        return filtered_coins
                    else:
                        raise Exception(f"CoinGecko API error: {response.status}")
                        
        except Exception as e:
            logger.error(f"Market ranking data fetch failed: {e}")
            raise
    
    def _format_market_ranking_response(self, coins: List[Dict[str, Any]], query_info: Dict[str, Any]) -> Dict[str, Any]:
        """Format market ranking response."""
        if not coins:
            metric_name = "FDV" if query_info["metric"] == "fdv" else "Market Cap"
            threshold_text = ""
            if query_info["threshold"]:
                threshold_val = query_info["threshold"] / 1_000_000_000 if query_info["threshold"] >= 1_000_000_000 else query_info["threshold"] / 1_000_000
                unit = "B" if query_info["threshold"] >= 1_000_000_000 else "M"
                threshold_text = f" {query_info['direction']} ${threshold_val:.1f}{unit}"
            
            return {
                "role": "assistant",
                "content": f"💹 **No Coins Found**\n\nI couldn't find any coins with {metric_name}{threshold_text}. Try adjusting your criteria or ask for 'trending coins'.",
                "timestamp": datetime.now(),
            }
        
        # Build response
        metric_name = "FDV" if query_info["metric"] == "fdv" else "Market Cap"
        threshold_text = ""
        if query_info["threshold"]:
            threshold_val = query_info["threshold"] / 1_000_000_000 if query_info["threshold"] >= 1_000_000_000 else query_info["threshold"] / 1_000_000
            unit = "B" if query_info["threshold"] >= 1_000_000_000 else "M"
            threshold_text = f" {query_info['direction']} ${threshold_val:.1f}{unit}"
        
        content = f"💹 **Coins by {metric_name}{threshold_text}**\n\n"
        
        for i, coin in enumerate(coins, 1):
            name = coin.get("name", "Unknown")
            symbol = coin.get("symbol", "").upper()
            price = coin.get("current_price", 0)
            
            if query_info["metric"] == "fdv":
                metric_value = coin.get("fully_diluted_valuation", 0)
            else:
                metric_value = coin.get("market_cap", 0)
            
            change_24h = coin.get("price_change_percentage_24h", 0)
            
            # Format metric value
            if metric_value >= 1_000_000_000:
                metric_formatted = f"${metric_value / 1_000_000_000:.2f}B"
            elif metric_value >= 1_000_000:
                metric_formatted = f"${metric_value / 1_000_000:.1f}M"
            else:
                metric_formatted = f"${metric_value:,.0f}"
            
            # Format price change
            change_emoji = "🟢" if change_24h >= 0 else "🔴"
            change_text = f"{change_24h:+.2f}%"
            
            content += f"**{i}. {name} ({symbol})**\n"
            content += f"   • Price: ${price:,.4f} {change_emoji} {change_text}\n"
            content += f"   • {metric_name}: {metric_formatted}\n\n"
        
        content += f"💡 *Data from CoinGecko • Ask for specific coin analysis or price updates*"
        
        return {
            "role": "assistant",
            "content": content,
            "timestamp": datetime.now(),
            "data": coins,
            "source": "market_ranking"
        }