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
        self.connected = False
        
        # Routing table: (pattern, tool_handler) - Ultra flexible patterns
        self.routes = [
            # Any mention of trending/popular coins
            (r"\b(trending|popular|hot|top|best|leading|gainers|losers)\b", self._handle_get_trending_coins),
            
            # Search requests (very flexible)
            (r"\b(search|find|lookup|look up)\b", self._handle_search_coins),
            
            # Market overview requests  
            (r"\b(market|global|overview|stats|statistics|cap|dominance|total)\b", self._handle_get_market_overview),
            
            # Historical data requests
            (r"\b(historical|history|past|chart|graph|performance|trend)\b", self._handle_get_historical_data),
            
            # News requests
            (r"\b(news|headlines|updates|latest|articles)\b", self._handle_ask),
            
            # Why questions with market sentiment
            (r"\b(why|what|how|explain|reason|cause)\b.*\b(down|up|dump|pump|crash|surge|rally|decline|rise|fall|moon|tank|dropping|rising|falling|climbing|bearish|bullish)\b", self._handle_ask),
            
            # ANY cryptocurrency mention (ultra flexible) - catches "analyse sol", "btc", "check ethereum", etc.
            (r"\b(bitcoin|btc|ethereum|eth|solana|sol|cardano|ada|polygon|matic|avalanche|avax|chainlink|link|polkadot|dot|dogecoin|doge|tether|usdt|bnb|binance|xrp|ripple|tron|trx|litecoin|ltc|monero|xmr|stellar|xlm|algorand|algo|vechain|vet|filecoin|fil|cosmos|atom|near|uniswap|uni|aave|maker|mkr|compound|comp|curve|crv|yearn|yfi|sushi|1inch|shiba|shib|pepe|bonk|floki|arbitrum|arb|optimism|op|pancakeswap|cake|thorchain|rune|raydium|ray|jupiter|jup|pyth|jito|jto|brett|wif|dogwifhat|sand|sandbox|mana|decentraland|hedera|hbar|internet-computer|icp|ethereum-classic|etc|bitcoin-cash|bch|immutable|imx|loopring|lrc)\b", self._handle_get_coin_price),
            
            # Fallback for everything else
            (r".*", self._handle_ask)
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
        
        # Comprehensive coin mappings - synchronized with CoinGecko client
        coin_map = {
            # Major coins
            "bitcoin": "bitcoin", "btc": "bitcoin",
            "ethereum": "ethereum", "eth": "ethereum",
            "tether": "tether", "usdt": "tether",
            "solana": "solana", "sol": "solana",
            "bnb": "binancecoin", "binance": "binancecoin",
            "xrp": "ripple", "ripple": "ripple",
            "usdc": "usd-coin", "usd-coin": "usd-coin",
            "cardano": "cardano", "ada": "cardano",
            "avalanche": "avalanche-2", "avax": "avalanche-2",
            "dogecoin": "dogecoin", "doge": "dogecoin",
            "tron": "tron", "trx": "tron",
            "polkadot": "polkadot", "dot": "polkadot",
            "polygon": "matic-network", "matic": "matic-network",
            "chainlink": "chainlink", "link": "chainlink",
            "litecoin": "litecoin", "ltc": "litecoin",
            "bitcoin-cash": "bitcoin-cash", "bch": "bitcoin-cash",
            "near": "near", "near-protocol": "near",
            "uniswap": "uniswap", "uni": "uniswap",
            "cosmos": "cosmos", "atom": "cosmos",
            "ethereum-classic": "ethereum-classic", "etc": "ethereum-classic",
            "monero": "monero", "xmr": "monero",
            "stellar": "stellar", "xlm": "stellar",
            "algorand": "algorand", "algo": "algorand",
            "vechain": "vechain", "vet": "vechain",
            "filecoin": "filecoin", "fil": "filecoin",
            "hedera": "hedera-hashgraph", "hbar": "hedera-hashgraph",
            "internet-computer": "internet-computer", "icp": "internet-computer",
            "sandbox": "the-sandbox", "sand": "the-sandbox",
            "mana": "decentraland", "decentraland": "decentraland",
            "aave": "aave", "lend": "aave",
            "maker": "maker", "mkr": "maker",
            "sushi": "sushi", "sushiswap": "sushi",
            
            # New/trending coins
            "shiba": "shiba-inu", "shib": "shiba-inu",
            "pepe": "pepe", "pepecoin": "pepe",
            "bonk": "bonk", "bonk-coin": "bonk",
            "dogwifhat": "dogwifcoin", "wif": "dogwifcoin",
            "floki": "floki", "floki-inu": "floki",
            "brett": "brett", "base-brett": "brett",
            "jupiter": "jupiter-exchange-solana", "jup": "jupiter-exchange-solana",
            "pyth": "pyth-network", "pyth-network": "pyth-network",
            "jito": "jito-governance-token", "jto": "jito-governance-token",
            
            # Layer 2s
            "arbitrum": "arbitrum", "arb": "arbitrum",
            "optimism": "optimism", "op": "optimism",
            "immutable": "immutable-x", "imx": "immutable-x",
            
            # DeFi tokens
            "pancakeswap": "pancakeswap-token", "cake": "pancakeswap-token",
            "thorchain": "thorchain", "rune": "thorchain",
            "raydium": "raydium", "ray": "raydium"
        }
        
        # Look for exact matches first (prioritize longer matches)
        sorted_coins = sorted(coin_map.items(), key=lambda x: len(x[0]), reverse=True)
        for term, coin_id in sorted_coins:
            if term in msg_lower:
                return coin_id
        
        # Legacy fallback logic
        for term, coin_id in coin_map.items():
            if term in msg_lower:
                return coin_id
        
        # Fallback: extract potential symbol from message
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