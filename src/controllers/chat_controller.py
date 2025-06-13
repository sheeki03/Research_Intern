"""
Chat Controller

Processes user chat messages, calls MCP tools (via CoinGeckoMCPClient),
and returns structured responses for the CryptoChatbotPage.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List

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
    """Synchronously execute an async coroutine.

    Handle the case where we're already in an asyncio event loop (like Streamlit).
    If there's already a loop running, we need to handle it differently.
    """
    try:
        # Check if there's already an event loop running
        loop = asyncio.get_running_loop()
        # If we get here, there's already a loop running
        # We need to use asyncio.create_task or run in a thread
        import concurrent.futures
        import threading
        
        # Run the coroutine in a separate thread with its own event loop
        def run_in_thread():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                return new_loop.run_until_complete(coro)
            finally:
                new_loop.close()
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(run_in_thread)
            return future.result(timeout=30)  # 30 second timeout
            
    except RuntimeError:
        # No event loop running, we can create one
        return asyncio.run(coro)


class ChatController:
    """High-level chat orchestrator for the Crypto AI Assistant."""

    def __init__(self):
        self.client = CoinGeckoMCPClient()
        # Initialize web search service if available
        self.search_service = SearchService() if WEB_SEARCH_AVAILABLE else None
        # Connect lazily – first call will attempt connect
        self.connected = False

    def _ensure_connection(self):
        if not self.connected:
            try:
                success = _run(self.client.connect())
                self.connected = success
                if not success:
                    logger.warning("Falling back to REST API only mode – MCP connection failed or disabled.")
            except Exception as e:
                logger.error(f"Error during MCP connection: {e}")
                self.connected = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_message(self, message: str) -> Dict[str, Any]:
        """Process a user message and return a structured assistant response."""
        self._ensure_connection()

        text = message.lower().strip()

        try:
            if any(w in text for w in ["bitcoin", "btc"]):
                price = self.get_price("bitcoin")
                return self._format_price_response(price)

            if any(w in text for w in ["ethereum", "eth"]):
                price = self.get_price("ethereum")
                return self._format_price_response(price)

            if "trending" in text or "hot" in text or "popular" in text:
                trending = self.get_trending()
                return self._format_trending_response(trending)

            if "search" in text:
                query = text.split("search")[-1].strip()
                results = self.search_coins(query)
                return self._format_search_response(query, results)

            if "price" in text:
                # naive extraction of last word as coin id
                coin_id = text.split()[-1]
                price = self.get_price(coin_id)
                return self._format_price_response(price)

            if "compare" in text:
                query = text.replace("compare", " ").replace("vs", " ").replace(",", " ")
                coin_ids = [w for w in query.split() if w]
                if len(coin_ids) >= 2:
                    comparison = self._compare_coins(coin_ids[:5])
                    return self._format_comparison_response(comparison)
                else:
                    return {
                        "role": "assistant",
                        "content": "Please specify at least two coin symbols to compare.",
                        "timestamp": datetime.now(),
                    }

            if "chart" in text or "plot" in text:
                # extract coin id
                words = text.split()
                coin_id = None
                for w in words:
                    if w in ["bitcoin", "btc", "ethereum", "eth", "sol", "solana"] or len(w) > 2:
                        coin_id = w
                        break
                if coin_id:
                    chart = self._get_price_chart(coin_id)
                    return chart

            if "analyze" in text:
                # take first coin after analyze
                words = text.split()
                idx = words.index("analyze") if "analyze" in words else 0
                coin_id = words[idx+1] if idx+1 < len(words) else None
                if coin_id:
                    analysis = self._analyse_coin(coin_id)
                    return self._format_analysis_response(coin_id, analysis)
                else:
                    return {
                        "role": "assistant",
                        "content": "Please specify a coin to analyze, e.g., 'analyze bitcoin'.",
                        "timestamp": datetime.now(),
                    }

            # Market analysis questions (prioritize over general questions)
            if any(term in text for term in ["dump", "crash", "tanked", "nuked", "plunge", "dumped", "crashed", "fell", "drop", "dropped", "decline", "pump", "rally", "moon", "surge", "spike", "rise", "pump", "bull", "bear", "what happened", "why did", "market"]):
                return self._handle_market_analysis_question(text)

            # News questions
            if any(term in text for term in ["news", "latest", "recent", "update", "updates", "breaking", "headlines", "stories"]):
                return self._handle_news_question(text)

            # Market overview questions
            if any(term in text for term in ["market overview", "global market", "total market cap", "market stats"]):
                return self._handle_market_overview_question()

            # Historical data questions
            if any(term in text for term in ["history", "historical", "past", "chart", "graph"]) and any(coin in text for coin in ["bitcoin", "btc", "ethereum", "eth", "solana", "sol"]):
                coin_id = "bitcoin"
                if "ethereum" in text or "eth" in text:
                    coin_id = "ethereum"
                elif "solana" in text or "sol" in text:
                    coin_id = "solana"
                
                # Extract days if mentioned
                days = 7  # default
                if "30 day" in text or "month" in text:
                    days = 30
                elif "7 day" in text or "week" in text:
                    days = 7
                elif "1 year" in text or "year" in text:
                    days = 365
                
                return self._handle_historical_data_question(coin_id, days)

            # Natural language questions using MCP "ask" tool (only for non-market questions)
            if any(term in text for term in ["what", "how", "why", "when", "where", "tell me", "explain"]):
                return self._handle_natural_language_question(text)

            # Default fallback
            return {
                "role": "assistant",
                "content": "💭 I can help you with:\n\n🏷️ **Prices**: 'Bitcoin price', 'Ethereum price'\n📈 **Trending**: 'trending coins', 'what's hot'\n🔍 **Search**: 'search Solana'\n📊 **Compare**: 'compare Bitcoin vs Ethereum'\n📉 **Analysis**: 'analyze Bitcoin', 'why did market dump'\n📰 **News**: 'crypto news', 'Bitcoin news', 'latest updates'\n📋 **Market**: 'market overview', 'global stats'\n\nTry one of these or ask me anything about crypto!",
                "timestamp": datetime.now(),
            }
        except Exception as e:
            logger.exception("Error processing message: %s", e)
            return {
                "role": "assistant",
                "content": f"⚠️ Sorry, I ran into an error: {e}",
                "timestamp": datetime.now(),
            }

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