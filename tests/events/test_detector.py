"""Tests for EventDetector main orchestrator."""

from unittest.mock import MagicMock

import pytest

from ai_trader.events.config import DEFAULT_EVENT_TRIGGER_CONFIG, STRATEGY_EVENT_DEFAULTS
from ai_trader.events.detector import EventDetector, format_trigger_context
from ai_trader.events.models import TriggerEvent

from .conftest import _make_indicators, _make_kline, _make_market_data


# ── Tests ────────────────────────────────────────────────────────────


class TestEventDetectorInit:
    def test_init(self):
        """EventDetector creates successfully with default config."""
        det = EventDetector(
            event_config=DEFAULT_EVENT_TRIGGER_CONFIG,
            enabled_strategies=["trend_following"],
        )
        assert det is not None


class TestScanNoEvents:
    def test_scan_no_events_normal_market(self):
        """Normal market conditions return empty list."""
        det = EventDetector(
            event_config=DEFAULT_EVENT_TRIGGER_CONFIG,
            enabled_strategies=["trend_following"],
        )
        md = _make_market_data(current_price=100.0)
        events = det.scan("BTCUSDT", md, None, market_state=None)
        assert events == []


class TestStrategyFiltering:
    def test_scan_filters_by_strategy(self):
        """trend_following doesn't include rsi_extreme -> RSI=20 should NOT trigger."""
        det = EventDetector(
            event_config=DEFAULT_EVENT_TRIGGER_CONFIG,
            enabled_strategies=["trend_following"],
        )
        # RSI=20 is oversold, would trigger rsi_extreme
        # But trend_following does not subscribe to rsi_extreme
        md = _make_market_data(
            current_price=100.0,
            indicators=_make_indicators(rsi=20.0),
        )
        events = det.scan("BTCUSDT", md, None, market_state=None)
        rsi_events = [e for e in events if e.event_type == "rsi_extreme"]
        assert len(rsi_events) == 0

    def test_scan_allows_strategy_relevant_event(self):
        """mean_reversion subscribes to rsi_extreme -> RSI=20 SHOULD trigger."""
        det = EventDetector(
            event_config=DEFAULT_EVENT_TRIGGER_CONFIG,
            enabled_strategies=["mean_reversion"],
        )
        md = _make_market_data(
            current_price=100.0,
            indicators=_make_indicators(rsi=20.0),
        )
        events = det.scan("BTCUSDT", md, None, market_state=None)
        rsi_events = [e for e in events if e.event_type == "rsi_extreme"]
        assert len(rsi_events) == 1
        assert rsi_events[0].event_type == "rsi_extreme"

    def test_scan_multi_strategy_union(self):
        """Multiple strategies get union of event types."""
        det = EventDetector(
            event_config=DEFAULT_EVENT_TRIGGER_CONFIG,
            enabled_strategies=["trend_following", "mean_reversion"],
        )
        active = det._get_active_event_types()
        # trend_following has macd_cross; mean_reversion has rsi_extreme
        assert "macd_cross" in active
        assert "rsi_extreme" in active


class TestCooldown:
    def test_cooldown_prevents_duplicate(self):
        """First scan triggers, second scan within cooldown returns empty."""
        det = EventDetector(
            event_config=DEFAULT_EVENT_TRIGGER_CONFIG,
            enabled_strategies=["mean_reversion"],
        )
        md = _make_market_data(
            current_price=100.0,
            indicators=_make_indicators(rsi=20.0),
        )
        events1 = det.scan("BTCUSDT", md, None, market_state=None)
        rsi_events1 = [e for e in events1 if e.event_type == "rsi_extreme"]
        assert len(rsi_events1) == 1

        # Second scan immediately (within cooldown)
        events2 = det.scan("BTCUSDT", md, None, market_state=None)
        assert events2 == []


class TestDisabledEvent:
    def test_disabled_event_not_triggered(self):
        """Event with enabled=False in config doesn't trigger."""
        config = {
            **DEFAULT_EVENT_TRIGGER_CONFIG,
            "events": {
                **DEFAULT_EVENT_TRIGGER_CONFIG["events"],
                "rsi_extreme": {
                    **DEFAULT_EVENT_TRIGGER_CONFIG["events"]["rsi_extreme"],
                    "enabled": False,
                },
            },
        }
        det = EventDetector(
            event_config=config,
            enabled_strategies=["mean_reversion"],
        )
        md = _make_market_data(
            current_price=100.0,
            indicators=_make_indicators(rsi=20.0),
        )
        events = det.scan("BTCUSDT", md, None, market_state=None)
        rsi_events = [e for e in events if e.event_type == "rsi_extreme"]
        assert len(rsi_events) == 0


class TestFormatTriggerContext:
    def test_format_basic(self):
        """format_trigger_context produces expected text."""
        event = TriggerEvent(
            event_type="rsi_extreme",
            description="RSI oversold",
            severity="medium",
            key_data={"rsi": 20.0},
        )
        text = format_trigger_context(
            events=[event],
            active_strategies=["mean_reversion"],
        )
        assert "市场事件触发" in text
        assert "rsi_extreme" in text
        assert "mean_reversion" in text
