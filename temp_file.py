"""
CoinGecko MCP Client

Handles connection to CoinGecko MCP server with REST API fallback.
"""

import asyncio
import json
import logging
import subprocess
import time
from typing import List, Optional, Dict, Any, Union
from datetime import datetime
import aiohttp
import requests
import unicodedata
import xml.etree.ElementTree as ET

from .config import MCPConfig
from .models import (
    Tool, PriceData, CoinData, MarketData, SearchResult, 
    HistoricalData, HistoricalPrice, MCPResponse, TimeFrame
)
from .exceptions import (
    MCPConnectionError, MCPTimeoutError, MCPRateLimitError,
    MCPToolNotFoundError, MCPInvalidResponseError
)

logger = logging.getLogger(__name__)

class CoinGeckoMCPClient:
    """
    CoinGecko MCP Client with REST API fallback.
    
    Prioritizes MCP connection for real-time data, falls back to REST API
    when MCP is unavailable.
    """
    
    def __init__(self, config: Optional[MCPConfig] = None):
        """
        Initialize the MCP client.
        
        Args:
            config: MCP configuration instance
        """
        self.config = config or MCPConfig()
        self.mcp_process: Optional[subprocess.Popen] = None
        self.is_connected = False
        self.available_tools: List[Tool] = []
        self.last_health_check = 0
        self.session: Optional[aiohttp.ClientSession] = None
        
        # Rate limiting
        self.last_request_time = 0
        self.request_count = 0
        self.request_window_start = time.time()
        
    async def connect(self) -> bool:
        """
        Connect to CoinGecko MCP server.
        
        Returns:
            True if connected successfully, False otherwise
        """
        try:
            logger.info("Attempting to connect to CoinGecko MCP server...")
            
            # First try MCP connection
            if await self._connect_mcp():
                self.is_connected = True
                logger.info("✅ Successfully connected to CoinGecko MCP server")
                return True
            
            # Fallback to REST API validation
            logger.warning("MCP connection failed, validating REST API fallback...")
            if await self._validate_rest_api():
                self.is_connected = True
                logger.info("✅ REST API fallback validated and ready")
                return True
            
            logger.error("❌ Both MCP and REST API connections failed")
            return False
            
        except Exception as e:
            logger.error(f"Connection error: {e}")
            return False
    
    async def _connect_mcp(self) -> bool:
        """Attempt to connect to MCP server using mcp-remote."""
        try:
            coingecko_config = self.config.coingecko_config
            
            # Start mcp-remote process
            cmd = [coingecko_config['command']] + coingecko_config['args']
            
            logger.info(f"Starting MCP process: {' '.join(cmd)}")
            
            # Start the MCP process
            self.mcp_process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # Line buffered
                universal_newlines=True
            )
            
            # Give it time to initialize
            await asyncio.sleep(2)
            
            # Check if process is still running
            if self.mcp_process.poll() is None:
                # Try to discover tools
                tools = await self._discover_tools()
                if tools:
                    self.available_tools = tools
                    logger.info(f"Discovered {len(tools)} MCP tools")
                    return True
                else:
                    # Process failed to start
                    stderr_output = self.mcp_process.stderr.read() if self.mcp_process.stderr else ""
                    logger.error(f"MCP process failed to start: {stderr_output}")
                    return False
            
            return False
            
        except Exception as e:
            logger.error(f"MCP connection failed: {e}")
            return False
    
    async def _validate_rest_api(self) -> bool:
        """Validate REST API connectivity as fallback."""
        try:
            fallback_url = self.config.fallback_endpoints.get('coingecko_rest')
            if not fallback_url:
                return False
            
            # Test basic ping endpoint
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{fallback_url}/ping", timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"REST API ping successful: {data}")
                        return True
            
            return False
            
        except Exception as e:
            logger.error(f"REST API validation failed: {e}")
            return False
    
    async def _discover_tools(self) -> List[Tool]:
        """Discover available MCP tools."""
        try:
            # For now, we'll return known CoinGecko MCP tools
            # In a full implementation, this would send a JSON-RPC "tools/list" request
            coingecko_tools = [
            Tool(
                name="get_coin_price",
                description="Get current price for a cryptocurrency",
                input_schema={"type": "object", "properties": {"coin_id": {"type": "string"}}}
            ),
            Tool(
                name="get_trending_coins", 
                description="Get currently trending cryptocurrencies",
                input_schema={"type": "object", "properties": {}}
            ),
            Tool(
                name="search_coins",
                description="Search for cryptocurrencies by name or symbol",
                input_schema={"type": "object", "properties": {"query": {"type": "string"}}}
            ),
            Tool(
                name="get_market_overview",
                description="Get global cryptocurrency market overview",
                input_schema={"type": "object", "properties": {}}
                ),
                Tool(
                    name="get_historical_data",
                    description="Get historical price data for a cryptocurrency",
                    input_schema={"type": "object", "properties": {
                        "coin_id": {"type": "string"},
                        "days": {"type": "integer"}
                    }}
                ),
                Tool(
                    name="ask",
                    description="Ask natural language questions about cryptocurrency data",
                    input_schema={"type": "object", "properties": {"question": {"type": "string"}}}
                )
            ]
            
            logger.info(f"Discovered {len(coingecko_tools)} CoinGecko MCP tools")
            return coingecko_tools
            
        except Exception as e:
            logger.error(f"Tool discovery failed: {e}")
            return []
    
    async def disconnect(self) -> None:
        """Disconnect from MCP server."""
        if self.mcp_process:
            try:
                self.mcp_process.terminate()
                self.mcp_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.mcp_process.kill()
                self.mcp_process.wait()
            
            self.mcp_process = None
        
        if self.session:
            await self.session.close()
            self.session = None
        
        self.is_connected = False
        logger.info("Disconnected from MCP server")
    
    async def list_tools(self) -> List[Tool]:
        """List available MCP tools."""
        if not self.is_connected:
            raise MCPConnectionError("Not connected to MCP server")
        
        return self.available_tools
    
    async def get_coin_price(self, coin_id: str) -> PriceData:
        """
        Get current price for a cryptocurrency.
        
        Args:
            coin_id: CoinGecko coin ID (e.g., 'bitcoin', 'ethereum')
            
        Returns:
            PriceData with current price information
        """
        try:
            # Try MCP first
            if self.is_connected and await self._has_mcp_tool("get_coin_price"):
                return await self._mcp_get_coin_price(coin_id)
            
            # Fallback to REST API
            return await self._rest_get_coin_price(coin_id)
            
        except Exception as e:
            logger.error(f"Failed to get coin price for {coin_id}: {e}")
            raise
    
    async def _mcp_get_coin_price(self, coin_id: str) -> PriceData:
        """Get coin price via MCP."""
        try:
            # Create MCP JSON-RPC request
            request = {
                "jsonrpc": "2.0",
                "id": f"price_{coin_id}_{int(time.time())}",
                "method": "tools/call",
                "params": {
                    "name": "get_coin_price",
                    "arguments": {"coin_id": coin_id}
                }
            }
            
            # Send request to MCP process and get response
            if self.mcp_process and self.mcp_process.poll() is None:
                response = await self._send_mcp_request(request)
                if response and response.get("result"):
                    # Parse MCP response and convert to PriceData
                    result = response["result"]
                    content = result.get("content", [])
                    if content and len(content) > 0:
                        data = json.loads(content[0].get("text", "{}"))
                        return self._parse_price_data(data, coin_id)
                
                # If MCP response parsing fails, fall back to REST
                logger.warning("MCP response parsing failed, falling back to REST")
                return await self._rest_get_coin_price(coin_id)
            else:
                logger.warning("MCP process not running, falling back to REST")
                return await self._rest_get_coin_price(coin_id)
                
        except Exception as e:
            logger.error(f"MCP get_coin_price failed: {e}, falling back to REST")
            return await self._rest_get_coin_price(coin_id)
    
    async def _rest_get_coin_price(self, coin_id: str) -> PriceData:
        """Get coin price via REST API."""
        await self._check_rate_limit()
        
        url = f"{self.config.fallback_endpoints['coingecko_rest']}/simple/price"
        params = {
            'ids': coin_id,
            'vs_currencies': 'usd',
            'include_market_cap': 'true',
            'include_24hr_vol': 'true',
            'include_24hr_change': 'true',
            'include_last_updated_at': 'true'
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        coin_data = data.get(coin_id, {})
                        
                        return PriceData(
                            coin_id=coin_id,
                            symbol=coin_id,  # Will be improved with coin info
                            name=coin_id.replace('-', ' ').title(),
                            current_price=coin_data.get('usd', 0),
                            market_cap=coin_data.get('usd_market_cap'),
                            volume_24h=coin_data.get('usd_24h_vol'),
                            price_change_percentage_24h=coin_data.get('usd_24h_change'),
                            last_updated=datetime.fromtimestamp(coin_data.get('last_updated_at', time.time()))
                        )
                    else:
                        raise MCPInvalidResponseError(f"REST API error: {response.status}")
        
        except Exception as e:
            logger.error(f"REST API request failed: {e}")
            raise
    
    async def get_trending_coins(self) -> List[CoinData]:
        """Get currently trending cryptocurrencies."""
        try:
            if self.is_connected and await self._has_mcp_tool("get_trending_coins"):
                return await self._mcp_get_trending_coins()
            
            return await self._rest_get_trending_coins()
            
        except Exception as e:
            logger.error(f"Failed to get trending coins: {e}")
            raise
    
    async def _rest_get_trending_coins(self) -> List[CoinData]:
        """Get trending coins via REST API."""
        await self._check_rate_limit()
        
        url = f"{self.config.fallback_endpoints['coingecko_rest']}/search/trending"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        trending_coins = []
                        
                        for coin in data.get('coins', [])[:10]:  # Top 10
                            coin_item = coin.get('item', {})
                            trending_coins.append(CoinData(
                                id=coin_item.get('id', ''),
                                symbol=coin_item.get('symbol', ''),
                                name=coin_item.get('name', ''),
                                market_cap_rank=coin_item.get('market_cap_rank'),
                                image=coin_item.get('thumb')
                            ))
                        
                        return trending_coins
                    else:
                        raise MCPInvalidResponseError(f"REST API error: {response.status}")
        
        except Exception as e:
            logger.error(f"REST API request failed: {e}")
            raise
    
    async def search_coins(self, query: str) -> List[SearchResult]:
        """Search for cryptocurrencies by name or symbol."""
        await self._check_rate_limit()
        
        url = f"{self.config.fallback_endpoints['coingecko_rest']}/search"
        params = {'query': query}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        results = []
                        
                        for coin in data.get('coins', [])[:10]:  # Top 10 results
                            results.append(SearchResult(
                                id=coin.get('id', ''),
                                name=coin.get('name', ''),
                                symbol=coin.get('symbol', ''),
                                market_cap_rank=coin.get('market_cap_rank'),
                                thumb=coin.get('thumb'),
                                large=coin.get('large')
                            ))
                        
                        return results
                    else:
                        raise MCPInvalidResponseError(f"REST API error: {response.status}")
        
        except Exception as e:
            logger.error(f"Search request failed: {e}")
            raise
    
    async def _has_mcp_tool(self, tool_name: str) -> bool:
        """Check if MCP tool is available."""
        return any(tool.name == tool_name for tool in self.available_tools)
    
    async def _check_rate_limit(self) -> None:
        """Check and enforce rate limits."""
        current_time = time.time()
        
        # Reset window if needed
        if current_time - self.request_window_start >= 60:
            self.request_count = 0
            self.request_window_start = current_time
        
        # Check rate limit
        rate_config = self.config.coingecko_config.get('rateLimits', {})
        max_requests = rate_config.get('requestsPerMinute', 100)
        
        if self.request_count >= max_requests:
            wait_time = 60 - (current_time - self.request_window_start)
            if wait_time > 0:
                logger.warning(f"Rate limit reached, waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)
                self.request_count = 0
                self.request_window_start = time.time()
        
        self.request_count += 1
        self.last_request_time = current_time
    
    async def _send_mcp_request(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Send MCP JSON-RPC request and get response."""
        try:
            if not self.mcp_process or self.mcp_process.poll() is not None:
                logger.error("MCP process not running")
                return None
            
            # Write request to stdin
            request_json = json.dumps(request) + "\n"
            self.mcp_process.stdin.write(request_json)
            self.mcp_process.stdin.flush()
            
            # Read response from stdout with timeout
            start_time = time.time()
            timeout = 15  # Increased to 15 seconds for complex queries
            
            # Collect all responses
            responses = []
            target_id = request.get("id")
            
            while time.time() - start_time < timeout:
                if self.mcp_process.stdout.readable():
                    try:
                        line = self.mcp_process.stdout.readline()
                        if line:
                            line = line.strip()
                            if line:
                                try:
                                    response = json.loads(line)
                                    responses.append(response)
                                    
                                    # Check if this is our response
                                    if response.get("id") == target_id:
                                        logger.debug(f"MCP response received: {response}")
                                        return response
                                    
                                    # Handle notification or other responses
                                    elif "result" in response or "error" in response:
                                        # Might be an async response without ID match
                                        responses.append(response)
                                        
                                except json.JSONDecodeError as je:
                                    logger.debug(f"JSON decode error: {je}, line: {line}")
                                    continue
                    except Exception as read_error:
                        logger.debug(f"Read error: {read_error}")
                        continue
                        
                await asyncio.sleep(0.1)
            
            # If no exact match, try to find a suitable response
            for response in responses:
                if "result" in response and response.get("result"):
                    logger.debug(f"Using fallback response: {response}")
                    return response
            
            logger.warning(f"MCP request timeout after {timeout}s, collected {len(responses)} responses")
            logger.debug(f"Collected responses: {responses}")
            return None
            
        except Exception as e:
            logger.error(f"MCP request failed: {e}")
            return None
    
    def _parse_price_data(self, data: Dict[str, Any], coin_id: str) -> PriceData:
        """Parse price data from MCP response."""
        try:
            # Handle different possible response formats
            if coin_id in data:
                coin_data = data[coin_id]
            elif 'data' in data:
                coin_data = data['data']
            else:
                coin_data = data
            
            return PriceData(
                id=coin_id,
                symbol=coin_data.get('symbol', ''),
                name=coin_data.get('name', coin_id.title()),
                current_price=float(coin_data.get('current_price', coin_data.get('usd', 0))),
                market_cap=coin_data.get('market_cap'),
                market_cap_rank=coin_data.get('market_cap_rank'),
                fully_diluted_valuation=coin_data.get('fully_diluted_valuation'),
                total_volume=coin_data.get('total_volume'),
                high_24h=coin_data.get('high_24h'),
                low_24h=coin_data.get('low_24h'),
                price_change_24h=coin_data.get('price_change_24h'),
                price_change_percentage_24h=coin_data.get('price_change_percentage_24h'),
                market_cap_change_24h=coin_data.get('market_cap_change_24h'),
                market_cap_change_percentage_24h=coin_data.get('market_cap_change_percentage_24h'),
                circulating_supply=coin_data.get('circulating_supply'),
                total_supply=coin_data.get('total_supply'),
                max_supply=coin_data.get('max_supply'),
                ath=coin_data.get('ath'),
                ath_change_percentage=coin_data.get('ath_change_percentage'),
                ath_date=coin_data.get('ath_date'),
                atl=coin_data.get('atl'),
                atl_change_percentage=coin_data.get('atl_change_percentage'),
                atl_date=coin_data.get('atl_date'),
                last_updated=coin_data.get('last_updated')
            )
            
        except Exception as e:
            logger.error(f"Error parsing price data: {e}")
            raise MCPInvalidResponseError(f"Failed to parse price data: {e}")
    
    async def _mcp_get_trending_coins(self) -> List[CoinData]:
        """Get trending coins via MCP."""
        try:
            # Create MCP JSON-RPC request
            request = {
                "jsonrpc": "2.0",
                "id": f"trending_{int(time.time())}",
                "method": "tools/call",
                "params": {
                    "name": "get_trending_coins",
                    "arguments": {}
                }
            }
            
            # Send request to MCP process and get response
            if self.mcp_process and self.mcp_process.poll() is None:
                response = await self._send_mcp_request(request)
                if response and response.get("result"):
                    # Parse MCP response and convert to CoinData list
                    result = response["result"]
                    content = result.get("content", [])
                    if content and len(content) > 0:
                        data = json.loads(content[0].get("text", "{}"))
                        return self._parse_trending_data(data)
                
                # If MCP response parsing fails, fall back to REST
                logger.info("MCP response parsing failed, using REST fallback for trending coins")
                return await self._rest_get_trending_coins()
            else:
                logger.warning("MCP process not running, falling back to REST")
                return await self._rest_get_trending_coins()
                
        except Exception as e:
            logger.error(f"MCP get_trending_coins failed: {e}, falling back to REST")
            return await self._rest_get_trending_coins()
    
    def _parse_trending_data(self, data: Dict[str, Any]) -> List[CoinData]:
        """Parse trending data from MCP response."""
        try:
            trending_coins = []
            
            # Handle different possible response formats
            coins_data = data.get('coins', data.get('data', []))
            
            for coin in coins_data[:10]:  # Top 10
                coin_item = coin.get('item', coin)
                trending_coins.append(CoinData(
                    id=coin_item.get('id', ''),
                    symbol=coin_item.get('symbol', ''),
                    name=coin_item.get('name', ''),
                    market_cap_rank=coin_item.get('market_cap_rank'),
                    image=coin_item.get('thumb', coin_item.get('image'))
                ))
            
            return trending_coins
            
        except Exception as e:
            logger.error(f"Error parsing trending data: {e}")
            raise MCPInvalidResponseError(f"Failed to parse trending data: {e}")
    
    async def ask_question(self, question: str) -> Dict[str, Any]:
        """
        Ask a natural language question about cryptocurrency data using MCP.
        
        Args:
            question: Natural language question about crypto data
            
        Returns:
            Dictionary with answer and metadata
        """
        try:
            # Try MCP first if available
            if self.is_connected and await self._has_mcp_tool("ask"):
                return await self._mcp_ask_question(question)
            
            # Fallback to REST-based analysis
            return await self._rest_analyze_question(question)
            
        except Exception as e:
            logger.error(f"Failed to answer question '{question}': {e}")
            return {
                "answer": f"I encountered an error while processing your question: {str(e)}",
                "error": True,
                "source": "error"
            }
    
    async def _mcp_ask_question(self, question: str) -> Dict[str, Any]:
        """Ask question via MCP."""
        try:
            request = {
                "jsonrpc": "2.0",
                "id": f"ask_{int(time.time())}",
                "method": "tools/call",
                "params": {
                    "name": "ask",
                    "arguments": {"question": question}
                }
            }
            
            if self.mcp_process and self.mcp_process.poll() is None:
                response = await self._send_mcp_request(request)
                if response and response.get("result"):
                    # Parse MCP response - handle nested data structure
                    result = response["result"]
                    content = result.get("content", [])
                    if content and len(content) > 0:
                        text_content = content[0].get("text", "")
                        
                        # Try to parse as JSON first (CoinGecko wraps in {"data": {"answer": "..."}})
                        try:
                            parsed_data = json.loads(text_content)
                            if isinstance(parsed_data, dict) and "data" in parsed_data:
                                answer = parsed_data["data"].get("answer", text_content)
                            else:
                                answer = text_content
                        except (json.JSONDecodeError, TypeError):
                            # If not JSON, use raw text
                            answer = text_content
                        
                        return {
                            "answer": answer,
                            "source": "mcp",
                            "error": False
                        }
                
                # If MCP response parsing fails, fall back to REST
                logger.info("MCP response parsing failed, using REST fallback for question answering")
                return await self._rest_analyze_question(question)
            else:
                return await self._rest_analyze_question(question)
                
        except Exception as e:
            logger.error(f"MCP ask failed: {e}")
            return await self._rest_analyze_question(question)
    
    async def _rest_analyze_question(self, question: str) -> Dict[str, Any]:
        """Analyze question using REST APIs and provide structured answer."""
        try:
            # Simple keyword-based analysis for common questions
            question_lower = question.lower()
            
            # Market dump/crash analysis
            if any(term in question_lower for term in ["dump", "crash", "down", "drop", "fell", "plunge", "dip", "decline"]):
                return await self._analyze_market_movement("down", question_lower)
            
            # Market pump/rally analysis  
            elif any(term in question_lower for term in ["pump", "rally", "up", "rise", "surge", "moon", "bull", "gain"]):
                return await self._analyze_market_movement("up", question_lower)
            
            # Price questions
            elif "price" in question_lower and any(coin in question_lower for coin in ["bitcoin", "btc", "ethereum", "eth", "solana", "sol"]):
                # Extract coin from question
                coin_id = "bitcoin"
                if "ethereum" in question_lower or "eth" in question_lower:
                    coin_id = "ethereum"
                elif "solana" in question_lower or "sol" in question_lower:
                    coin_id = "solana"
                
                price_data = await self._rest_get_coin_price(coin_id)
                return {
                    "answer": f"The current price of {price_data.name} ({price_data.symbol.upper()}) is ${price_data.current_price:,.2f}. "
                             f"It has changed {price_data.price_change_percentage_24h:+.2f}% in the last 24 hours.",
                    "data": price_data,
                    "source": "rest_api",
                    "error": False
                }
            
            elif "trending" in question_lower:
                trending_data = await self._rest_get_trending_coins()
                coin_names = [coin.name for coin in trending_data[:5]]
                return {
                    "answer": f"The top trending cryptocurrencies right now are: {', '.join(coin_names)}.",
                    "data": trending_data,
                    "source": "rest_api", 
                    "error": False
                }
            
            # Crypto news query
            elif "news" in question_lower:
                headlines = await self._fetch_crypto_news()
                if headlines:
                    answer_lines = ["📰 **Latest Crypto News Headlines (last 24h)**\n"]
                    for title, link in headlines:
                        answer_lines.append(f"- [{title}]({link})")
                    answer = "\n".join(answer_lines)
                    return {
                        "answer": answer,
                        "data": {"headlines": headlines},
                        "source": "crypto_news_rss",
                        "error": False
                    }
                else:
                    return {
                        "answer": "Sorry, I couldn't fetch the latest crypto news at the moment. Please try again later.",
                        "source": "crypto_news_rss",
                        "error": False
                    }
            
            else:
                return {
                    "answer": "I can help you with cryptocurrency price information and trending coins. Try asking about Bitcoin price or trending cryptocurrencies!",
                    "source": "fallback",
                    "error": False
                }
                
        except Exception as e:
            logger.error(f"REST analysis failed: {e}")
            return {
                "answer": f"I encountered an error while analyzing your question: {str(e)}",
                "error": True,
                "source": "error"
            }
    
    async def _analyze_market_movement(self, direction: str, question: str) -> Dict[str, Any]:
        """Analyze market movement and provide insights."""
        try:
            # Get current market data
            btc_data = await self._rest_get_coin_price("bitcoin")
            eth_data = await self._rest_get_coin_price("ethereum")
            market_data = await self._rest_get_market_overview()
            
            # Search for recent crypto news related to market movement
            news_headlines = await self._search_crypto_news_web(direction, question)
            
            # Analyze sentiment based on major coins
            btc_change = btc_data.price_change_percentage_24h or 0
            eth_change = eth_data.price_change_percentage_24h or 0
            market_change = market_data.market_cap_change_percentage_24h_usd or 0
            
            # Determine market condition
            avg_change = (btc_change + eth_change + market_change) / 3
            
            if direction == "down":
                if avg_change < -5:
                    condition = "significant decline"
                    emoji = "📉"
                elif avg_change < -2:
                    condition = "moderate decline"
                    emoji = "⬇️"
                else:
                    condition = "minor correction"
                    emoji = "🔻"
                
                analysis = f"{emoji} **Market Analysis - {condition.title()}**\n\n"
                analysis += f"The cryptocurrency market is experiencing a {condition} with several factors potentially contributing:\n\n"
                
                # Key metrics
                analysis += f"📊 **Current Metrics:**\n"
                bullet = "- "
                analysis += (
                    f"{bullet}Bitcoin: ${btc_data.current_price:,.2f} ({btc_change:+.2f}%)\n"
                    f"{bullet}Ethereum: ${eth_data.current_price:,.2f} ({eth_change:+.2f}%)\n"
                    f"{bullet}Total Market Cap: {market_change:+.2f}% (24h)\n\n"
                )
                
                # Add recent news if found
                if news_headlines:
                    analysis += f"📰 **Recent News Impact:**\n"
                    for headline in news_headlines[:3]:  # Top 3 headlines
                        analysis += f"{bullet}[{headline['title']}]({headline['url']})\n"
                    analysis += "\n"
                
                # Potential factors
                analysis += f"🔍 **Potential Factors:**\n"
                analysis += f"• **Profit Taking**: Investors may be securing gains after recent rallies\n"
                analysis += f"• **Market Sentiment**: Fear, uncertainty, or negative news affecting confidence\n"
                analysis += f"• **Technical Correction**: Natural price adjustment after rapid growth\n"
                analysis += f"• **External Factors**: Regulatory news, macroeconomic events, or institutional movements\n\n"
                
                analysis += f"💡 **Insight**: Market volatility is normal in crypto. Consider this an opportunity for long-term investors."
                
                # Normalize and return
                analysis = unicodedata.normalize("NFKD", analysis)

                return {
                    "answer": analysis,
                    "data": {
                        "btc": btc_data,
                        "eth": eth_data,
                        "market": market_data,
                        "news": news_headlines
                    },
                    "source": "market_analysis",
                    "error": False
                }
            
            else:  # direction == "up"
                if avg_change > 5:
                    condition = "strong rally"
                    emoji = "🚀"
                elif avg_change > 2:
                    condition = "moderate gain"
                    emoji = "📈"
                else:
                    condition = "slight uptick"
                    emoji = "🔺"
                
                analysis = f"{emoji} **Market Analysis - {condition.title()}**\n\n"
                analysis += f"The cryptocurrency market is experiencing a {condition} with positive momentum building:\n\n"
                
                # Key metrics
                analysis += f"📊 **Current Metrics:**\n"
                bullet = "- "
                analysis += (
                    f"{bullet}Bitcoin: ${btc_data.current_price:,.2f} ({btc_change:+.2f}%)\n"
                    f"{bullet}Ethereum: ${eth_data.current_price:,.2f} ({eth_change:+.2f}%)\n"
                    f"{bullet}Total Market Cap: {market_change:+.2f}% (24h)\n\n"
                )
                
                # Add recent news if found
                if news_headlines:
                    analysis += f"📰 **Recent News Impact:**\n"
                    for headline in news_headlines[:3]:  # Top 3 headlines
                        analysis += f"{bullet}[{headline['title']}]({headline['url']})\n"
                    analysis += "\n"
                
                # Positive factors
                analysis += f"🔍 **Driving Factors:**\n"
                analysis += f"• **Institutional Interest**: Growing adoption and investment from institutions\n"
                analysis += f"• **Market Sentiment**: Increased confidence and positive news flow\n"
                analysis += f"• **Technical Breakout**: Price breaking through key resistance levels\n"
                analysis += f"• **Fundamental Growth**: Improving technology and use case adoption\n\n"
                
                analysis += f"💡 **Insight**: Positive market momentum may attract more investors."
                
                # Normalize and return
                analysis = unicodedata.normalize("NFKD", analysis)

                return {
                    "answer": analysis,
                    "data": {
                        "btc": btc_data,
                        "eth": eth_data,
                        "market": market_data,
                        "news": news_headlines
                    },
                    "source": "market_analysis",
                    "error": False
                }
            
        except Exception as e:
            logger.error(f"Market analysis failed: {e}")
            return {
                "answer": f"I encountered an error analyzing the market movement: {str(e)}",
                "error": True,
                "source": "error"
            }
    
    async def get_market_overview(self) -> MarketData:
        """Get global market overview."""
        try:
            # Try MCP first if available
            if self.is_connected and await self._has_mcp_tool("get_market_overview"):
                return await self._mcp_get_market_overview()
            
            # Fallback to REST API
            return await self._rest_get_market_overview()
            
        except Exception as e:
            logger.error(f"Failed to get market overview: {e}")
            raise
    
    async def _mcp_get_market_overview(self) -> MarketData:
        """Get market overview via MCP."""
        try:
            request = {
                "jsonrpc": "2.0",
                "id": f"market_{int(time.time())}",
                "method": "tools/call",
                "params": {
                    "name": "get_market_overview",
                    "arguments": {}
                }
            }
            
            if self.mcp_process and self.mcp_process.poll() is None:
                response = await self._send_mcp_request(request)
                if response and response.get("result"):
                    result = response["result"]
                    content = result.get("content", [])
                    if content and len(content) > 0:
                        data = json.loads(content[0].get("text", "{}"))
                        return self._parse_market_data(data)
                
                logger.info("MCP response parsing failed, using REST fallback for market overview")
                
            return await self._rest_get_market_overview()
                
        except Exception as e:
            logger.error(f"MCP get_market_overview failed: {e}")
            return await self._rest_get_market_overview()
    
    async def _rest_get_market_overview(self) -> MarketData:
        """Get market overview via REST API."""
        await self._check_rate_limit()
        
        url = f"{self.config.fallback_endpoints['coingecko_rest']}/global"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        global_data = data.get('data', {})
                        return MarketData(
                            total_market_cap=global_data.get('total_market_cap', {}),
                            total_volume=global_data.get('total_volume', {}),
                            market_cap_percentage=global_data.get('market_cap_percentage', {}),
                            market_cap_change_percentage_24h_usd=global_data.get('market_cap_change_percentage_24h_usd'),
                            active_cryptocurrencies=global_data.get('active_cryptocurrencies'),
                            upcoming_icos=global_data.get('upcoming_icos'),
                            ongoing_icos=global_data.get('ongoing_icos'),
                            ended_icos=global_data.get('ended_icos'),
                            updated_at=global_data.get('updated_at')
                        )
                    else:
                        raise MCPInvalidResponseError(f"REST API error: {response.status}")
        
        except Exception as e:
            logger.error(f"REST API request failed: {e}")
            raise
    
    def _parse_market_data(self, data: Dict[str, Any]) -> MarketData:
        """Parse market data from MCP response."""
        try:
            global_data = data.get('data', data)
            return MarketData(
                total_market_cap=global_data.get('total_market_cap', {}),
                total_volume=global_data.get('total_volume', {}),
                market_cap_percentage=global_data.get('market_cap_percentage', {}),
                market_cap_change_percentage_24h_usd=global_data.get('market_cap_change_percentage_24h_usd'),
                active_cryptocurrencies=global_data.get('active_cryptocurrencies'),
                upcoming_icos=global_data.get('upcoming_icos'),
                ongoing_icos=global_data.get('ongoing_icos'),
                ended_icos=global_data.get('ended_icos'),
                updated_at=global_data.get('updated_at')
            )
        except Exception as e:
            logger.error(f"Error parsing market data: {e}")
            raise MCPInvalidResponseError(f"Failed to parse market data: {e}")
    
    async def get_historical_data(self, coin_id: str, days: int) -> HistoricalData:
        """Get historical price data."""
        try:
            # Try MCP first if available
            if self.is_connected and await self._has_mcp_tool("get_historical_data"):
                return await self._mcp_get_historical_data(coin_id, days)
            
            # Fallback to REST API
            return await self._rest_get_historical_data(coin_id, days)
            
        except Exception as e:
            logger.error(f"Failed to get historical data: {e}")
            raise
    
    async def _mcp_get_historical_data(self, coin_id: str, days: int) -> HistoricalData:
        """Get historical data via MCP."""
        try:
            request = {
                "jsonrpc": "2.0",
                "id": f"historical_{coin_id}_{int(time.time())}",
                "method": "tools/call",
                "params": {
                    "name": "get_historical_data",
                    "arguments": {"coin_id": coin_id, "days": days}
                }
            }
            
            if self.mcp_process and self.mcp_process.poll() is None:
                response = await self._send_mcp_request(request)
                if response and response.get("result"):
                    result = response["result"]
                    content = result.get("content", [])
                    if content and len(content) > 0:
                        data = json.loads(content[0].get("text", "{}"))
                        return self._parse_historical_data(data, coin_id)
                
                logger.info("MCP response parsing failed, using REST fallback for historical data")
                
            return await self._rest_get_historical_data(coin_id, days)
                
        except Exception as e:
            logger.error(f"MCP get_historical_data failed: {e}")
            return await self._rest_get_historical_data(coin_id, days)
    
    async def _rest_get_historical_data(self, coin_id: str, days: int) -> HistoricalData:
        """Get historical data via REST API."""
        await self._check_rate_limit()

        url = f"{self.config.fallback_endpoints['coingecko_rest']}/coins/{coin_id}/market_chart"
        params = {
            'vs_currency': 'usd',
            'days': days,
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=15) as response:
                    if response.status == 200:
                        data = await response.json()
                        return self._parse_historical_data(data, coin_id)
                    else:
                        raise MCPInvalidResponseError(f"REST API error: {response.status}")
        except Exception as e:
            logger.error(f"Failed to fetch historical data: {e}")
            raise
    
    def _parse_historical_data(self, data: Dict[str, Any], coin_id: str) -> HistoricalData:
        """Parse historical data from response."""
        try:
            from datetime import datetime
            prices = [HistoricalPrice(timestamp=datetime.fromtimestamp(p[0]/1000), price=p[1]) for p in data.get('prices', [])]
            market_caps = [HistoricalPrice(timestamp=datetime.fromtimestamp(m[0]/1000), price=m[1]) for m in data.get('market_caps', [])]
            volumes = [HistoricalPrice(timestamp=datetime.fromtimestamp(v[0]/1000), price=v[1]) for v in data.get('total_volumes', [])]
            return HistoricalData(
                coin_id=coin_id,
                prices=prices,
                market_caps=market_caps,
                total_volumes=volumes
            )
        except Exception as e:
            logger.error(f"Error parsing historical data: {e}")
            raise MCPInvalidResponseError(f"Failed to parse historical data: {e}")
    
    async def _fetch_crypto_news(self, limit: int = 5):
        """Fetch latest crypto news headlines from CoinDesk RSS."""
        rss_url = "https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(rss_url, timeout=10) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        root = ET.fromstring(text)
                        channel = root.find('channel')
                        items = channel.findall('item') if channel is not None else []
                        headlines = []
                        for item in items[:limit]:
                            title = item.findtext('title', default='')
                            link = item.findtext('link', default='')
                            if title and link:
                                headlines.append((title, link))
                        return headlines
        except Exception as e:
            logger.error(f"Failed to fetch crypto news RSS: {e}")
        return []

    async def _search_crypto_news_web(self, direction: str, question: str) -> List[Dict[str, str]]:
        """Search web for recent crypto news related to market movement."""
        try:
            # Build search query based on direction and question
            # Extract specific coins from question for targeted search
            question_lower = question.lower()
            specific_coins = []
            coin_keywords = {
                'bitcoin': 'bitcoin', 'btc': 'bitcoin',
                'ethereum': 'ethereum', 'eth': 'ethereum', 
                'solana': 'solana', 'sol': 'solana',
                'cardano': 'cardano', 'ada': 'cardano',
                'polkadot': 'polkadot', 'dot': 'polkadot',
                'chainlink': 'chainlink', 'link': 'chainlink',
                'polygon': 'polygon', 'matic': 'polygon'
            }
            
            for keyword, coin_name in coin_keywords.items():
                if keyword in question_lower:
                    specific_coins.append(coin_name)
            
            # Use first search term + specific coin if found
            search_query = search_terms[0]
            if specific_coins:
                search_query = f"{specific_coins[0]} {search_terms[0]}"
            
            # Simple web search using DuckDuckGo or Google News RSS
            # For now, return CoinDesk headlines as they're crypto-focused
            headlines = await self._fetch_crypto_news(limit=5)
            
            # Convert to expected format
            news_results = []
            for title, url in headlines:
                # Filter for relevant keywords
                title_lower = title.lower()
                if any(term in title_lower for term in ['bitcoin', 'crypto', 'ethereum', 'market', 'price']):
                    news_results.append({
                        'title': title,
                        'url': url,
                        'relevance': 'high' if any(coin in title_lower for coin in specific_coins) else 'medium'
                    })
            
            return news_results
            
        except Exception as e:
            logger.error(f"Web news search failed: {e}")
            return []

    def _get_comprehensive_coin_mapping(self) -> Dict[str, str]:
        """Get comprehensive mapping of coin symbols/names to CoinGecko IDs."""
        return {
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
            "leo": "leo-token", "leo-token": "leo-token",
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
            "compound": "compound-governance-token", "comp": "compound-governance-token",
            "sushi": "sushi", "sushiswap": "sushi",
            "curve": "curve-dao-token", "crv": "curve-dao-token",
            "1inch": "1inch", "1inch-network": "1inch",
            "yearn": "yearn-finance", "yfi": "yearn-finance",
            
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
            "loopring": "loopring", "lrc": "loopring",
            
            # DeFi tokens
            "pancakeswap": "pancakeswap-token", "cake": "pancakeswap-token",
            "thorchain": "thorchain", "rune": "thorchain",
            "raydium": "raydium", "ray": "raydium",
            "serum": "serum", "srm": "serum"
        } 