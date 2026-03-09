"""Unit tests for SignalFilter"""

import pytest
from datetime import datetime, timedelta
from ai_trader.strategies.signal_filter import SignalFilter
from ai_trader.strategies.strategy_base import SignalAction


class TestSignalFilter:

    def test_hold_always_allowed(self):
        sf = SignalFilter(min_interval_hours=6)
        sf.record_trade(SignalAction.LONG, datetime(2026, 1, 1, 12, 0))
        allowed, reason = sf.should_allow_signal(SignalAction.HOLD, datetime(2026, 1, 1, 12, 1))
        assert allowed is True
        assert reason == "HOLD signal"

    def test_first_signal_allowed(self):
        sf = SignalFilter(min_interval_hours=6)
        allowed, reason = sf.should_allow_signal(SignalAction.LONG, datetime(2026, 1, 1, 12, 0))
        assert allowed is True
        assert reason == "Signal allowed"

    def test_signal_within_min_interval_blocked(self):
        sf = SignalFilter(min_interval_hours=6)
        sf.record_trade(SignalAction.LONG, datetime(2026, 1, 1, 12, 0))
        allowed, reason = sf.should_allow_signal(SignalAction.LONG, datetime(2026, 1, 1, 15, 0))
        assert allowed is False
        assert "Too soon" in reason

    def test_signal_after_min_interval_allowed(self):
        sf = SignalFilter(min_interval_hours=6)
        sf.record_trade(SignalAction.LONG, datetime(2026, 1, 1, 12, 0))
        allowed, reason = sf.should_allow_signal(SignalAction.LONG, datetime(2026, 1, 1, 18, 1))
        assert allowed is True

    def test_opposite_action_within_cooldown_blocked(self):
        sf = SignalFilter(min_interval_hours=6, reverse_cooldown_hours=24)
        sf.record_trade(SignalAction.LONG, datetime(2026, 1, 1, 12, 0))
        # 10h later: past min_interval but within reverse_cooldown
        allowed, reason = sf.should_allow_signal(SignalAction.SHORT, datetime(2026, 1, 1, 22, 0))
        assert allowed is False
        assert "flip" in reason.lower()

    def test_opposite_action_after_cooldown_allowed(self):
        sf = SignalFilter(min_interval_hours=6, reverse_cooldown_hours=24)
        sf.record_trade(SignalAction.LONG, datetime(2026, 1, 1, 12, 0))
        # 25h later
        allowed, reason = sf.should_allow_signal(SignalAction.SHORT, datetime(2026, 1, 2, 13, 0))
        assert allowed is True

    def test_same_direction_no_extra_cooldown(self):
        sf = SignalFilter(min_interval_hours=6, reverse_cooldown_hours=24)
        sf.record_trade(SignalAction.LONG, datetime(2026, 1, 1, 12, 0))
        # 7h later: past min_interval, same direction should not be affected by reverse cooldown
        allowed, reason = sf.should_allow_signal(SignalAction.LONG, datetime(2026, 1, 1, 19, 0))
        assert allowed is True

    def test_record_trade_updates_state(self):
        sf = SignalFilter()
        t = datetime(2026, 1, 1, 12, 0)
        sf.record_trade(SignalAction.SHORT, t)
        assert sf.last_trade_time == t
        assert sf.last_action == SignalAction.SHORT

    def test_reset_clears_state(self):
        sf = SignalFilter()
        sf.record_trade(SignalAction.LONG, datetime(2026, 1, 1, 12, 0))
        sf.reset()
        assert sf.last_trade_time is None
        assert sf.last_action is None
        # Should allow any signal immediately
        allowed, _ = sf.should_allow_signal(SignalAction.SHORT, datetime(2026, 1, 1, 12, 1))
        assert allowed is True
