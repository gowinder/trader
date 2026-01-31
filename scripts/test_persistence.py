"""测试决策持久化功能"""

import asyncio
import sys
import os

# 添加 src 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ai_trader.persistence import DatabaseManager, DecisionPersistenceService
from ai_trader.models.decision import TradingDecision, TechnicalAnalysisResult, RiskAssessment
from ai_trader.models.market import MarketData, Indicators, Kline


async def test_persistence():
    """测试决策持久化"""
    # 数据库连接
    db_url = "postgresql://postgres:postgres@192.168.1.83:5432/trader_dashboard"

    db = DatabaseManager(db_url)
    await db.connect()

    service = DecisionPersistenceService(db)

    # 创建测试数据
    decision = TradingDecision(
        action="open_long",
        confidence=75.5,
        leverage=5,
        position_size_percent=10.0,
        entry_price=96500.0,
        stop_loss_price=95000.0,
        take_profit_price=100000.0,
        reasoning="Test decision - BTC shows strong bullish momentum",
    )

    technical = TechnicalAnalysisResult(
        trend="bullish",
        trend_confidence=70.0,
        support_levels=[95000.0, 94000.0],
        resistance_levels=[98000.0, 100000.0],
        volume_trend="increasing",
        pattern="bull_flag",
        signal_strength="buy",
        key_observations=[
            "Price above MA7 and MA25",
            "RSI at 65, room for upside",
            "MACD bullish crossover",
        ],
    )

    risk = RiskAssessment(
        risk_level="medium",
        risk_score=45.0,
        recommended_leverage=5,
        recommended_position_percent=10.0,
        should_trade=True,
        risk_factors=["Market volatility elevated", "Weekend liquidity lower"],
        mitigation_suggestions=["Use tight stop loss", "Scale in gradually"],
    )

    # 创建模拟市场数据
    indicators = Indicators(
        ma7=96000.0,
        ma25=95500.0,
        ma99=93000.0,
        rsi=65.0,
        macd=150.0,
        macd_signal=120.0,
        macd_histogram=30.0,
        boll_upper=98000.0,
        boll_middle=96000.0,
        boll_lower=94000.0,
        atr=800.0,
    )

    market_data = MarketData(
        symbol="BTC/USDT",
        current_price=96500.0,
        interval="1h",
        indicators=indicators,
        klines=[],
        high_24h=97000.0,
        low_24h=95000.0,
        change_24h=1.5,
        volume_24h=50000.0,
    )

    # 保存决策
    try:
        decision_id = await service.save_decision(
            decision=decision,
            technical=technical,
            risk=risk,
            market_data=market_data,
            llm_provider="test",
            llm_model="test-model",
            llm_raw_output='{"action": "open_long", "confidence": 75.5}',
            llm_tokens_used=500,
        )
        print(f"✓ 决策已保存: {decision_id}")

        # 验证数据
        row = await db.fetchrow(
            "SELECT * FROM decisions WHERE id = $1", decision_id
        )
        print(f"✓ 决策记录验证: symbol={row['symbol']}, action={row['action']}")

        tech_row = await db.fetchrow(
            "SELECT * FROM technical_snapshots WHERE decision_id = $1", decision_id
        )
        print(f"✓ 技术分析快照验证: trend={tech_row['trend']}")

        risk_row = await db.fetchrow(
            "SELECT * FROM risk_snapshots WHERE decision_id = $1", decision_id
        )
        print(f"✓ 风险评估快照验证: risk_level={risk_row['risk_level']}")

        print("\n所有测试通过!")

    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(test_persistence())
