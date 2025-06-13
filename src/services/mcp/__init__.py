"""
MCP (Model Context Protocol) Services Package

This package contains services for integrating with MCP servers,
specifically for cryptocurrency data via CoinGecko MCP server.
"""

from .config import MCPConfig
from .coingecko_client import CoinGeckoMCPClient
from .exceptions import MCPConnectionError, MCPTimeoutError, MCPRateLimitError

__all__ = [
    'MCPConfig',
    'CoinGeckoMCPClient', 
    'MCPConnectionError',
    'MCPTimeoutError',
    'MCPRateLimitError'
] 