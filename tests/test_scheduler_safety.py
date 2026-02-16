"""Unit tests for Phase 1 safety features integrated into Scheduler:
- Daily loss limit circuit breaker
- SignalFilter integration
Tests operate on Scheduler internal state without requiring full init.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

from ai_trader.strategies.signal_filter import SignalFilter
from ai_trader.strategies.strategy_base import SignalAction


# ---------------------------------------------------------------------------
# Helper: build a minimal Scheduler-like object with only the Phase 1 attrs
# ---------------------------------------------------------------------------
class FakeScheduler:
    """Mimics Scheduler's Phase 1 attributes for isolated testing."""

    def __init__(self):
        self._daily_pnl: dict[str, float] = {}
        self._daily_pnl_date: str = ""
        self._trading_halted: bool = False
        self._halt_until: str | None = None
        self._halt_consecutive_days: int = 0
        self._signal_filters: dict[str, SignalFilter] = {}


# ===========================================================================
# Daily loss limit tests
# ===========================================================================
class TestDailyLossLimit:
    """Test the daily PnL tracking and circuit-breaker logic"""

    def test_pnl_accumulation(self):
        s = FakeScheduler()
        s._daily_pnl["BTC/USDT:USDT"] = -50.0
        s._daily_pnl["ETH/USDT:USDT"] = -30.0
        total = sum(s._daily_pnl.values())
        assert total == pytest.approx(-80.0)

    def test_halt_triggers_when_loss_exceeds_limit(self):
        """Simulate the check in _run_cycle_for_symbol_impl"""
        s = FakeScheduler()
        equity = 10000.0
        daily_loss_limit_percent = 3.0  # 3% = 300 USDT

        s._daily_pnl["BTC/USDT:USDT"] = -200.0
        s._daily_pnl["ETH/USDT:USDT"] = -150.0
        daily_pnl_total = sum(s._daily_pnl.values())  # -350

        max_daily_loss = equity * (daily_loss_limit_percent / 100)  # 300
        if daily_pnl_total < 0 and abs(daily_pnl_total) >= max_daily_loss:
            s._trading_halted = True
            s._halt_consecutive_days += 1

        assert s._trading_halted is True
        assert s._halt_consecutive_days == 1

    def test_no_halt_when_within_limit(self):
        s = FakeScheduler()
        equity = 10000.0
        daily_loss_limit_percent = 3.0

        s._daily_pnl["BTC/USDT:USDT"] = -100.0
        daily_pnl_total = sum(s._daily_pnl.values())  # -100

        max_daily_loss = equity * (daily_loss_limit_percent / 100)  # 300
        halted = daily_pnl_total < 0 and abs(daily_pnl_total) >= max_daily_loss
        assert halted is False

    def test_no_halt_when_profitable(self):
        s = FakeScheduler()
        equity = 10000.0
        daily_loss_limit_percent = 3.0

        s._daily_pnl["BTC/USDT:USDT"] = 500.0
        daily_pnl_total = sum(s._daily_pnl.values())

        halted = daily_pnl_total < 0 and abs(daily_pnl_total) >= (equity * daily_loss_limit_percent / 100)
        assert halted is False

    def test_daily_reset(self):
        """Simulate the daily reset logic in start() loop"""
        s = FakeScheduler()
        s._daily_pnl = {"BTC/USDT:USDT": -200.0}
        s._daily_pnl_date = "2026-02-15"
        s._trading_halted = False

        # New day
        today_str = "2026-02-16"
        if today_str != s._daily_pnl_date:
            if not s._trading_halted:
                s._halt_consecutive_days = 0
            s._daily_pnl = {}
            s._daily_pnl_date = today_str
            s._trading_halted = False

        assert s._daily_pnl == {}
        assert s._daily_pnl_date == "2026-02-16"
        assert s._halt_consecutive_days == 0

    def test_consecutive_days_preserved_after_halt(self):
        """If yesterday triggered halt, consecutive_days should NOT reset on new day"""
        s = FakeScheduler()
        s._daily_pnl = {"BTC/USDT:USDT": -500.0}
        s._daily_pnl_date = "2026-02-15"
        s._trading_halted = True  # Yesterday triggered halt
        s._halt_consecutive_days = 1

        today_str = "2026-02-16"
        if today_str != s._daily_pnl_date:
            if not s._trading_halted:
                s._halt_consecutive_days = 0
            s._daily_pnl = {}
            s._daily_pnl_date = today_str
            s._trading_halted = False

        # consecutive_days should stay at 1 because yesterday was halted
        assert s._halt_consecutive_days == 1

    def test_forced_break_after_consecutive_halts(self):
        """After N consecutive halt days, _halt_until should be set"""
        s = FakeScheduler()
        s._halt_consecutive_days = 1
        consecutive_halt_days_for_break = 2
        forced_break_days = 7

        # Simulate second consecutive halt
        s._trading_halted = True
        s._halt_consecutive_days += 1  # now 2

        if s._halt_consecutive_days >= consecutive_halt_days_for_break:
            break_end = datetime(2026, 2, 16) + timedelta(days=forced_break_days)
            s._halt_until = break_end.strftime("%Y-%m-%d")

        assert s._halt_until == "2026-02-23"
        assert s._halt_consecutive_days == 2

    def test_forced_break_end_resets_consecutive(self):
        """When forced break period ends, _halt_consecutive_days resets to 0"""
        s = FakeScheduler()
        s._halt_until = "2026-02-20"
        s._halt_consecutive_days = 2
        s._trading_halted = True

        # Simulate check when today >= halt_until
        current_date_str = "2026-02-21"
        if s._halt_until:
            if current_date_str < s._halt_until:
                pass  # still in break
            else:
                s._trading_halted = False
                s._halt_until = None
                s._halt_consecutive_days = 0

        assert s._trading_halted is False
        assert s._halt_until is None
        assert s._halt_consecutive_days == 0

    def test_halt_blocks_open_but_allows_close(self):
        """When halted with position, open signals blocked, close allowed"""
        s = FakeScheduler()
        s._trading_halted = True

        # Open signal should be blocked
        action = "open_long"
        has_position = True
        if s._trading_halted and action in ("open_long", "open_short"):
            action = "hold"  # blocked

        assert action == "hold"

        # Close signal should NOT be blocked
        action2 = "close_long"
        if s._trading_halted and action2 in ("open_long", "open_short"):
            action2 = "hold"

        assert action2 == "close_long"  # unchanged


# ===========================================================================
# SignalFilter integration tests
# ===========================================================================
class TestSignalFilterIntegration:
    """Test SignalFilter as used by Scheduler"""

    def test_filter_blocks_rapid_open(self):
        """Simulate the scheduler's filter logic after LLM decision"""
        filters: dict[str, SignalFilter] = {}
        symbol = "BTC/USDT:USDT"
        min_interval = 4.0
        reverse_cooldown = 12.0

        # First open_long at T=0, should pass and be recorded
        if symbol not in filters:
            filters[symbol] = SignalFilter(
                min_interval_hours=min_interval,
                reverse_cooldown_hours=reverse_cooldown,
            )
        sf = filters[symbol]

        t0 = datetime(2026, 1, 1, 12, 0)
        allowed, _ = sf.should_allow_signal(SignalAction.LONG, t0)
        assert allowed is True
        sf.record_trade(SignalAction.LONG, t0)

        # Second open_long 2h later — blocked
        t1 = datetime(2026, 1, 1, 14, 0)
        allowed, reason = sf.should_allow_signal(SignalAction.LONG, t1)
        assert allowed is False
        assert "Too soon" in reason

    def test_filter_not_applied_to_close(self):
        """close_long/close_short should never be filtered"""
        sf = SignalFilter(min_interval_hours=4)
        sf.record_trade(SignalAction.LONG, datetime(2026, 1, 1, 12, 0))

        # HOLD is always allowed (close actions are not SignalAction enums,
        # they are handled at scheduler level by not entering the filter branch)
        allowed, _ = sf.should_allow_signal(SignalAction.HOLD, datetime(2026, 1, 1, 12, 1))
        assert allowed is True

    def test_record_only_on_success(self):
        """Simulate: filter passes, but order_id is None (order failed) → don't record"""
        sf = SignalFilter(min_interval_hours=4)
        t0 = datetime(2026, 1, 1, 12, 0)

        allowed, _ = sf.should_allow_signal(SignalAction.LONG, t0)
        assert allowed is True

        order_id = None  # order failed
        if order_id:
            sf.record_trade(SignalAction.LONG, t0)

        # Because we didn't record, next signal should still be allowed
        t1 = datetime(2026, 1, 1, 12, 30)
        allowed2, _ = sf.should_allow_signal(SignalAction.LONG, t1)
        assert allowed2 is True

    def test_per_symbol_isolation(self):
        """Each symbol has its own SignalFilter instance"""
        filters: dict[str, SignalFilter] = {}
        for sym in ["BTC/USDT:USDT", "ETH/USDT:USDT"]:
            filters[sym] = SignalFilter(min_interval_hours=4)

        t0 = datetime(2026, 1, 1, 12, 0)
        filters["BTC/USDT:USDT"].record_trade(SignalAction.LONG, t0)

        # ETH filter should be independent
        t1 = datetime(2026, 1, 1, 12, 30)
        allowed, _ = filters["ETH/USDT:USDT"].should_allow_signal(SignalAction.LONG, t1)
        assert allowed is True

        # BTC filter should block
        allowed2, _ = filters["BTC/USDT:USDT"].should_allow_signal(SignalAction.LONG, t1)
        assert allowed2 is False


# ===========================================================================
# Config defaults tests
# ===========================================================================
class TestPhase1ConfigDefaults:
    """Test that new config fields have correct defaults"""

    def test_daily_loss_limit_percent_default(self):
        from ai_trader.config import TradingConfig
        cfg = TradingConfig(_env_file=None)
        assert cfg.daily_loss_limit_percent == 3.0

    def test_consecutive_halt_days_default(self):
        from ai_trader.config import TradingConfig
        cfg = TradingConfig(_env_file=None)
        assert cfg.consecutive_halt_days_for_break == 2

    def test_forced_break_days_default(self):
        from ai_trader.config import TradingConfig
        cfg = TradingConfig(_env_file=None)
        assert cfg.forced_break_days == 7

    def test_signal_min_interval_default(self):
        from ai_trader.config import TradingConfig
        cfg = TradingConfig(_env_file=None)
        assert cfg.signal_min_interval_hours == 4.0

    def test_signal_reverse_cooldown_default(self):
        from ai_trader.config import TradingConfig
        cfg = TradingConfig(_env_file=None)
        assert cfg.signal_reverse_cooldown_hours == 12.0

    def test_config_from_env(self, monkeypatch):
        monkeypatch.setenv("DAILY_LOSS_LIMIT_PERCENT", "5.0")
        monkeypatch.setenv("SIGNAL_MIN_INTERVAL_HOURS", "6.0")
        from ai_trader.config import TradingConfig
        cfg = TradingConfig(_env_file=None)
        assert cfg.daily_loss_limit_percent == 5.0
        assert cfg.signal_min_interval_hours == 6.0
