"""Test individual decision components without network calls"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ai_trader.models.market import MarketData, Kline, Indicators
from ai_trader.data.multi_timeframe import (
    MultiTimeframeData,
    TimeframeAnalysis,
    TrendDirection,
    MACDSignal,
)
from ai_trader.config import config


def create_mock_klines(count: int = 100, start_price: float = 88000.0) -> list[Kline]:
    """Create mock kline data"""
    klines = []
    now = datetime.now()

    for i in range(count):
        timestamp = now - timedelta(hours=count - i)
        price = start_price + (i - count // 2) * 100

        klines.append(
            Kline(
                timestamp=int(timestamp.timestamp() * 1000),
                open=price - 50,
                high=price + 100,
                low=price - 100,
                close=price,
                volume=1000000.0 + i * 10000,
            )
        )

    return klines


def test_market_data():
    """Test MarketData creation"""
    print("Testing MarketData creation...")

    klines = create_mock_klines(100, 87800.0)

    indicators = Indicators(
        ma7=87800.0,
        ma25=87500.0,
        ma99=86900.0,
        rsi=55.0,
        macd=120.0,
        macd_signal=100.0,
        macd_histogram=20.0,
        boll_upper=88500.0,
        boll_middle=87800.0,
        boll_lower=87100.0,
        atr=450.0,
    )

    market_data = MarketData(
        symbol="BTC/USDT",
        current_price=87800.0,
        klines=klines,
        interval="1h",
        indicators=indicators,
        high_24h=88500.0,
        low_24h=86900.0,
        change_24h=1.2,
        volume_24h=15000000000.0,
    )

    print(f"  ✓ Symbol: {market_data.symbol}")
    print(f"  ✓ Price: ${market_data.current_price:,.2f}")
    print(f"  ✓ K线数: {len(market_data.klines)}")
    print(f"  ✓ RSI: {market_data.indicators.rsi}")
    print()


def test_multi_timeframe_data():
    """Test MultiTimeframeData creation"""
    print("Testing MultiTimeframeData creation...")

    analyses = {
        "15m": TimeframeAnalysis(
            interval="15m",
            trend=TrendDirection.SIDEWAYS,
            ma_alignment=False,
            macd_signal=MACDSignal.BEARISH,
            support_levels=[87000.0, 86500.0],
            resistance_levels=[88000.0, 88500.0],
            confidence=0.50,
            current_price=87800.0,
            atr=300.0,
        ),
        "1h": TimeframeAnalysis(
            interval="1h",
            trend=TrendDirection.UPTREND,
            ma_alignment=True,
            macd_signal=MACDSignal.BULLISH,
            support_levels=[87200.0, 86800.0],
            resistance_levels=[88200.0, 88800.0],
            confidence=0.75,
            current_price=87800.0,
            atr=450.0,
        ),
    }

    mtf_data = MultiTimeframeData(
        symbol="BTC/USDT",
        analyses=analyses,
        overall_trend=TrendDirection.UPTREND,
        confluence_score=0.70,
        recommended_action="open_long",
    )

    print(f"  ✓ Symbol: {mtf_data.symbol}")
    print(f"  ✓ 时间框架数: {len(mtf_data.analyses)}")
    print(f"  ✓ 整体趋势: {mtf_data.overall_trend.value}")
    print(f"  ✓ Confluence: {mtf_data.confluence_score:.0%}")
    print(f"  ✓ 建议: {mtf_data.recommended_action}")
    print()


def test_config():
    """Test configuration"""
    print("Testing configuration...")
    print(f"  ✓ LLM Provider: {config.llm_provider}")
    print(f"  ✓ LLM Model: {config.llm_model}")
    print(f"  ✓ Trading Mode: {config.trading_mode}")
    print(f"  ✓ 情绪分析启用: {config.enable_sentiment_analysis}")
    print(f"  ✓ 量化策略启用: {config.enable_quant_strategies}")
    print(f"  ✓ AI权重: {config.ai_weight}")
    print(f"  ✓ 量化权重: {config.quant_weight}")
    print()


def main():
    print("=" * 60)
    print("组件测试")
    print("=" * 60)
    print()

    try:
        test_config()
        test_market_data()
        test_multi_timeframe_data()

        print("=" * 60)
        print("✅ 所有组件测试通过！")
        print("=" * 60)

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
