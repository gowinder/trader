"""决策模型单元测试"""

import pytest
from pydantic import ValidationError

from ai_trader.models.decision import (
    RiskAssessment,
    TechnicalAnalysisResult,
    TradingDecision,
)


# ── TechnicalAnalysisResult ──────────────────────────────────────────


class TestTechnicalAnalysisResult:
    def test_technical_analysis_result_defaults(self):
        r = TechnicalAnalysisResult(trend="neutral")
        assert r.trend_confidence == 50.0
        assert r.support_levels == []
        assert r.resistance_levels == []
        assert r.volume_trend == "stable"
        assert r.pattern == ""
        assert r.signal_strength == "neutral"
        assert r.key_observations == []

    def test_technical_analysis_result_full(self):
        r = TechnicalAnalysisResult(
            trend="strong_bullish",
            trend_confidence=95.0,
            support_levels=[100.0, 200.0],
            resistance_levels=[300.0],
            volume_trend="increasing",
            pattern="head_and_shoulders",
            signal_strength="strong_buy",
            key_observations=["breakout"],
        )
        assert r.trend == "strong_bullish"
        assert r.trend_confidence == 95.0
        assert r.support_levels == [100.0, 200.0]
        assert r.signal_strength == "strong_buy"

    def test_technical_analysis_result_trend_confidence_ge(self):
        with pytest.raises(ValidationError):
            TechnicalAnalysisResult(trend="neutral", trend_confidence=-1)

    def test_technical_analysis_result_trend_confidence_le(self):
        with pytest.raises(ValidationError):
            TechnicalAnalysisResult(trend="neutral", trend_confidence=101)

    def test_technical_analysis_result_trend_confidence_boundary(self):
        r0 = TechnicalAnalysisResult(trend="neutral", trend_confidence=0)
        assert r0.trend_confidence == 0
        r100 = TechnicalAnalysisResult(trend="neutral", trend_confidence=100)
        assert r100.trend_confidence == 100

    def test_technical_analysis_result_invalid_trend(self):
        with pytest.raises(ValidationError):
            TechnicalAnalysisResult(trend="invalid_trend")

    def test_technical_analysis_result_invalid_volume_trend(self):
        with pytest.raises(ValidationError):
            TechnicalAnalysisResult(trend="neutral", volume_trend="exploding")

    def test_technical_analysis_result_invalid_signal_strength(self):
        with pytest.raises(ValidationError):
            TechnicalAnalysisResult(trend="neutral", signal_strength="mega_buy")


# ── RiskAssessment ───────────────────────────────────────────────────


class TestRiskAssessment:
    def test_risk_assessment_defaults(self):
        r = RiskAssessment()
        assert r.risk_level == "medium"
        assert r.risk_score == 50.0
        assert r.recommended_leverage == 1
        assert r.recommended_position_percent == 10.0
        assert r.should_trade is False
        assert r.fee_warning is False
        assert r.risk_factors == []
        assert r.mitigation_suggestions == []

    def test_risk_assessment_boundary_risk_score_0(self):
        r = RiskAssessment(risk_score=0)
        assert r.risk_score == 0

    def test_risk_assessment_boundary_risk_score_100(self):
        r = RiskAssessment(risk_score=100)
        assert r.risk_score == 100

    def test_risk_assessment_risk_score_below_0(self):
        with pytest.raises(ValidationError):
            RiskAssessment(risk_score=-1)

    def test_risk_assessment_risk_score_above_100(self):
        with pytest.raises(ValidationError):
            RiskAssessment(risk_score=101)

    def test_risk_assessment_should_trade_default_false(self):
        r = RiskAssessment()
        assert r.should_trade is False

    def test_risk_assessment_invalid_risk_level(self):
        with pytest.raises(ValidationError):
            RiskAssessment(risk_level="extreme")

    def test_risk_assessment_recommended_leverage_ge(self):
        with pytest.raises(ValidationError):
            RiskAssessment(recommended_leverage=0)


# ── TradingDecision ──────────────────────────────────────────────────


class TestTradingDecision:
    def test_trading_decision_basic(self):
        d = TradingDecision(action="hold")
        assert d.action == "hold"
        assert d.confidence == 50.0
        assert d.leverage == 1
        assert d.order_type == "market"
        assert d.execution_urgency == "wait_for_price"

    def test_trading_decision_all_actions(self):
        valid_actions = [
            "open_long", "open_short", "close_long", "close_short",
            "add_long", "add_short", "reduce_long", "reduce_short", "hold",
        ]
        for action in valid_actions:
            d = TradingDecision(action=action)
            assert d.action == action

    def test_trading_decision_invalid_action(self):
        with pytest.raises(ValidationError):
            TradingDecision(action="buy")

    def test_trading_decision_confidence_boundary_0(self):
        d = TradingDecision(action="hold", confidence=0)
        assert d.confidence == 0

    def test_trading_decision_confidence_boundary_100(self):
        d = TradingDecision(action="hold", confidence=100)
        assert d.confidence == 100

    def test_trading_decision_confidence_below_0(self):
        with pytest.raises(ValidationError):
            TradingDecision(action="hold", confidence=-1)

    def test_trading_decision_confidence_above_100(self):
        with pytest.raises(ValidationError):
            TradingDecision(action="hold", confidence=101)

    def test_trading_decision_leverage_validator_below_1(self):
        d = TradingDecision(action="hold", leverage=0)
        assert d.leverage == 1

    def test_trading_decision_leverage_validator_negative(self):
        d = TradingDecision(action="hold", leverage=-5)
        assert d.leverage == 1

    def test_trading_decision_leverage_normal(self):
        d = TradingDecision(action="hold", leverage=10)
        assert d.leverage == 10

    def test_trading_decision_order_type_default_market(self):
        d = TradingDecision(action="hold")
        assert d.order_type == "market"

    def test_trading_decision_order_type_limit(self):
        d = TradingDecision(action="hold", order_type="limit")
        assert d.order_type == "limit"

    def test_trading_decision_invalid_order_type(self):
        with pytest.raises(ValidationError):
            TradingDecision(action="hold", order_type="stop")

    def test_trading_decision_serialization_roundtrip(self):
        d = TradingDecision(
            action="open_long",
            confidence=80.0,
            leverage=5,
            position_size_percent=20.0,
            entry_price=50000.0,
            stop_loss_price=48000.0,
            take_profit_price=55000.0,
            order_type="limit",
            reasoning="bullish breakout",
            reasoning_zh="看涨突破",
            execution_urgency="immediate",
        )
        data = d.model_dump()
        d2 = TradingDecision(**data)
        assert d2.action == d.action
        assert d2.confidence == d.confidence
        assert d2.leverage == d.leverage
        assert d2.entry_price == d.entry_price
        assert d2.stop_loss_price == d.stop_loss_price
        assert d2.take_profit_price == d.take_profit_price

    def test_trading_decision_json_roundtrip(self):
        d = TradingDecision(action="close_short", confidence=75.0)
        json_str = d.model_dump_json()
        d2 = TradingDecision.model_validate_json(json_str)
        assert d2.action == d.action
        assert d2.confidence == d.confidence

    def test_trading_decision_private_attr_not_serialized(self):
        d = TradingDecision(action="hold")
        data = d.model_dump()
        assert "_llm_raw_output" not in data
