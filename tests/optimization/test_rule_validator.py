# tests/optimization/test_rule_validator.py
"""Tests for RuleValidator."""

import pytest
from datetime import datetime, timezone

from ai_trader.optimization.rule_validator import RuleValidator
from ai_trader.memory.models import TradeMemoryEntry


def _make_entry(
    is_winner: bool = True,
    market_state: str = "trending",
    hour_of_day: int = 10,
    consecutive_losses: int = 0,
    pnl_percent: float = 1.0,
    trade_id: str = "",
) -> TradeMemoryEntry:
    return TradeMemoryEntry(
        trade_id=trade_id or f"t_{id(is_winner)}",
        timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        symbol="BTC/USDT",
        action="open_long",
        confidence=0.8,
        leverage=1.0,
        reasoning="test",
        market_state=market_state,
        hour_of_day=hour_of_day,
        consecutive_losses=consecutive_losses,
        pnl_percent=pnl_percent,
        is_winner=is_winner,
    )


def _make_history(
    n: int,
    winner_ratio: float = 0.5,
    market_state: str = "trending",
    hour_of_day: int = 10,
) -> list[TradeMemoryEntry]:
    entries = []
    for i in range(n):
        is_w = i < int(n * winner_ratio)
        entries.append(
            _make_entry(
                is_winner=is_w,
                market_state=market_state,
                hour_of_day=hour_of_day,
                pnl_percent=2.0 if is_w else -1.0,
                trade_id=f"t_{i}",
            )
        )
    return entries


class TestRuleValidator:
    @pytest.fixture
    def validator(self):
        return RuleValidator()

    @pytest.fixture
    def sample_trades(self):
        trades = []
        for i in range(30):
            is_ranging = i < 20
            is_winner = (i % 4 != 0) if is_ranging else (i % 3 != 0)
            trades.append(TradeMemoryEntry(
                trade_id=f"t{i}",
                timestamp=datetime.now(),
                symbol="BTCUSDT",
                action="close_long",
                confidence=55.0 if is_ranging else 70.0,
                leverage=5.0,
                reasoning="test",
                market_state="ranging" if is_ranging else "strong_trend",
                entry_price=50000.0,
                pnl_percent=2.0 if is_winner else -1.5,
                is_winner=is_winner,
            ))
        return trades

    def test_validate_with_sufficient_samples(self, validator, sample_trades):
        rule = {
            "condition": {"market_state": "ranging"},
            "recommendation": {"confidence_threshold": "+10"},
        }
        result = validator.validate(rule, sample_trades)
        assert "is_valid" in result
        assert "sample_size" in result
        assert result["sample_size"] >= 20

    def test_reject_insufficient_samples(self, validator):
        trades = [
            TradeMemoryEntry(
                trade_id="t1",
                timestamp=datetime.now(),
                symbol="BTCUSDT",
                action="close_long",
                confidence=70.0,
                leverage=5.0,
                reasoning="test",
                market_state="ranging",
                entry_price=50000.0,
                is_winner=True,
            )
        ] * 5
        rule = {"condition": {"market_state": "ranging"}, "recommendation": {}}
        result = validator.validate(rule, trades)
        assert result["is_valid"] is False
        assert "样本不足" in result["reason"]


class TestMatchCondition:

    def setup_method(self):
        self.v = RuleValidator()

    def test_match_condition_market_state(self):
        entry = _make_entry(market_state="trending")
        assert self.v._match_condition(entry, {"market_state": "trending"}) is True
        assert self.v._match_condition(entry, {"market_state": "ranging"}) is False

    def test_match_condition_hour_range(self):
        entry = _make_entry(hour_of_day=10)
        assert self.v._match_condition(entry, {"hour_range": [8, 12]}) is True
        assert self.v._match_condition(entry, {"hour_range": [8, 9]}) is False
        assert self.v._match_condition(entry, {"hour_range": [10, 10]}) is True

    def test_match_condition_consecutive_losses_gt(self):
        entry = _make_entry(consecutive_losses=3)
        assert self.v._match_condition(entry, {"consecutive_losses_gt": 2}) is True
        assert self.v._match_condition(entry, {"consecutive_losses_gt": 3}) is False
        assert self.v._match_condition(entry, {"consecutive_losses_gt": 4}) is False

    def test_match_condition_empty(self):
        entry = _make_entry()
        assert self.v._match_condition(entry, {}) is True


class TestValidateExtended:

    def setup_method(self):
        self.v = RuleValidator()

    def test_validate_insufficient_samples(self):
        history = _make_history(10)
        result = self.v.validate({"condition": {"market_state": "trending"}}, history)
        assert result["is_valid"] is False
        assert "样本不足" in result["reason"]
        assert result["sample_size"] == 10

    def test_validate_with_enough_samples(self):
        matched = _make_history(30, winner_ratio=0.9, market_state="trending")
        baseline = _make_history(30, winner_ratio=0.3, market_state="ranging")
        for i, e in enumerate(baseline):
            e.trade_id = f"b_{i}"
        history = matched + baseline

        rule = {"condition": {"market_state": "trending"}, "recommendation": {"action": "open_long"}}
        result = self.v.validate(rule, history)
        assert result["sample_size"] == 30
        assert "win_rate" in result
        assert "baseline_win_rate" in result
        assert "p_value" in result
        assert "improvement" in result


class TestSignificanceTest:

    def setup_method(self):
        self.v = RuleValidator()

    def test_significance_test_no_baseline(self):
        matched = _make_history(25)
        p = self.v._simple_significance_test(matched, [])
        assert p == 1.0

    def test_significance_test_small_baseline(self):
        matched = _make_history(25)
        baseline = _make_history(3)
        p = self.v._simple_significance_test(matched, baseline)
        assert p == 1.0


class TestCreateDistilledRule:

    def setup_method(self):
        self.v = RuleValidator()

    def test_create_distilled_rule_valid(self):
        rule = {
            "condition": {"market_state": "trending"},
            "recommendation": {"action": "open_long"},
            "reasoning": "trend is good",
        }
        validation = {
            "is_valid": True,
            "sample_size": 30,
            "win_rate": 0.8,
            "avg_pnl": 1.5,
            "p_value": 0.03,
        }
        dr = self.v.create_distilled_rule(rule, validation)
        assert dr is not None
        assert dr.condition == {"market_state": "trending"}
        assert dr.win_rate == 0.8
        assert dr.rule_id.startswith("rule_")

    def test_create_distilled_rule_invalid(self):
        rule = {"condition": {}, "recommendation": {}}
        validation = {"is_valid": False, "reason": "not enough"}
        dr = self.v.create_distilled_rule(rule, validation)
        assert dr is None
