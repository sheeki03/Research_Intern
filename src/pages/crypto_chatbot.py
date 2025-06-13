"""
Crypto AI Chatbot Page

Interactive cryptocurrency analysis chatbot with MCP integration.
"""

import streamlit as st
import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Any

# Check MCP availability
try:
    from src.services.mcp.config import MCPConfig  # Fixed import path
    from src.services.mcp.coingecko_client import CoinGeckoMCPClient
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False

# Internal imports
from src.pages.base_page import BasePage
from src.controllers.chat_controller import ChatController

logger = logging.getLogger(__name__)

class CryptoChatbotPage(BasePage):
    """Crypto AI Assistant chatbot page."""
    
    def __init__(self):
        super().__init__("Crypto AI Assistant", "💰")
        self.title = "🪙 Crypto AI Assistant"
        self.controller = ChatController()
        
    async def render(self):
        """Render the crypto chatbot page."""
        self._render_header()
        self._render_chat_interface()
        self._render_analysis_panel()
        
    def _render_header(self):
        """Render page header with status."""
        st.markdown("""
        <div style="text-align: center; padding: 20px;">
            <h1>🪙 Crypto AI Assistant</h1>
            <p style="font-size: 18px; color: #666;">
                Your intelligent cryptocurrency analysis companion
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        # Connection status
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if MCP_AVAILABLE:
                # Check actual MCP connection status
                try:
                    if hasattr(self.controller, 'connected') and self.controller.connected:
                        st.success("🟢 MCP Server Connected")
                    elif hasattr(self.controller, 'client'):
                        st.info("🔵 MCP Available - REST Fallback Active")
                    else:
                        st.success("🟢 MCP Services Ready")
                except Exception:
                    st.info("🔵 MCP Available - REST Fallback Active")
            else:
                st.warning("🟡 Using REST API Mode (MCP dependencies pending)")
    
    def _render_chat_interface(self):
        """Render the main chat interface."""
        st.markdown("### 💬 Chat with Crypto AI")
        
        # Initialize chat history
        if "chat_history" not in st.session_state:
            st.session_state.chat_history = [
                {
                    "role": "assistant",
                    "content": "👋 Hello! I'm your Crypto AI Assistant. I can help you analyze cryptocurrencies, compare coins, and provide market insights. Try asking me about Bitcoin, trending coins, or any crypto analysis you need!",
                    "timestamp": datetime.now()
                }
            ]
        
        # Chat container
        chat_container = st.container()
        
        with chat_container:
            # Display chat history
            for message in st.session_state.chat_history:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])
                    if "data" in message:
                        self._render_message_data(message["data"])
        
        # Chat input
        if user_input := st.chat_input("Ask me about cryptocurrency..."):
            self._handle_user_message(user_input)
    
    def _handle_user_message(self, user_input: str):
        """Handle user message and generate response."""
        # Add user message to history
        st.session_state.chat_history.append({
            "role": "user",
            "content": user_input,
            "timestamp": datetime.now()
        })
        
        # Display user message
        with st.chat_message("user"):
            st.markdown(user_input)
        
        # Generate and display assistant response
        with st.chat_message("assistant"):
            with st.spinner("Analyzing..."):
                response = self._generate_response(user_input)
                st.markdown(response["content"])
                
                if "data" in response:
                    self._render_message_data(response["data"])
        
        # Add assistant response to history
        st.session_state.chat_history.append(response)
        
        # Auto-scroll to bottom (rerun to update display)
        st.rerun()
    
    def _generate_response(self, user_input: str) -> Dict[str, Any]:
        """Generate AI response to user input using ChatController."""
        try:
            # Get response from new deterministic controller
            mcp_response = self.controller.process_message(user_input)
            
            # Convert to legacy format for existing UI components
            return self._convert_mcp_response_to_legacy(mcp_response, user_input)
            
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return {
                "role": "assistant",
                "content": f"⚠️ I encountered an error processing your request: {str(e)}. Please try again.",
                "timestamp": datetime.now()
            }
    
    def _convert_mcp_response_to_legacy(self, mcp_response: Dict[str, Any], user_input: str) -> Dict[str, Any]:
        """Convert new MCP response format to legacy format for UI compatibility."""
        try:
            if not mcp_response.get("ok"):
                # Handle errors
                error = mcp_response.get("error", "Unknown error")
                if error == "unsupported_query":
                    hint = mcp_response.get("meta", {}).get("hint", "")
                    content = f"❓ **Unsupported Query**\n\nI couldn't understand your request. {hint}\n\n"
                    content += "**Try these examples:**\n"
                    content += "• 'Bitcoin price'\n"
                    content += "• 'trending coins'\n" 
                    content += "• 'search dogecoin'\n"
                    content += "• 'global market stats'\n"
                    content += "• 'historical Bitcoin data'\n"
                    content += "• 'coins above 5 billion FDV'"
                else:
                    content = f"⚠️ **Error:** {error}"
                
                return {
                    "role": "assistant",
                    "content": content,
                    "timestamp": datetime.now()
                }
            
            # Handle successful responses
            tool = mcp_response.get("tool")
            data = mcp_response.get("data", {})
            meta = mcp_response.get("meta", {})
            
            if tool == "get_coin_price":
                return self._format_coin_price_response(data, meta)
            elif tool == "get_trending_coins":
                return self._format_trending_response(data, meta)
            elif tool == "search_coins":
                return self._format_search_response(data, meta)
            elif tool == "get_market_overview":
                return self._format_market_overview_response(data, meta)
            elif tool == "get_historical_data":
                return self._format_historical_response(data, meta)
            elif tool == "ask":
                return self._format_ask_response(data, meta)
            else:
                return {
                    "role": "assistant", 
                    "content": f"✅ **Response from {tool}**\n\n{str(data)}",
                    "timestamp": datetime.now()
                }
                
        except Exception as e:
            logger.error(f"Error converting MCP response: {e}")
            return {
                "role": "assistant",
                "content": f"⚠️ Error processing response: {str(e)}",
                "timestamp": datetime.now()
            }
    
    def _format_coin_price_response(self, data: Dict[str, Any], meta: Dict[str, Any]) -> Dict[str, Any]:
        """Format coin price response for UI."""
        name = data.get("name", "Unknown")
        symbol = data.get("symbol", "").upper()
        price = data.get("price", 0)
        change_24h = data.get("change_24h", 0)
        market_cap = data.get("market_cap", 0)
        
        change_emoji = "🟢" if change_24h >= 0 else "🔴"
        content = f"💰 **{name} ({symbol})**\n\n"
        content += f"**Current Price:** ${price:,.4f}\n"
        content += f"**24h Change:** {change_emoji} {change_24h:+.2f}%\n"
        if market_cap:
            content += f"**Market Cap:** ${market_cap:,.0f}\n"
        
        latency = meta.get("latency_ms", 0)
        content += f"\n*Response time: {latency}ms*"
        
        return {
            "role": "assistant",
            "content": content,
            "timestamp": datetime.now(),
            "data": {
                "type": "coin_info",
                "coin": name,
                "symbol": symbol,
                "price": f"${price:,.4f}",
                "change_24h": f"{change_24h:+.2f}%",
                "market_cap": f"${market_cap:,.0f}" if market_cap else "N/A",
                "volume": "N/A"
            }
        }
    
    def _format_trending_response(self, data: Dict[str, Any], meta: Dict[str, Any]) -> Dict[str, Any]:
        """Format trending coins response for UI."""
        trending = data.get("trending", [])
        limit = data.get("limit", 10)
        
        content = f"🔥 **Top {len(trending)} Trending Coins**\n\n"
        
        for i, coin in enumerate(trending, 1):
            name = coin.get("name", "Unknown")
            symbol = coin.get("symbol", "").upper()
            rank = coin.get("market_cap_rank", "N/A")
            change = coin.get("price_change_percentage_24h", 0)
            
            change_emoji = "🟢" if change >= 0 else "🔴"
            content += f"**{i}. {name} ({symbol})**\n"
            content += f"   • Rank: #{rank}\n"
            content += f"   • 24h: {change_emoji} {change:+.2f}%\n\n"
        
        latency = meta.get("latency_ms", 0)
        content += f"*Response time: {latency}ms*"
        
        return {
            "role": "assistant",
            "content": content,
            "timestamp": datetime.now(),
            "data": {
                "type": "trending_list",
                "coins": [
                    {
                        "name": coin.get("name", "Unknown"),
                        "symbol": coin.get("symbol", "").upper(),
                        "rank": coin.get("market_cap_rank", "N/A"),
                        "change": f"{coin.get('price_change_percentage_24h', 0):+.2f}%"
                    }
                    for coin in trending
                ]
            }
        }
    
    def _format_search_response(self, data: Dict[str, Any], meta: Dict[str, Any]) -> Dict[str, Any]:
        """Format search results response for UI."""
        query = data.get("query", "")
        results = data.get("results", [])
        total = data.get("total_found", 0)
        
        content = f"🔍 **Search Results for '{query}'** ({total} found)\n\n"
        
        for i, coin in enumerate(results[:10], 1):  # Show top 10
            name = coin.get("name", "Unknown")
            symbol = coin.get("symbol", "").upper()
            rank = coin.get("market_cap_rank", "N/A")
            
            content += f"**{i}. {name} ({symbol})**\n"
            content += f"   • Market Cap Rank: #{rank}\n\n"
        
        latency = meta.get("latency_ms", 0)
        content += f"*Response time: {latency}ms*"
        
        return {
            "role": "assistant",
            "content": content,
            "timestamp": datetime.now()
        }
    
    def _format_market_overview_response(self, data: Dict[str, Any], meta: Dict[str, Any]) -> Dict[str, Any]:
        """Format market overview response for UI."""
        market_cap = data.get("total_market_cap_usd", 0)
        volume = data.get("total_volume_usd", 0)
        btc_dom = data.get("btc_dominance", 0)
        change_24h = data.get("market_cap_change_24h", 0)
        active_cryptos = data.get("active_cryptocurrencies", 0)
        
        content = f"📊 **Global Cryptocurrency Market**\n\n"
        content += f"💰 **Total Market Cap:** ${market_cap:,.0f}\n"
        content += f"📈 **24h Volume:** ${volume:,.0f}\n"
        content += f"🟠 **Bitcoin Dominance:** {btc_dom:.1f}%\n"
        
        if change_24h:
            change_emoji = "📈" if change_24h >= 0 else "📉"
            content += f"{change_emoji} **24h Change:** {change_24h:+.2f}%\n"
        
        content += f"🪙 **Active Cryptocurrencies:** {active_cryptos:,}\n"
        
        latency = meta.get("latency_ms", 0)
        content += f"\n*Response time: {latency}ms*"
        
        return {
            "role": "assistant",
            "content": content,
            "timestamp": datetime.now(),
            "data": {
                "type": "market_overview",
                "total_market_cap": f"${market_cap:,.0f}",
                "total_volume": f"${volume:,.0f}",
                "btc_dominance": f"{btc_dom:.1f}%",
                "eth_dominance": "N/A",  # Legacy compatibility
                "active_cryptos": f"{active_cryptos:,}",
                "market_sentiment": "Neutral"  # Legacy compatibility
            }
        }
    
    def _format_historical_response(self, data: Dict[str, Any], meta: Dict[str, Any]) -> Dict[str, Any]:
        """Format historical data response for UI."""
        coin_id = data.get("coin_id", "")
        days = data.get("days", 0)
        prices = data.get("prices", [])
        total_points = data.get("total_points", 0)
        
        if not prices:
            content = f"📈 **No historical data found for {coin_id}**"
        else:
            first_price = prices[0].get("price", 0)
            last_price = prices[-1].get("price", 0) if len(prices) > 1 else first_price
            
            if first_price > 0:
                change_pct = ((last_price - first_price) / first_price) * 100
            else:
                change_pct = 0
            
            content = f"📈 **{coin_id.title()} Historical Data ({days} days)**\n\n"
            content += f"**Starting Price:** ${first_price:,.4f}\n"
            content += f"**Latest Price:** ${last_price:,.4f}\n"
            content += f"**Period Change:** {change_pct:+.2f}%\n"
            content += f"**Data Points:** {total_points:,}\n"
        
        latency = meta.get("latency_ms", 0)
        content += f"\n*Response time: {latency}ms*"
        
        return {
            "role": "assistant",
            "content": content,
            "timestamp": datetime.now(),
            "data": {
                "type": "historical_data",
                "coin_id": coin_id,
                "days": days,
                "data": data  # Pass through for potential chart rendering
            }
        }
    
    def _format_ask_response(self, data: Dict[str, Any], meta: Dict[str, Any]) -> Dict[str, Any]:
        """Format MCP ask tool response for UI."""
        question = data.get("question", "")
        answer = data.get("answer", "")
        source = data.get("source", "mcp")
        
        # Ensure clean UTF-8 encoding and normalize text
        if isinstance(answer, str):
            # Normalize unicode characters that might cause display issues
            answer = answer.encode('utf-8', errors='replace').decode('utf-8')
            # Replace problematic unicode characters
            answer = answer.replace('\u2212', '-')  # Minus sign to hyphen
            answer = answer.replace('\u2022', '•')  # Bullet point normalization
        
        content = f"🤖 **AI Response**\n\n{answer}\n\n"
        content += f"*Source: {source}*"
        
        latency = meta.get("latency_ms", 0)
        content += f" | *Response time: {latency}ms*"
        
        return {
            "role": "assistant",
            "content": content,
            "timestamp": datetime.now(),
            "data": {
                "type": "natural_language_response",
                "source": source,
                "original_question": question
            }
        }
    
    def _render_message_data(self, data: Dict[str, Any]):
        """Render structured data from chat messages."""
        data_type = data.get("type", "")
        
        if data_type == "coin_info":
            self._render_coin_info(data)
        elif data_type == "trending_list":
            self._render_trending_list(data)
        elif data_type in ("comparison", "dynamic_comparison"):
            self._render_comparison(data)
        elif data_type == "price_list":
            self._render_price_list(data)
        elif data_type == "market_overview":
            self._render_market_overview(data)
        elif data_type == "chart_line":
            self._render_chart(data)
        elif data_type == "analysis_table":
            self._render_analysis_table(data)
        elif data_type == "enhanced_analysis":
            self._render_enhanced_analysis(data)
        elif data_type == "market_analysis":
            self._render_market_analysis(data)
        elif data_type == "market_overview":
            self._render_market_overview_data(data)
        elif data_type == "historical_data":
            self._render_historical_data(data)
        elif data_type == "natural_language_response":
            self._render_natural_language_response(data)
    
    def _render_coin_info(self, data: Dict[str, Any]):
        """Render individual coin information."""
        col1, col2 = st.columns(2)
        
        with col1:
            st.metric(
                label=f"{data['coin']} ({data['symbol']})",
                value=data['price'],
                delta=data['change_24h']
            )
        
        with col2:
            st.metric(
                label="Market Cap",
                value=data['market_cap']
            )
            st.metric(
                label="24h Volume", 
                value=data['volume']
            )
        
        if 'insights' in data:
            st.markdown("**💡 Key Insights:**")
            for insight in data['insights']:
                st.markdown(f"• {insight}")
    
    def _render_trending_list(self, data: Dict[str, Any]):
        """Render trending coins list."""
        for coin in data['coins']:
            col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
            with col1:
                st.write(f"**{coin['name']}** ({coin['symbol']})")
            with col2:
                st.write(f"#{coin['rank']}")
            with col3:
                st.write(coin['change'])
            with col4:
                st.button("📊", key=f"analyze_{coin['symbol']}", help=f"Analyze {coin['name']}")
    
    def _render_comparison(self, data: Dict[str, Any]):
        """Render coin comparison table (supports dynamic coins)."""
        st.markdown("**Comparison Table:**")

        coins = data.get('coins', [])
        metrics = data.get('metrics', [])

        # Header row
        header_cols = st.columns(len(coins) + 1)
        header_cols[0].write("**Metric**")
        for idx, coin_id in enumerate(coins):
            header_cols[idx + 1].write(f"**{coin_id.capitalize()}**")

        # Metric rows
        for metric in metrics:
            cols = st.columns(len(coins) + 1)
            cols[0].write(f"**{metric['metric']}**")
            for idx, coin_id in enumerate(coins):
                cols[idx + 1].write(metric.get(coin_id, "-"))
    
    def _render_price_list(self, data: Dict[str, Any]):
        """Render price list."""
        for price_info in data['prices']:
            col1, col2, col3 = st.columns([2, 1, 1])
            with col1:
                st.write(f"**{price_info['name']}** ({price_info['symbol']})")
            with col2:
                st.write(price_info['price'])
            with col3:
                change_color = "green" if price_info['change'].startswith('+') else "red"
                st.markdown(f"<span style='color: {change_color}'>{price_info['change']}</span>", 
                           unsafe_allow_html=True)
    
    def _render_market_overview(self, data: Dict[str, Any]):
        """Render market overview."""
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Total Market Cap", data['total_market_cap'])
            st.metric("BTC Dominance", data['btc_dominance'])
        
        with col2:
            st.metric("24h Volume", data['total_volume'])
            st.metric("ETH Dominance", data['eth_dominance'])
        
        with col3:
            st.metric("Active Cryptos", data['active_cryptos'])
            st.metric("Market Sentiment", data['market_sentiment'])
    
    def _render_chart(self, data: Dict[str, Any]):
        """Render Plotly chart from JSON."""
        import plotly.graph_objects as go
        import json as js
        fig_json = data.get('figure')
        if fig_json:
            fig = go.Figure(js.loads(fig_json))
            st.plotly_chart(fig, use_container_width=True)
    
    def _render_analysis_table(self, data: Dict[str, Any]):
        """Render technical analysis metrics table."""
        metrics = data.get('metrics', [])
        for row in metrics:
            col1, col2 = st.columns(2)
            col1.write(f"**{row['metric']}**")
            col2.write(row['value'])
    
    def _render_enhanced_analysis(self, data: Dict[str, Any]):
        """Render enhanced analysis with charts, metrics, and insights."""
        charts = data.get('charts', {})
        metrics = data.get('metrics', {})
        insights = data.get('insights', [])
        
        # Display charts if available
        if charts:
            st.markdown("### 📈 Interactive Charts")
            
            # Price chart with moving averages
            if 'price_chart' in charts:
                try:
                    st.plotly_chart(charts['price_chart'], use_container_width=True)
                except Exception as e:
                    st.error(f"Error displaying price chart: {e}")
            
            # RSI chart
            if 'rsi_chart' in charts:
                try:
                    st.plotly_chart(charts['rsi_chart'], use_container_width=True)
                except Exception as e:
                    st.error(f"Error displaying RSI chart: {e}")
        
        # Metrics summary in columns
        if metrics:
            st.markdown("### 📊 Technical Indicators")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if 'sma_7' in metrics:
                    st.metric("7-Day SMA", f"${metrics['sma_7']:,.2f}")
                if 'rsi_14' in metrics:
                    st.metric("RSI (14)", f"{metrics['rsi_14']:.1f}", 
                             help=f"Signal: {metrics.get('rsi_signal', 'N/A')}")
            
            with col2:
                if 'sma_14' in metrics:
                    st.metric("14-Day SMA", f"${metrics['sma_14']:,.2f}")
                if 'volatility_14' in metrics:
                    st.metric("Volatility (14d)", f"{metrics['volatility_14']:.2f}%")
            
            with col3:
                if 'performance_7d' in metrics and metrics['performance_7d'] is not None:
                    st.metric("7-Day Performance", f"{metrics['performance_7d']:+.2f}%",
                             delta=f"{metrics['performance_7d']:.2f}%")
                if 'performance_30d' in metrics and metrics['performance_30d'] is not None:
                    st.metric("30-Day Performance", f"{metrics['performance_30d']:+.2f}%")
        
        # Support/Resistance levels
        if 'price_min_30d' in metrics and 'price_max_30d' in metrics:
            st.markdown("### 🎯 Key Levels")
            col1, col2 = st.columns(2)
            with col1:
                st.metric("30-Day Support", f"${metrics['price_min_30d']:,.2f}")
            with col2:
                st.metric("30-Day Resistance", f"${metrics['price_max_30d']:,.2f}")
        
        # Analysis insights
        if insights:
            st.markdown("### 💡 Analysis Insights")
            for insight in insights:
                st.markdown(f"• {insight}")
        
        # Analysis metadata
        if data.get('date_range') or data.get('data_points'):
            st.markdown("---")
            st.caption(f"**Analysis Period:** {data.get('date_range', 'N/A')} | **Data Points:** {data.get('data_points', 0)}")
    
    def _render_market_analysis(self, data: Dict[str, Any]):
        """Render market analysis with sentiment and metrics."""
        sentiment = data.get('sentiment', 'Neutral')
        btc_change = data.get('btc_change', 0)
        eth_change = data.get('eth_change', 0)
        analysis_type = data.get('analysis_type', 'general_market')
        trending_coins = data.get('trending_coins', [])
        
        # Market sentiment indicator
        st.markdown("### 🎯 Market Sentiment")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            # Sentiment color coding
            if sentiment == "Bullish":
                sentiment_color = "🟢"
            elif sentiment == "Bearish":
                sentiment_color = "🔴"
            elif "Slightly" in sentiment:
                sentiment_color = "🟡"
            else:
                sentiment_color = "⚪"
            
            st.metric("Overall Sentiment", f"{sentiment_color} {sentiment}")
        
        with col2:
            delta_color = "normal" if btc_change > 0 else "inverse"
            st.metric("Bitcoin 24h", f"{btc_change:+.2f}%", delta=f"{btc_change:.2f}%", delta_color=delta_color)
        
        with col3:
            delta_color = "normal" if eth_change > 0 else "inverse"
            st.metric("Ethereum 24h", f"{eth_change:+.2f}%", delta=f"{eth_change:.2f}%", delta_color=delta_color)
        
        # Trending coins
        if trending_coins:
            st.markdown("### 🔥 Trending Now")
            trending_text = " • ".join(trending_coins)
            st.info(f"**Hot Topics:** {trending_text}")
        
        # Market analysis chart (simple sentiment visualization)
        st.markdown("### 📊 Market Overview")
        
        import plotly.graph_objects as go
        
        # Create a simple gauge chart for sentiment
        sentiment_score = 50  # Neutral baseline
        if sentiment == "Bullish":
            sentiment_score = 80
        elif sentiment == "Slightly Bullish":
            sentiment_score = 65
        elif sentiment == "Slightly Bearish":
            sentiment_score = 35
        elif sentiment == "Bearish":
            sentiment_score = 20
        
        fig = go.Figure(go.Indicator(
            mode = "gauge+number+delta",
            value = sentiment_score,
            domain = {'x': [0, 1], 'y': [0, 1]},
            title = {'text': "Market Sentiment Score"},
            delta = {'reference': 50},
            gauge = {
                'axis': {'range': [None, 100]},
                'bar': {'color': "darkblue"},
                'steps': [
                    {'range': [0, 25], 'color': "lightcoral"},
                    {'range': [25, 50], 'color': "lightyellow"},
                    {'range': [50, 75], 'color': "lightgreen"},
                    {'range': [75, 100], 'color': "green"}
                ],
                'threshold': {
                    'line': {'color': "red", 'width': 4},
                    'thickness': 0.75,
                    'value': 90
                }
            }
        ))
        
        fig.update_layout(height=300, font={'color': "white"}, paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width=True)
        
        # Quick action buttons
        st.markdown("### 🎯 Quick Actions")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            if st.button("📈 Analyze BTC", key="market_btc_analysis"):
                st.session_state.chat_history.append({
                    "role": "user",
                    "content": "analyze bitcoin",
                    "timestamp": datetime.now()
                })
                st.rerun()
        
        with col2:
            if st.button("🔷 Analyze ETH", key="market_eth_analysis"):
                st.session_state.chat_history.append({
                    "role": "user",
                    "content": "analyze ethereum", 
                    "timestamp": datetime.now()
                })
                st.rerun()
        
        with col3:
            if st.button("🔥 Trending", key="market_trending"):
                st.session_state.chat_history.append({
                    "role": "user",
                    "content": "show me trending coins",
                    "timestamp": datetime.now()
                })
                st.rerun()
        
        with col4:
            if st.button("⚖️ Compare", key="market_compare"):
                st.session_state.chat_history.append({
                    "role": "user",
                    "content": "compare bitcoin and ethereum",
                    "timestamp": datetime.now()
                })
                st.rerun()
    
    def _render_analysis_panel(self):
        """Render the analysis side panel."""
        with st.sidebar:
            st.markdown("### 📊 Quick Analysis")
            
            # Quick actions
            st.markdown("**Quick Actions:**")
            if st.button("🔥 Show Trending", use_container_width=True):
                self._handle_user_message("Show me trending coins")
            
            if st.button("🪙 Bitcoin Analysis", use_container_width=True):
                self._handle_user_message("Tell me about Bitcoin")
            
            if st.button("🔷 Ethereum Analysis", use_container_width=True):
                self._handle_user_message("Tell me about Ethereum")
            
            if st.button("🌍 Market Overview", use_container_width=True):
                self._handle_user_message("Show me market overview")
            
            # Settings
            st.markdown("---")
            st.markdown("### ⚙️ Settings")
            
            # Currency preference
            currency = st.selectbox("Currency", ["USD", "EUR", "GBP", "JPY"], index=0)
            
            # Update frequency
            update_freq = st.selectbox("Update Frequency", 
                                     ["Real-time", "1 minute", "5 minutes", "15 minutes"], 
                                     index=1)
            
            # Analysis depth
            analysis_depth = st.selectbox("Analysis Depth", 
                                        ["Basic", "Detailed", "Expert"], 
                                        index=1)
            
            # Chat history controls
            st.markdown("---")
            st.markdown("### 💬 Chat Controls")
            
            if st.button("🗑️ Clear Chat", use_container_width=True):
                st.session_state.chat_history = [
                    {
                        "role": "assistant",
                        "content": "Chat cleared! How can I help you with cryptocurrency analysis?",
                        "timestamp": datetime.now()
                    }
                ]
                st.rerun()
            
            # Export chat
            if st.button("📤 Export Chat", use_container_width=True):
                chat_export = json.dumps(st.session_state.chat_history, default=str, indent=2)
                st.download_button(
                    "Download Chat History",
                    chat_export,
                    "crypto_chat_history.json",
                    "application/json"
                )

    def _render_market_overview_data(self, data: Dict[str, Any]):
        """Render market overview data."""
        market_data = data.get('market_data')
        if not market_data:
            return
        
        # Create overview metrics
        col1, col2, col3, col4 = st.columns(4)
        
        total_market_cap_usd = market_data.total_market_cap.get('usd', 0)
        total_volume_usd = market_data.total_volume.get('usd', 0)
        btc_dominance = market_data.market_cap_percentage.get('btc', 0)
        change_24h = market_data.market_cap_change_percentage_24h_usd or 0
        
        with col1:
            st.metric(
                "Total Market Cap",
                f"${total_market_cap_usd:,.0f}",
                delta=f"{change_24h:+.2f}%" if change_24h else None
            )
        
        with col2:
            st.metric(
                "24h Volume",
                f"${total_volume_usd:,.0f}"
            )
        
        with col3:
            st.metric(
                "Bitcoin Dominance",
                f"{btc_dominance:.1f}%"
            )
        
        with col4:
            st.metric(
                "Active Coins",
                f"{market_data.active_cryptocurrencies:,}"
            )
    
    def _render_historical_data(self, data: Dict[str, Any]):
        """Render historical data with chart."""
        historical_data = data.get('data')
        coin_id = data.get('coin_id', 'Unknown')
        days = data.get('days', 7)
        
        if not historical_data or not historical_data.prices:
            st.warning("No historical data available")
            return
        
        # Prepare data for chart
        import pandas as pd
        
        chart_data = []
        for price in historical_data.prices:
            chart_data.append({
                'Date': price.timestamp,
                'Price': price.price
            })
        
        df = pd.DataFrame(chart_data)
        
        # Create line chart
        st.subheader(f"📈 {coin_id.title()} Price Chart ({days} days)")
        st.line_chart(df.set_index('Date')['Price'])
        
        # Show key metrics
        col1, col2, col3 = st.columns(3)
        
        prices = [p.price for p in historical_data.prices]
        
        with col1:
            st.metric("Highest Price", f"${max(prices):,.2f}")
        
        with col2:
            st.metric("Lowest Price", f"${min(prices):,.2f}")
        
        with col3:
            change_pct = data.get('price_change_percentage', 0)
            st.metric("Period Change", f"{change_pct:+.2f}%")
    
    def _render_natural_language_response(self, data: Dict[str, Any]):
        """Render natural language response with source info."""
        source = data.get('source', 'unknown')
        original_question = data.get('original_question', '')
        
        # Show source indicator
        if source == "mcp":
            st.info("🤖 Response powered by MCP AI analysis")
        elif source == "rest_api":
            st.info("📊 Response based on real-time data analysis")
        else:
            st.info("💡 General response")
        
        # Show original question if different
        if original_question:
            with st.expander("📝 Original Question"):
                st.write(original_question)

def main():
    """Main function to run the crypto chatbot page."""
    page = CryptoChatbotPage()
    page.render()

if __name__ == "__main__":
    main() 