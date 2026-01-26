"""Test multi-timeframe analysis with mock data"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ai_trader.data.multi_timeframe import (
    MultiTimeframeManager,
    TimeframeAnalysis,
    TrendDirection,
    MACDSignal,
)
from ai_trader.models.market import Indicators, Kline, MarketData
from unittest.mock import AsyncMock, MagicMock


def create_mock_market_data(symbol: str, interval: str, trend: str = "uptrend") -> MarketData:
    """Create mock market data for testing"""

    # Create mock indicators based on trend
    if trend == "uptrend":
        indicators = Indicators(
            ma7=60500.0,
            ma25=60000.0,
            ma99=59500.0,
            rsi=65.0,
            macd=100.0,
            macd_signal=80.0,
            macd_histogram=20.0,
            boll_upper=61000.0,
            boll_middle=60000.0,
            boll_lower=59000.0,
            atr=500.0,
        )
        current_price = 60600.0
    elif trend == "downtrend":
        indicators = Indicators(
            ma7=59500.0,
            ma25=60000.0,
            ma99=60500.0,
            rsi=35.0,
            macd=-100.0,
            macd_signal=-80.0,
            macd_histogram=-20.0,
            boll_upper=61000.0,
            boll_middle=60000.0,
            boll_lower=59000.0,
            atr=500.0,
        )
        current_price = 59400.0
    else:  # sideways
        indicators = Indicators(
            ma7=60000.0,
            ma25=60000.0,
            ma99=60000.0,
            rsi=50.0,
            macd=0.0,
            macd_signal=0.0,
            macd_histogram=0.0,
            boll_upper=61000.0,
            boll_middle=60000.0,
            boll_lower=59000.0,
            atr=300.0,
        )
        current_price = 60000.0

    # Create mock klines
    klines = []
    for i in range(50):
        kline = Kline(
            timestamp=1700000000 + i * 900000,  # 15 min intervals
            open=current_price - 100 + (i % 10) * 20,
            high=current_price + 50,
            low=current_price - 50,
            close=current_price,
            volume=1000.0 + i * 10,
        )
        klines.append(kline)

    return MarketData(
        symbol=symbol,
        current_price=current_price,
        klines=klines,
        interval=interval,
        indicators=indicators,
        high_24h=current_price + 500,
        low_24h=current_price - 500,
        change_24h=1.5,
        volume_24h=1000000.0,
    )


async def test_multi_timeframe():
    """Test multi-timeframe analysis with mock data"""
    print("=" * 60)
    print("🧪 Testing Multi-Timeframe Analysis (Mock Data)")
    print("=" * 60)

    # Create mock exchange client
    mock_client = MagicMock()

    # Create MultiTimeframeManager
    mtf_manager = MultiTimeframeManager(mock_client)

    # Override market data manager to return mock data
    async def mock_get_market_data(symbol, interval, limit):
        # Simulate different trends for different timeframes
        if interval == "15m":
            return create_mock_market_data(symbol, interval, "uptrend")
        elif interval == "1h":
            return create_mock_market_data(symbol, interval, "uptrend")
        elif interval == "4h":
            return create_mock_market_data(symbol, interval, "sideways")
        else:
            return create_mock_market_data(symbol, interval, "uptrend")

    mtf_manager.market_mgr.get_market_data = mock_get_market_data

    # Test with day trading timeframes
    print("\n📊 Testing Day Trading Timeframes (15m, 1h, 4h)...")
    mtf_data = await mtf_manager.get_multi_timeframe_data(
        symbol="BTCUSDT",
        timeframes=["15m", "1h", "4h"],
        limit=100,
    )

    if mtf_data:
        print(f"✅ Multi-timeframe analysis completed!")
        print(f"\n📈 Overall Analysis:")
        print(f"  Symbol: {mtf_data.symbol}")
        print(f"  Overall Trend: {mtf_data.overall_trend.value.upper()}")
        print(f"  Confluence Score: {mtf_data.confluence_score:.2%}")
        print(f"  Recommended Action: {mtf_data.recommended_action.upper()}")

        print(f"\n📊 Individual Timeframe Analysis:")
        for interval, analysis in mtf_data.analyses.items():
            print(f"\n  ⏱️  {interval}:")
            print(f"    Trend: {analysis.trend.value}")
            print(f"    MA Alignment: {'✅' if analysis.ma_alignment else '❌'}")
            print(f"    MACD Signal: {analysis.macd_signal.value}")
            print(f"    Confidence: {analysis.confidence:.0%}")
            print(f"    Current Price: {analysis.current_price:.2f} USDT")
            print(f"    ATR: {analysis.atr:.2f}")

            if analysis.support_levels:
                print(f"    Support Levels: {', '.join(f'{s:.2f}' for s in analysis.support_levels[:3])}")
            if analysis.resistance_levels:
                print(f"    Resistance Levels: {', '.join(f'{r:.2f}' for r in analysis.resistance_levels[:3])}")

        # Interpretation
        print(f"\n💡 Interpretation:")
        if mtf_data.confluence_score >= 0.7:
            print(f"  🟢 HIGH confluence - Strong signal quality")
        elif mtf_data.confluence_score >= 0.5:
            print(f"  🟡 MEDIUM confluence - Moderate signal quality")
        else:
            print(f"  🔴 LOW confluence - Conflicting signals, avoid trading")

        if mtf_data.recommended_action == "buy":
            print(f"  📈 BUY signal - All timeframes align for uptrend")
        elif mtf_data.recommended_action == "sell":
            print(f"  📉 SELL signal - All timeframes align for downtrend")
        else:
            print(f"  ⏸️  HOLD - Wait for better setup")

    else:
        print("❌ Multi-timeframe analysis failed")

    print("\n" + "=" * 60)
    print("✅ Multi-Timeframe Analysis Test Completed")
    print("=" * 60)


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_multi_timeframe())
