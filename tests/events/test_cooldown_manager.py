"""Supplementary tests for CooldownManager (complements test_cooldown.py)."""

from unittest.mock import patch

from ai_trader.events.cooldown import CooldownManager


class TestCooldownManagerSupplementary:
    """Covers scenarios not in test_cooldown.py."""

    def test_default_cooldown_values(self):
        """Default constructor uses 300 / 600."""
        mgr = CooldownManager()
        assert mgr.global_cooldown == 300
        assert mgr.per_event_cooldown == 600

    def test_multiple_events_independent_per_event(self):
        """Per-event cooldowns are tracked independently."""
        mgr = CooldownManager(global_cooldown=0, per_event_cooldown=100)

        with patch("ai_trader.events.cooldown.time.monotonic", return_value=1000.0):
            mgr.record_trigger("event_a")

        with patch("ai_trader.events.cooldown.time.monotonic", return_value=1050.0):
            mgr.record_trigger("event_b")

        # At t=1101: event_a expired (101s > 100), event_b still active (51s < 100)
        with patch("ai_trader.events.cooldown.time.monotonic", return_value=1101.0):
            assert mgr.can_trigger("event_a") is True
            assert mgr.can_trigger("event_b") is False

    def test_record_trigger_updates_global_each_time(self):
        """Each record_trigger resets the global cooldown clock."""
        mgr = CooldownManager(global_cooldown=100, per_event_cooldown=0)

        with patch("ai_trader.events.cooldown.time.monotonic", return_value=1000.0):
            mgr.record_trigger("a")

        # At t=1050 trigger "b" — resets global to 1050
        with patch("ai_trader.events.cooldown.time.monotonic", return_value=1050.0):
            mgr.record_trigger("b")

        # At t=1101 — 101s since first trigger but only 51s since second
        with patch("ai_trader.events.cooldown.time.monotonic", return_value=1101.0):
            assert mgr.can_trigger("c") is False  # global cooldown from t=1050

        # At t=1151 — 101s since second trigger
        with patch("ai_trader.events.cooldown.time.monotonic", return_value=1151.0):
            assert mgr.can_trigger("c") is True

    def test_per_event_fully_expires(self):
        """Per-event cooldown allows same event after full duration."""
        mgr = CooldownManager(global_cooldown=0, per_event_cooldown=600)

        with patch("ai_trader.events.cooldown.time.monotonic", return_value=1000.0):
            mgr.record_trigger("x")

        with patch("ai_trader.events.cooldown.time.monotonic", return_value=1601.0):
            assert mgr.can_trigger("x") is True
