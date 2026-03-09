"""补充 memory/models.py 的测试场景"""

import pytest
from datetime import datetime, timedelta
from ai_trader.memory.models import TradeMemoryEntry, DistilledRule, RuleStatus


class TestTradeMemoryEntryToDict:
    def test_trade_memory_entry_to_dict(self):
        ts = datetime(2025, 1, 1, 12, 0, 0)
        entry = TradeMemoryEntry(
            trade_id="t1",
            timestamp=ts,
            symbol="BTCUSDT",
            action="open_long",
            confidence=80.0,
            leverage=10.0,
            reasoning="bullish",
            market_state="trending",
            timeframe_alignment={"1h": "up"},
            technical_snapshot={"rsi": 65},
            patterns_detected=["hammer"],
            entry_price=50000.0,
            exit_price=52000.0,
            pnl_percent=4.0,
            max_adverse_excursion=1.5,
            max_favorable_excursion=5.0,
            holding_duration=timedelta(hours=2),
            hour_of_day=12,
            day_of_week=3,
            consecutive_losses=0,
            is_winner=True,
        )
        d = entry.to_dict()
        assert d["trade_id"] == "t1"
        assert d["timestamp"] == ts.isoformat()
        assert d["symbol"] == "BTCUSDT"
        assert d["action"] == "open_long"
        assert d["confidence"] == 80.0
        assert d["leverage"] == 10.0
        assert d["reasoning"] == "bullish"
        assert d["market_state"] == "trending"
        assert d["timeframe_alignment"] == {"1h": "up"}
        assert d["technical_snapshot"] == {"rsi": 65}
        assert d["patterns_detected"] == ["hammer"]
        assert d["entry_price"] == 50000.0
        assert d["exit_price"] == 52000.0
        assert d["pnl_percent"] == 4.0
        assert d["max_adverse_excursion"] == 1.5
        assert d["max_favorable_excursion"] == 5.0
        assert d["holding_duration"] == str(timedelta(hours=2))
        assert d["hour_of_day"] == 12
        assert d["day_of_week"] == 3
        assert d["consecutive_losses"] == 0
        assert d["is_winner"] is True

    def test_trade_memory_entry_to_dict_none_holding_duration(self):
        entry = TradeMemoryEntry(
            trade_id="t2",
            timestamp=datetime.now(),
            symbol="ETHUSDT",
            action="close_short",
            confidence=70.0,
            leverage=5.0,
            reasoning="tp",
            market_state="ranging",
        )
        d = entry.to_dict()
        assert d["holding_duration"] is None
        assert d["exit_price"] is None
        assert d["pnl_percent"] is None


class TestTradeMemoryEntryDefaults:
    def test_trade_memory_entry_defaults(self):
        entry = TradeMemoryEntry(
            trade_id="t3",
            timestamp=datetime.now(),
            symbol="BTCUSDT",
            action="open_long",
            confidence=60.0,
            leverage=3.0,
            reasoning="test",
            market_state="volatile",
        )
        assert entry.timeframe_alignment == {}
        assert entry.technical_snapshot == {}
        assert entry.patterns_detected == []
        assert entry.entry_price == 0.0
        assert entry.exit_price is None
        assert entry.pnl_percent is None
        assert entry.max_adverse_excursion == 0.0
        assert entry.max_favorable_excursion == 0.0
        assert entry.holding_duration is None
        assert entry.hour_of_day == 0
        assert entry.day_of_week == 0
        assert entry.consecutive_losses == 0
        assert entry.is_winner is None


class TestDistilledRuleStatisticalValidity:
    def _make_rule(self, p_value=0.03, sample_size=25, **kwargs):
        defaults = dict(
            rule_id="r1",
            condition={"rsi": ">70"},
            recommendation={"action": "sell"},
            win_rate=0.7,
            avg_pnl=0.02,
        )
        defaults.update(kwargs)
        return DistilledRule(p_value=p_value, sample_size=sample_size, **defaults)

    def test_distilled_rule_is_statistically_valid_true(self):
        rule = self._make_rule(p_value=0.03, sample_size=25)
        assert rule.is_statistically_valid() is True

    def test_distilled_rule_is_statistically_valid_false_p_value(self):
        rule = self._make_rule(p_value=0.06, sample_size=25)
        assert rule.is_statistically_valid() is False

    def test_distilled_rule_is_statistically_valid_false_sample_size(self):
        rule = self._make_rule(p_value=0.03, sample_size=15)
        assert rule.is_statistically_valid() is False

    def test_distilled_rule_is_statistically_valid_boundary(self):
        # p_value == threshold => not valid (strict <)
        rule = self._make_rule(p_value=0.05, sample_size=20)
        assert rule.is_statistically_valid() is False

        # p_value just below, sample_size exactly at min
        rule2 = self._make_rule(p_value=0.049, sample_size=20)
        assert rule2.is_statistically_valid() is True


class TestDistilledRuleToDict:
    def test_distilled_rule_to_dict(self):
        rule = DistilledRule(
            rule_id="r2",
            condition={"vol": "high"},
            recommendation={"leverage": "-2"},
            sample_size=30,
            win_rate=0.65,
            avg_pnl=0.01,
            p_value=0.02,
            reasoning="volume rule",
            status=RuleStatus.ACTIVE.value,
            validation_count=5,
        )
        d = rule.to_dict()
        assert d["rule_id"] == "r2"
        assert d["condition"] == {"vol": "high"}
        assert d["recommendation"] == {"leverage": "-2"}
        assert d["sample_size"] == 30
        assert d["win_rate"] == 0.65
        assert d["avg_pnl"] == 0.01
        assert d["p_value"] == 0.02
        assert d["reasoning"] == "volume rule"
        assert d["status"] == "active"
        assert d["validation_count"] == 5
        assert "created_at" in d
        assert d["last_validated"] is None


class TestDistilledRuleDefaultStatus:
    def test_distilled_rule_default_status(self):
        rule = DistilledRule(
            rule_id="r3",
            condition={},
            recommendation={},
            sample_size=20,
            win_rate=0.5,
            avg_pnl=0.0,
            p_value=0.04,
        )
        assert rule.status == "candidate"
        assert rule.status == RuleStatus.CANDIDATE.value


class TestRuleStatusEnum:
    def test_rule_status_enum(self):
        assert RuleStatus.CANDIDATE.value == "candidate"
        assert RuleStatus.ACTIVE.value == "active"
        assert RuleStatus.DEPRECATED.value == "deprecated"

    def test_rule_status_is_str(self):
        assert isinstance(RuleStatus.CANDIDATE, str)
        assert RuleStatus.ACTIVE == "active"
