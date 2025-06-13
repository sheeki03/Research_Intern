import asyncio
import logging
from typing import List, Dict, Any

from src.services.mcp.coingecko_client import CoinGeckoMCPClient
from src.services.mcp.models import PriceData, ComparisonData, CoinData

logger = logging.getLogger(__name__)

class ComparisonService:
    """Service to compare multiple cryptocurrencies using the MCP/REST client."""

    def __init__(self):
        self.client = CoinGeckoMCPClient()
        self.connected = False

    async def _ensure_connection(self):
        if not self.connected:
            self.connected = await self.client.connect()

    async def compare(self, coin_ids: List[str]) -> Dict[str, Any]:
        """Compare multiple coins and return metrics suitable for UI table."""
        await self._ensure_connection()

        # Fetch price data for each coin
        prices: Dict[str, PriceData] = {}
        for cid in coin_ids:
            try:
                prices[cid] = await self.client.get_coin_price(cid)
            except Exception as e:
                logger.warning(f"Failed to fetch price for {cid}: {e}")

        # Build metrics
        rows = []
        metrics = [
            ("Price", lambda p: f"${p.current_price:,.2f}"),
            ("24h Change", lambda p: f"{p.price_change_percentage_24h:+.2f}%" if p.price_change_percentage_24h is not None else "N/A"),
            ("Market Cap", lambda p: f"${p.market_cap:,.0f}" if p.market_cap else "N/A"),
            ("24h Volume", lambda p: f"${p.volume_24h:,.0f}" if p.volume_24h else "N/A"),
        ]

        comparison_metrics = []
        for metric_name, fn in metrics:
            row = {"metric": metric_name}
            for cid, pdata in prices.items():
                row[cid] = fn(pdata)
            comparison_metrics.append(row)

        return {
            "coins": list(prices.keys()),
            "metrics": comparison_metrics,
        } 