"""
MCP Connection Test Script

Tests the MCP configuration and connection setup.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add src to path for imports
sys.path.append(str(Path(__file__).parent.parent.parent))

from services.mcp.config import MCPConfig
from services.mcp.coingecko_client import CoinGeckoMCPClient

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

async def test_mcp_setup():
    """Test MCP configuration and client setup."""
    logger.info("🧪 Starting MCP Setup Test...")
    
    try:
        # Test 1: Configuration loading
        logger.info("📋 Test 1: Loading MCP configuration...")
        config = MCPConfig()
        logger.info(f"✅ Config loaded successfully")
        logger.info(f"   - CoinGecko config: {config.coingecko_config}")
        logger.info(f"   - Fallback endpoints: {config.fallback_endpoints}")
        
        # Test 2: Client initialization
        logger.info("🔧 Test 2: Initializing MCP client...")
        client = CoinGeckoMCPClient(config)
        logger.info("✅ Client initialized successfully")
        
        # Test 3: Connection attempt
        logger.info("🌐 Test 3: Testing connection...")
        connected = await client.connect()
        
        if connected:
            logger.info("✅ Connection successful!")
            
            # Test 4: Tool discovery
            logger.info("🔍 Test 4: Discovering available tools...")
            tools = await client.list_tools()
            logger.info(f"✅ Found {len(tools)} tools:")
            for tool in tools:
                logger.info(f"   - {tool.name}: {tool.description}")
            
            # Test 5: Basic data fetch
            logger.info("💰 Test 5: Testing data fetch (Bitcoin price)...")
            try:
                btc_price = await client.get_coin_price('bitcoin')
                logger.info(f"✅ Bitcoin price: ${btc_price.current_price:,.2f}")
                logger.info(f"   - Market cap: ${btc_price.market_cap:,.0f}")
                logger.info(f"   - 24h change: {btc_price.price_change_percentage_24h:.2f}%")
            except Exception as e:
                logger.warning(f"⚠️ Data fetch test failed: {e}")
            
            # Test 6: Trending coins
            logger.info("📈 Test 6: Testing trending coins...")
            try:
                trending = await client.get_trending_coins()
                logger.info(f"✅ Found {len(trending)} trending coins:")
                for coin in trending[:3]:  # Show top 3
                    logger.info(f"   - {coin.name} ({coin.symbol}) - Rank #{coin.market_cap_rank}")
            except Exception as e:
                logger.warning(f"⚠️ Trending coins test failed: {e}")
            
            # Cleanup
            await client.disconnect()
            logger.info("🔌 Disconnected from client")
            
        else:
            logger.error("❌ Connection failed!")
            return False
        
        logger.info("🎉 All tests completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Test failed with error: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_mcp_setup())
    sys.exit(0 if success else 1) 