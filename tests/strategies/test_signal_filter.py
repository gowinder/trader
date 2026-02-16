"""Unit tests for SignalFilter with reverse_cooldown_hours support"""

import pytest
from datetime import datetime, timedelta
from ai_trader.strategies.signal_filter import SignalFilter
from ai_trader.strategies.strategy_base import SignalAction


class TestSignalFilterBasic:
    """Basic signal filtering tests"""

    def test_allow_first_signal(self):
        sf = SignalFilter(min_interval_hours=4)
        allowed, reason = sf.should_allow_signal(SignalAction.LONG, datetime(2026, 1, 1, 12, 0))
        assert allowed is True

    def test_hold_always_allowed(self):
        sf = SignalFilter(min_interval_hours=4)
        sf.record_trade(SignalAction.LONG, datetime(2026, 1, 1, 12, 0))
        # HOLD immediately after a trade should still pass
        allowed, _ = sf.should_allow_signal(SignalAction.HOLD, datetime(2026, 1, 1, 12, 1))
        assert allowed is True

    def test_block_too_soon(self):
        sf = SignalFilter(min_interval_hours=4)
        sf.record_trade(SignalAction.LONG, datetime(2026, 1, 1, 12, 0))
        allowed, reason = sf.should_allow_signal(SignalAction.LONG, datetime(2026, 1, 1, 13, 0))
        assert allowed is False
        assert "Too soon" in reason

    def test_allow_after_interval(self):
        sf = SignalFilter(min_interval_hours=4)
        sf.record_trade(SignalAction.LONG, datetime(2026, 1, 1, 12, 0))
        allowed, _ = sf.should_allow_signal(SignalAction.LONG, datetime(2026, 1, 1, 16, 1))
        assert allowed is True


class TestSignalFilterReverseCooldown:
    """Tests for configurable reverse cooldown"""

    def test_block_quick_direction_flip(self):
        sf = SignalFilter(min_interval_hours=4, reverse_cooldown_hours=12)
        sf.record_trade(SignalAction.LONG, datetime(2026, 1, 1, 12, 0))
        # 6h later: past min_interval but within reverse_cooldown
        allowed, reason = sf.should_allow_signal(SignalAction.SHORT, datetime(2026, 1, 1, 18, 0))
        assert allowed is False
        assert "flip" in reason.lower()

    def test_allow_flip_after_cooldown(self):
        sf = SignalFilter(min_interval_hours=4, reverse_cooldown_hours=12)
        sf.record_trade(SignalAction.LONG, datetime(2026, 1, 1, 12, 0))
        # 13h later: past both min_interval and reverse_cooldown
        allowed, _ = sf.should_allow_signal(SignalAction.SHORT, datetime(2026, 1, 2, 1, 0))
        assert allowed is True

    def test_same_direction_not_affected_by_reverse_cooldown(self):
        sf = SignalFilter(min_interval_hours=4, reverse_cooldown_hours=24)
        sf.record_trade(SignalAction.LONG, datetime(2026, 1, 1, 12, 0))
        # 5h later: same direction, past min_interval, reverse_cooldown irrelevant
        allowed, _ = sf.should_allow_signal(SignalAction.LONG, datetime(2026, 1, 1, 17, 0))
        assert allowed is True

    def test_custom_short_cooldown(self):
        sf = SignalFilter(min_interval_hours=1, reverse_cooldown_hours=2)
        sf.record_trade(SignalAction.SHORT, datetime(2026, 1, 1, 10, 0))
        # 1.5h: past min_interval but within 2h reverse cooldown
        allowed, _ = sf.should_allow_signal(SignalAction.LONG, datetime(2026, 1, 1, 11, 30))
        assert allowed is False
        # 2.5h: past both
        allowed, _ = sf.should_allow_signal(SignalAction.LONG, datetime(2026, 1, 1, 12, 30))
        assert allowed is True

    def test_float_interval_hours(self):
        sf = SignalFilter(min_interval_hours=0.5)  # 30 minutes
        sf.record_trade(SignalAction.LONG, datetime(2026, 1, 1, 12, 0))
        # 20 min later: blocked
        allowed, _ = sf.should_allow_signal(SignalAction.LONG, datetime(2026, 1, 1, 12, 20))
        assert allowed is False
        # 35 min later: allowed
        allowed, _ = sf.should_allow_signal(SignalAction.LONG, datetime(2026, 1, 1, 12, 35))
        assert allowed is True


class TestSignalFilterReset:
    """Test reset functionality"""

    def test_reset_clears_state(self):
        sf = SignalFilter(min_interval_hours=4)
        sf.record_trade(SignalAction.LONG, datetime(2026, 1, 1, 12, 0))
        sf.reset()
        # Should allow immediately after reset
        allowed, _ = sf.should_allow_signal(SignalAction.SHORT, datetime(2026, 1, 1, 12, 1))
        assert allowed is True
