"""Test complete hybrid decision flow with mock data (offline)"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ai_trader.ai.hybrid_decision import HybridDecisionEngine
from ai_trader.ai.llm_client import LLMClient
from ai_trader.models.market import MarketData, Kline, Indicators
from ai_trader.data.multi_timeframe import (
    MultiTimeframeData,
    TimeframeAnalysis,
    TrendDirection,
    MACDSignal,
)


def create_mock_klines(count: int = 100, start_price: float = 88000.0) -> list[Kline]:
    """Create mock kline data"""
    klines = []
    now = datetime.now()

    for i in range(count):
        timestamp = now - timedelta(hours=count - i)
        price = start_price + (i - count // 2) * 100  # Trending price

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


def create_mock_indicators() -> Indicators:
    """Create mock technical indicators"""
    return Indicators(
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


def create_mock_mtf_data(symbol: str) -> MultiTimeframeData:
    """Create mock multi-timeframe data"""
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
        "4h": TimeframeAnalysis(
            interval="4h",
            trend=TrendDirection.UPTREND,
            ma_alignment=True,
            macd_signal=MACDSignal.BULLISH,
            support_levels=[86500.0, 85500.0],
            resistance_levels=[89000.0, 90000.0],
            confidence=0.85,
            current_price=87800.0,
            atr=650.0,
        ),
    }

    return MultiTimeframeData(
        symbol=symbol,
        analyses=analyses,
        overall_trend=TrendDirection.UPTREND,
        confluence_score=0.70,
        recommended_action="open_long",
    )


async def main():
    """Test hybrid decision with mock data"""
    print("=" * 60)
    print("混合决策系统测试 (离线模拟数据)")
    print("=" * 60)
    print()

    # Create LLM client and engine
    llm_client = LLMClient()
    engine = HybridDecisionEngine(llm_client)

    symbol = "BTC/USDT"
    print(f"分析交易对: {symbol}")
    print()

    # Step 1: Create mock market data
    print("Step 1: 创建模拟市场数据...")
    klines = create_mock_klines(100, 87800.0)
    indicators = create_mock_indicators()

    market_data = MarketData(
        symbol=symbol,
        current_price=87800.0,
        klines=klines,
        interval="1h",
        indicators=indicators,
        high_24h=88500.0,
        low_24h=86900.0,
        change_24h=1.2,
        volume_24h=15000000000.0,
    )

    print(f"  ✓ 价格: ${market_data.current_price:,.2f}")
    print(f"  ✓ K线数: {len(klines)}")
    print(f"  ✓ 24h变化: {market_data.change_24h:+.2f}%")
    print()

    # Step 2: Create mock multi-timeframe data
    print("Step 2: 创建多时间框架数据...")
    mtf_data = create_mock_mtf_data(symbol)

    for interval, analysis in mtf_data.analyses.items():
        print(
            f"  ✓ {interval}: 趋势={analysis.trend.value}, "
            f"置信度={analysis.confidence:.2f}, MACD={analysis.macd_signal.value}"
        )
    print(f"  ✓ 整体趋势: {mtf_data.overall_trend.value}")
    print(f"  ✓ Confluence: {mtf_data.confluence_score:.0%}")
    print(f"  ✓ 建议行动: {mtf_data.recommended_action}")
    print()

    # Step 3: Run decision engine
    print("Step 3: 执行混合决策...")
    try:
        decision, tech_result, risk_result = await engine.analyze_and_decide(
            market_data=market_data,
            current_position=None,  # No position
            available_balance=10000.0,  # $10,000 USDT
            total_equity=10000.0,
            mtf_data=mtf_data,
            daily_pnl=0.0,
            trades_today=0,
            consecutive_losses=0,
            emotional_state="calm",
        )

        # Display results
        print()
        print("=" * 60)
        print("决策结果")
        print("=" * 60)
        print(f"行动: {decision.action}")
        print(f"置信度: {decision.final_confidence:.2%}")
        print(f"最终评分: {decision.final_score:.2f}")
        print()

        print("--- 技术分析 ---")
        print(f"趋势: {tech_result.trend}")
        if tech_result.support_levels:
            print(f"支撑位: ${tech_result.support_levels[0]:.2f}")
        if tech_result.resistance_levels:
            print(f"阻力位: ${tech_result.resistance_levels[0]:.2f}")
        print()

        print("--- 组件评分 ---")
        print(f"AI 评分: {decision.ai_score:.2f} (置信度: {decision.ai_confidence:.2%})")
        print(f"量化评分: {decision.quant_score:.2f} (置信度: {decision.quant_confidence:.2%})")

        if decision.sentiment_result:
            print(f"情绪: {decision.sentiment_result.score.name}")
            print(f"  - 置信度: {decision.sentiment_result.confidence:.2%}")
            print(f"  - 新闻数: {decision.sentiment_result.news_count}")
            print(f"  - 调整值: {decision.sentiment_result.get_sentiment_adjustment():.2f}")
            print(f"  - 极端恐慌: {decision.sentiment_result.extreme_fear}")
            print(f"  - 极端贪婪: {decision.sentiment_result.extreme_greed}")
        else:
            print("情绪: 未启用或无数据")
        print()

        print("--- 风险评估 ---")
        print(f"风险等级: {risk_result.risk_level}")
        print(f"最大仓位: {risk_result.max_position_size:.4f} BTC")
        print(f"建议杠杆: {risk_result.recommended_leverage}x")
        print()

        print("--- Confluence ---")
        print(f"多时间框架共振: {mtf_data.confluence_score:.0f}%")
        print()

        if decision.action in ["open_long", "open_short"]:
            print("--- 交易参数 ---")
            if decision.entry_price:
                print(f"入场价: ${decision.entry_price:.2f}")
            if decision.stop_loss:
                print(f"止损价: ${decision.stop_loss:.2f}")
            if decision.take_profit:
                print(f"止盈价: ${decision.take_profit:.2f}")
            if decision.stop_loss and decision.entry_price:
                risk_pct = abs(decision.entry_price - decision.stop_loss) / decision.entry_price * 100
                print(f"风险: {risk_pct:.2f}%")

        print("=" * 60)
        print()
        print("✅ 测试完成！混合决策系统工作正常。")

    except Exception as e:
        print(f"❌ 决策失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
