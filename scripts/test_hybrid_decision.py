"""Test complete hybrid decision flow"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ai_trader.ai.hybrid_decision import HybridDecisionEngine
from ai_trader.ai.llm_client import LLMClient
from ai_trader.config import config
from ai_trader.exchange import create_exchange_client


async def main():
    """Test hybrid decision with all components"""
    print("=" * 60)
    print("混合决策系统测试")
    print("=" * 60)
    print()

    # Create LLM client and engine
    llm_client = LLMClient()
    engine = HybridDecisionEngine(llm_client)

    # Create exchange client
    client = create_exchange_client()

    try:
        symbol = "BTC/USDT"
        print(f"分析交易对: {symbol}")
        print()

        # Step 1: Get market data
        print("Step 1: 获取市场数据...")
        ticker = await client.get_ticker(symbol)
        klines = await client.get_klines(symbol, "1h", 100)
        print(f"  ✓ 价格: ${ticker.last_price:,.2f}")
        print(f"  ✓ K线数: {len(klines)}")
        print()

        # Prepare market data with all required fields
        from ai_trader.models.market import MarketData
        from ai_trader.data.indicators import calculate_indicators

        # Calculate indicators
        indicators = calculate_indicators(klines)

        market_data = MarketData(
            symbol=symbol,
            current_price=ticker.last_price,
            klines=klines,
            interval="1h",
            indicators=indicators,
            high_24h=ticker.high_24h,
            low_24h=ticker.low_24h,
            change_24h=ticker.change_24h,
            volume_24h=ticker.volume_24h,
        )

        # Step 2: Get multi-timeframe data
        print("Step 2: 获取多时间框架数据...")
        from ai_trader.data.multi_timeframe import MultiTimeframeManager

        mtf_manager = MultiTimeframeManager(client)
        mtf_data = await mtf_manager.get_multi_timeframe_data(symbol)

        # Display timeframe data
        for interval, analysis in mtf_data.analyses.items():
            print(f"  ✓ {interval}: 趋势={analysis.trend.value}, 置信度={analysis.confidence:.2f}, MACD={analysis.macd_signal.value}")
        print(f"  ✓ 整体趋势: {mtf_data.overall_trend.value}")
        print(f"  ✓ Confluence: {mtf_data.confluence_score:.0%}")
        print(f"  ✓ 建议行动: {mtf_data.recommended_action}")
        print()

        # Step 3: Run decision engine
        print("Step 3: 执行混合决策...")
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
        print(f"支撑位: ${tech_result.support_levels[0]:.2f}" if tech_result.support_levels else "N/A")
        print(f"阻力位: ${tech_result.resistance_levels[0]:.2f}" if tech_result.resistance_levels else "N/A")
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
            print(f"入场价: ${decision.entry_price:.2f}" if decision.entry_price else "N/A")
            print(f"止损价: ${decision.stop_loss:.2f}" if decision.stop_loss else "N/A")
            print(f"止盈价: ${decision.take_profit:.2f}" if decision.take_profit else "N/A")
            if decision.stop_loss and decision.entry_price:
                risk_pct = abs(decision.entry_price - decision.stop_loss) / decision.entry_price * 100
                print(f"风险: {risk_pct:.2f}%")

        print("=" * 60)

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
