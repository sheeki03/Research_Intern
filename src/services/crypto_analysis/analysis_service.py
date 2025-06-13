import asyncio
import logging
from typing import Dict, Any, List
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta

from src.services.mcp.coingecko_client import CoinGeckoMCPClient
from src.services.mcp.models import HistoricalData, HistoricalPrice

logger = logging.getLogger(__name__)

class AnalysisService:
    """Provide common technical analysis metrics using historical price data."""

    def __init__(self):
        self.client = CoinGeckoMCPClient()
        self.connected = False

    async def _ensure_connection(self):
        if not self.connected:
            self.connected = await self.client.connect()

    async def analyze(self, coin_id: str, days: int = 30) -> Dict[str, Any]:
        """Return comprehensive analysis with charts, metrics, and insights."""
        await self._ensure_connection()
        hist: HistoricalData = await self.client.get_historical_data(coin_id, days)

        # Build pandas DataFrame
        df = pd.DataFrame([
            {
                'timestamp': p.timestamp,
                'price': p.price
            } for p in hist.prices
        ])
        
        prices = df['price']
        timestamps = df['timestamp']

        # Calculate technical indicators
        metrics = self._calculate_technical_indicators(prices)
        
        # Generate charts
        charts = self._generate_charts(df, coin_id, metrics)
        
        # Generate insights
        insights = self._generate_insights(metrics, prices)
        
        return {
            'metrics': metrics,
            'charts': charts,
            'insights': insights,
            'data_points': len(hist.prices),
            'date_range': f"{timestamps.iloc[0].strftime('%Y-%m-%d')} to {timestamps.iloc[-1].strftime('%Y-%m-%d')}"
        }
    
    def _calculate_technical_indicators(self, prices: pd.Series) -> Dict[str, Any]:
        """Calculate various technical analysis indicators."""
        metrics = {}
        
        try:
            # Moving Averages
            metrics['sma_7'] = prices.rolling(window=7).mean().iloc[-1]
            metrics['sma_14'] = prices.rolling(window=14).mean().iloc[-1]
            metrics['sma_30'] = prices.rolling(window=min(30, len(prices))).mean().iloc[-1]
            
            # Current price vs moving averages
            current_price = prices.iloc[-1]
            metrics['price_vs_sma_7'] = ((current_price - metrics['sma_7']) / metrics['sma_7']) * 100
            metrics['price_vs_sma_14'] = ((current_price - metrics['sma_14']) / metrics['sma_14']) * 100
            
        except Exception as e:
            logger.warning(f"SMA calc error: {e}")

        try:
            # RSI (Relative Strength Index)
            delta = prices.diff()
            up, down = delta.clip(lower=0), -delta.clip(upper=0)
            roll_up = up.rolling(14).mean()
            roll_down = down.rolling(14).mean()
            rs = roll_up / roll_down
            rsi = 100 - (100 / (1 + rs))
            metrics['rsi_14'] = rsi.iloc[-1]
            
            # RSI interpretation
            if metrics['rsi_14'] > 70:
                metrics['rsi_signal'] = "Overbought"
            elif metrics['rsi_14'] < 30:
                metrics['rsi_signal'] = "Oversold"
            else:
                metrics['rsi_signal'] = "Neutral"
                
        except Exception as e:
            logger.warning(f"RSI calc error: {e}")

        try:
            # Volatility
            metrics['volatility_14'] = prices.pct_change().rolling(14).std().iloc[-1] * 100
            
            # Price performance
            metrics['performance_7d'] = ((prices.iloc[-1] - prices.iloc[-7]) / prices.iloc[-7]) * 100 if len(prices) >= 7 else None
            metrics['performance_14d'] = ((prices.iloc[-1] - prices.iloc[-14]) / prices.iloc[-14]) * 100 if len(prices) >= 14 else None
            metrics['performance_30d'] = ((prices.iloc[-1] - prices.iloc[-30]) / prices.iloc[-30]) * 100 if len(prices) >= 30 else None
            
            # Support and Resistance (simple)
            metrics['price_min_30d'] = prices.tail(min(30, len(prices))).min()
            metrics['price_max_30d'] = prices.tail(min(30, len(prices))).max()
            
        except Exception as e:
            logger.warning(f"Performance calc error: {e}")

        return metrics
    
    def _generate_charts(self, df: pd.DataFrame, coin_id: str, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Generate interactive charts for the analysis."""
        charts = {}
        
        try:
            # Price chart with moving averages
            fig_price = go.Figure()
            
            # Add price line
            fig_price.add_trace(go.Scatter(
                x=df['timestamp'],
                y=df['price'],
                name='Price',
                line=dict(color='#00d4aa', width=2)
            ))
            
            # Add moving averages if available
            if 'sma_7' in metrics and len(df) >= 7:
                sma_7 = df['price'].rolling(window=7).mean()
                fig_price.add_trace(go.Scatter(
                    x=df['timestamp'],
                    y=sma_7,
                    name='SMA 7',
                    line=dict(color='#ff6b6b', width=1, dash='dash')
                ))
            
            if 'sma_14' in metrics and len(df) >= 14:
                sma_14 = df['price'].rolling(window=14).mean()
                fig_price.add_trace(go.Scatter(
                    x=df['timestamp'],
                    y=sma_14,
                    name='SMA 14',
                    line=dict(color='#4ecdc4', width=1, dash='dot')
                ))
            
            fig_price.update_layout(
                title=f'{coin_id.title()} Price Analysis',
                xaxis_title='Date',
                yaxis_title='Price (USD)',
                template='plotly_dark',
                height=400
            )
            
            charts['price_chart'] = fig_price
            
            # RSI Chart
            if 'rsi_14' in metrics:
                rsi_values = []
                prices = df['price']
                delta = prices.diff()
                up, down = delta.clip(lower=0), -delta.clip(upper=0)
                roll_up = up.rolling(14).mean()
                roll_down = down.rolling(14).mean()
                rs = roll_up / roll_down
                rsi_series = 100 - (100 / (1 + rs))
                
                fig_rsi = go.Figure()
                fig_rsi.add_trace(go.Scatter(
                    x=df['timestamp'][14:],  # Skip first 14 days for RSI
                    y=rsi_series[14:],
                    name='RSI (14)',
                    line=dict(color='#feca57')
                ))
                
                # Add overbought/oversold lines
                fig_rsi.add_hline(y=70, line_dash="dash", line_color="red", annotation_text="Overbought (70)")
                fig_rsi.add_hline(y=30, line_dash="dash", line_color="green", annotation_text="Oversold (30)")
                
                fig_rsi.update_layout(
                    title='RSI (Relative Strength Index)',
                    xaxis_title='Date',
                    yaxis_title='RSI',
                    template='plotly_dark',
                    height=300,
                    yaxis=dict(range=[0, 100])
                )
                
                charts['rsi_chart'] = fig_rsi
            
        except Exception as e:
            logger.error(f"Chart generation error: {e}")
            charts['error'] = str(e)
        
        return charts
    
    def _generate_insights(self, metrics: Dict[str, Any], prices: pd.Series) -> List[str]:
        """Generate actionable insights based on analysis."""
        insights = []
        
        try:
            current_price = prices.iloc[-1]
            
            # Price trend insights
            if 'price_vs_sma_7' in metrics:
                if metrics['price_vs_sma_7'] > 2:
                    insights.append(f"📈 Price is {metrics['price_vs_sma_7']:.1f}% above 7-day average - strong upward momentum")
                elif metrics['price_vs_sma_7'] < -2:
                    insights.append(f"📉 Price is {abs(metrics['price_vs_sma_7']):.1f}% below 7-day average - bearish trend")
                else:
                    insights.append("🔄 Price is trading near 7-day average - sideways movement")
            
            # RSI insights
            if 'rsi_14' in metrics:
                rsi = metrics['rsi_14']
                if rsi > 70:
                    insights.append(f"⚠️ RSI at {rsi:.1f} indicates overbought conditions - potential correction ahead")
                elif rsi < 30:
                    insights.append(f"💡 RSI at {rsi:.1f} suggests oversold conditions - potential buying opportunity")
                else:
                    insights.append(f"✅ RSI at {rsi:.1f} shows balanced momentum")
            
            # Volatility insights
            if 'volatility_14' in metrics:
                vol = metrics['volatility_14']
                if vol > 5:
                    insights.append(f"🌊 High volatility ({vol:.1f}%) - expect significant price swings")
                elif vol < 2:
                    insights.append(f"😴 Low volatility ({vol:.1f}%) - price is consolidating")
                else:
                    insights.append(f"📊 Moderate volatility ({vol:.1f}%) - normal price movement")
            
            # Performance insights
            if 'performance_7d' in metrics and metrics['performance_7d'] is not None:
                perf_7d = metrics['performance_7d']
                if perf_7d > 10:
                    insights.append(f"🚀 Exceptional 7-day performance: +{perf_7d:.1f}%")
                elif perf_7d > 5:
                    insights.append(f"📈 Strong 7-day performance: +{perf_7d:.1f}%")
                elif perf_7d < -10:
                    insights.append(f"⚠️ Significant 7-day decline: {perf_7d:.1f}%")
                elif perf_7d < -5:
                    insights.append(f"📉 Weak 7-day performance: {perf_7d:.1f}%")
            
            # Support/Resistance insights
            if 'price_min_30d' in metrics and 'price_max_30d' in metrics:
                price_range = metrics['price_max_30d'] - metrics['price_min_30d']
                current_position = (current_price - metrics['price_min_30d']) / price_range
                
                if current_position > 0.8:
                    insights.append(f"🔝 Price near 30-day high (${metrics['price_max_30d']:,.2f}) - testing resistance")
                elif current_position < 0.2:
                    insights.append(f"🔻 Price near 30-day low (${metrics['price_min_30d']:,.2f}) - testing support")
                
        except Exception as e:
            logger.error(f"Insights generation error: {e}")
            insights.append("⚠️ Unable to generate full insights due to limited data")
        
        return insights 