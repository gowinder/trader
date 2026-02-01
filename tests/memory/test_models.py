# tests/memory/test_models.py
import pytest
from datetime import datetime, timedelta
from ai_trader.memory.models import TradeMemoryEntry, DistilledRule


class TestTradeMemoryEntry:
    def test_create_entry(self):
        entry = TradeMemoryEntry(
            trade_id="trade_001",
            timestamp=datetime.now(),
            symbol="BTCUSDT",
            action="open_long",
            confidence=75.0,
            leverage=5.0,
            reasoning="趋势向上",
            market_state="strong_trend",
            entry_price=50000.0,
        )
        assert entry.trade_id == "trade_001"
        assert entry.action == "open_long"
        assert entry.is_winner is None  # 未平仓

    def test_entry_with_result(self):
        entry = TradeMemoryEntry(
            trade_id="trade_002",
            timestamp=datetime.now(),
            symbol="BTCUSDT",
            action="close_long",
            confidence=80.0,
            leverage=5.0,
            reasoning="止盈",
            market_state="strong_trend",
            entry_price=50000.0,
            exit_price=52000.0,
            pnl_percent=4.0,
            is_winner=True,
        )
        assert entry.is_winner is True
        assert entry.pnl_percent == 4.0


class TestDistilledRule:
    def test_create_rule(self):
        rule = DistilledRule(
            rule_id="rule_001",
            condition={"market_state": "ranging", "rsi": ">70"},
            recommendation={"confidence_threshold": "+10"},
            sample_size=25,
            win_rate=0.72,
            avg_pnl=0.015,
            p_value=0.03,
        )
        assert rule.status == "candidate"
        assert rule.is_statistically_valid()

    def test_rule_invalid_p_value(self):
        rule = DistilledRule(
            rule_id="rule_002",
            condition={"market_state": "trending"},
            recommendation={"leverage": "-1"},
            sample_size=15,
            win_rate=0.55,
            avg_pnl=0.005,
            p_value=0.12,
        )
        assert not rule.is_statistically_valid()
