"""
Data Models for MCP Responses and Crypto Data

Defines Pydantic models for type-safe data handling.
"""

from typing import List, Optional, Dict, Any, Union
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

# Since we can't install pydantic yet, I'll use dataclasses for now
# TODO: Replace with Pydantic models when dependencies are available

@dataclass
class Tool:
    """Represents an MCP tool/function."""
    name: str
    description: str
    input_schema: Dict[str, Any]

@dataclass  
class PriceData:
    """Cryptocurrency price information."""
    coin_id: str
    symbol: str
    name: str
    current_price: float
    price_usd: Optional[float] = None
    change_24h: Optional[float] = None
    volume_24h: Optional[float] = None
    market_cap: Optional[float] = None
    market_cap_rank: Optional[int] = None
    fully_diluted_valuation: Optional[float] = None
    total_volume: Optional[float] = None
    high_24h: Optional[float] = None
    low_24h: Optional[float] = None
    price_change_24h: Optional[float] = None
    price_change_percentage_24h: Optional[float] = None
    market_cap_change_24h: Optional[float] = None
    market_cap_change_percentage_24h: Optional[float] = None
    circulating_supply: Optional[float] = None
    total_supply: Optional[float] = None
    max_supply: Optional[float] = None
    ath: Optional[float] = None
    ath_change_percentage: Optional[float] = None
    ath_date: Optional[str] = None
    atl: Optional[float] = None
    atl_change_percentage: Optional[float] = None
    atl_date: Optional[str] = None
    last_updated: Optional[str] = None
    
    id: Optional[str] = None
    
    def __post_init__(self):
        """Handle field aliasing and backward compatibility."""
        if self.id is None:
            self.id = self.coin_id
        if self.price_usd and not self.current_price:
            self.current_price = self.price_usd
        if self.change_24h and not self.price_change_24h:
            self.price_change_24h = self.change_24h
        if self.volume_24h and not self.total_volume:
            self.total_volume = self.volume_24h

@dataclass
class CoinData:
    """Comprehensive coin information."""
    id: str
    symbol: str
    name: str
    image: Optional[str] = None
    current_price: Optional[float] = None
    market_cap: Optional[float] = None
    market_cap_rank: Optional[int] = None
    fully_diluted_valuation: Optional[float] = None
    total_volume: Optional[float] = None
    high_24h: Optional[float] = None
    low_24h: Optional[float] = None
    price_change_24h: Optional[float] = None
    price_change_percentage_24h: Optional[float] = None
    price_change_percentage_7d: Optional[float] = None
    price_change_percentage_30d: Optional[float] = None
    circulating_supply: Optional[float] = None
    total_supply: Optional[float] = None
    max_supply: Optional[float] = None
    ath: Optional[float] = None
    ath_date: Optional[datetime] = None
    atl: Optional[float] = None
    atl_date: Optional[datetime] = None

@dataclass
class MarketData:
    """Global market overview data."""
    total_market_cap: Dict[str, float]
    total_volume: Dict[str, float]
    market_cap_percentage: Dict[str, float]
    active_cryptocurrencies: int
    upcoming_icos: int
    ongoing_icos: int
    ended_icos: int
    updated_at: Optional[datetime] = None
    markets: Optional[int] = None
    market_cap_change_percentage_24h_usd: Optional[float] = None
    
    # Additional fields for easier access
    total_market_cap_usd: Optional[float] = None
    total_volume_usd: Optional[float] = None
    btc_dominance: Optional[float] = None
    
    def __post_init__(self):
        """Extract USD values for easier access."""
        if self.total_market_cap and 'usd' in self.total_market_cap:
            self.total_market_cap_usd = self.total_market_cap['usd']
        if self.total_volume and 'usd' in self.total_volume:
            self.total_volume_usd = self.total_volume['usd']
        if self.market_cap_percentage and 'btc' in self.market_cap_percentage:
            self.btc_dominance = self.market_cap_percentage['btc']

@dataclass
class SearchResult:
    """Search result for coin lookup."""
    id: str
    name: str
    symbol: str
    market_cap_rank: Optional[int] = None
    thumb: Optional[str] = None
    large: Optional[str] = None

@dataclass
class HistoricalPrice:
    """Historical price point."""
    timestamp: datetime
    price: float
    market_cap: Optional[float] = None
    volume: Optional[float] = None

@dataclass
class HistoricalData:
    """Historical data collection."""
    coin_id: str
    prices: List[HistoricalPrice]
    market_caps: List[HistoricalPrice]
    total_volumes: List[HistoricalPrice]

class TimeFrame(Enum):
    """Supported time frames for historical data."""
    HOUR_1 = "1h"
    HOUR_24 = "24h"
    DAY_7 = "7d"
    DAY_30 = "30d"
    DAY_90 = "90d"
    YEAR_1 = "1y"
    MAX = "max"

@dataclass
class ComparisonData:
    """Data for comparing multiple coins."""
    coins: List[CoinData]
    comparison_matrix: Dict[str, Dict[str, float]]
    correlation_data: Optional[Dict[str, Dict[str, float]]] = None

@dataclass
class MCPResponse:
    """Standard MCP response wrapper."""
    success: bool
    data: Any
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

@dataclass
class ChatContext:
    """Context for chat conversations."""
    user_id: str
    session_id: str
    message_history: List[Dict[str, str]]
    current_coins: List[str]
    analysis_preferences: Dict[str, Any]

@dataclass
class AnalysisQuery:
    """Query for crypto analysis."""
    query_type: str
    coins: List[str]
    timeframe: TimeFrame
    parameters: Dict[str, Any]

@dataclass
class AnalysisResult:
    """Result of crypto analysis."""
    query: AnalysisQuery
    data: Any
    insights: List[str]
    recommendations: List[str]
    visualizations: List[Dict[str, Any]]

@dataclass
class PlotData:
    """Data for creating visualizations."""
    plot_type: str
    data: Dict[str, Any]
    config: Dict[str, Any]
    title: str
    description: Optional[str] = None 