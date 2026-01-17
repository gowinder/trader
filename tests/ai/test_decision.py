import pytest
from unittest.mock import AsyncMock, MagicMock
from ai_trader.ai.decision import DecisionEngine
from ai_trader.models.market import MarketData, Indicators, Kline
from ai_trader.models.order import Position
from ai_trader.models.decision import (
    TechnicalAnalysisResult,
    RiskAssessment,
    TradingDecision,
)


@pytest.fixture
def mock_llm_client():
    client = AsyncMock()
    # Mock chat responses for 3 steps

    # 1. Technical
    tech_result = {
        "trend": "bullish",
        "trend_confidence": 80,
        "support_levels": [9000],
        "resistance_levels": [11000],
        "volume_trend": "stable",
        "pattern": "none",
        "signal_strength": "buy",
        "key_observations": ["Up"],
    }

    # 2. Risk
    risk_result = {
        "risk_level": "low",
        "risk_score": 20,
        "recommended_leverage": 5,
        "recommended_position_percent": 10,
        "should_trade": True,
        "fee_warning": False,
        "risk_factors": ["None"],
        "mitigation_suggestions": ["None"],
    }

    # 3. Trading
    trading_result = {
        "action": "open_long",
        "confidence": 85,
        "leverage": 5,
        "position_size_percent": 10,
        "entry_price": 0,
        "stop_loss_price": 9500,
        "take_profit_price": 10500,
        "order_type": "market",
        "reasoning": "Go",
        "execution_urgency": "immediate",
    }

    client.chat.side_effect = [tech_result, risk_result, trading_result]
    return client


@pytest.fixture
def mock_market_data():
    return MarketData(
        symbol="BTCUSDT",
        current_price=10000,
        klines=[Kline(timestamp=0, open=100, high=101, low=99, close=100, volume=10)]
        * 100,
        interval="15m",
        indicators=Indicators(
            ma7=100,
            ma25=100,
            ma99=100,
            rsi=50,
            macd=0,
            macd_signal=0,
            macd_histogram=0,
            boll_upper=101,
            boll_middle=100,
            boll_lower=99,
            atr=1,
        ),
        high_24h=10100,
        low_24h=9900,
        change_24h=1.0,
        volume_24h=1000,
    )


@pytest.mark.asyncio
async def test_make_decision(mock_llm_client, mock_market_data):
    """Test full decision flow"""
    engine = DecisionEngine(mock_llm_client)

    decision, tech, risk = await engine.analyze_and_decide(
        market_data=mock_market_data,
        current_position=None,
        available_balance=1000.0,
        total_equity=1000.0,
    )

    assert isinstance(decision, TradingDecision)
    assert decision.action == "open_long"
    assert isinstance(tech, TechnicalAnalysisResult)
    assert isinstance(risk, RiskAssessment)

    assert mock_llm_client.chat.call_count == 3
