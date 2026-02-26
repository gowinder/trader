"""Tests for CooldownManager."""

from unittest.mock import patch

from ai_trader.events.cooldown import CooldownManager


class TestCooldownManager:
    """CooldownManager test suite."""

    def test_can_trigger_initially(self):
        """Fresh manager allows triggering any event."""
        mgr = CooldownManager(global_cooldown=300, per_event_cooldown=600)
        assert mgr.can_trigger("price_spike") is True
        assert mgr.can_trigger("volume_surge") is True

    def test_global_cooldown_blocks(self):
        """After trigger, other events blocked by global cooldown."""
        mgr = CooldownManager(global_cooldown=300, per_event_cooldown=600)

        with patch("ai_trader.events.cooldown.time.monotonic", return_value=1000.0):
            mgr.record_trigger("price_spike")

        # 100s later — still within 300s global cooldown
        with patch("ai_trader.events.cooldown.time.monotonic", return_value=1100.0):
            assert mgr.can_trigger("volume_surge") is False
            assert mgr.can_trigger("price_spike") is False

        # 301s later — global cooldown expired, but per-event still active for price_spike
        with patch("ai_trader.events.cooldown.time.monotonic", return_value=1301.0):
            assert mgr.can_trigger("volume_surge") is True
            assert mgr.can_trigger("price_spike") is False  # per-event 600s not yet passed

    def test_per_event_cooldown_blocks(self):
        """Same event blocked by per-event cooldown; different event OK when global_cooldown=0."""
        mgr = CooldownManager(global_cooldown=0, per_event_cooldown=600)

        with patch("ai_trader.events.cooldown.time.monotonic", return_value=1000.0):
            mgr.record_trigger("price_spike")

        with patch("ai_trader.events.cooldown.time.monotonic", return_value=1100.0):
            # Same event still in per-event cooldown
            assert mgr.can_trigger("price_spike") is False
            # Different event not affected (global cooldown is 0)
            assert mgr.can_trigger("volume_surge") is True

    def test_cooldown_expires(self):
        """When cooldowns are 0, triggering is immediately allowed again."""
        mgr = CooldownManager(global_cooldown=0, per_event_cooldown=0)

        with patch("ai_trader.events.cooldown.time.monotonic", return_value=1000.0):
            mgr.record_trigger("price_spike")

        # Same timestamp — cooldown=0 means elapsed >= 0 is always true
        with patch("ai_trader.events.cooldown.time.monotonic", return_value=1000.0):
            assert mgr.can_trigger("price_spike") is True
            assert mgr.can_trigger("volume_surge") is True

    def test_reset(self):
        """Reset clears all cooldowns."""
        mgr = CooldownManager(global_cooldown=300, per_event_cooldown=600)

        with patch("ai_trader.events.cooldown.time.monotonic", return_value=1000.0):
            mgr.record_trigger("price_spike")

        with patch("ai_trader.events.cooldown.time.monotonic", return_value=1050.0):
            assert mgr.can_trigger("price_spike") is False

        mgr.reset()

        with patch("ai_trader.events.cooldown.time.monotonic", return_value=1050.0):
            assert mgr.can_trigger("price_spike") is True
            assert mgr.can_trigger("volume_surge") is True
