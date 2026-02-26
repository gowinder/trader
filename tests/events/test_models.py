from datetime import datetime, timezone

import pytest

from ai_trader.events.models import TriggerEvent
from ai_trader.events.config import STRATEGY_EVENT_DEFAULTS, DEFAULT_EVENT_TRIGGER_CONFIG


class TestTriggerEvent:
    def test_create_with_all_fields(self):
        ts = datetime(2026, 2, 26, 12, 0, 0, tzinfo=timezone.utc)
        evt = TriggerEvent(
            event_type="price_surge",
            description="BTC price surged 5% in 5 minutes",
            severity="high",
            key_data={"symbol": "BTCUSDT", "change_pct": 5.0},
            timestamp=ts,
        )
        assert evt.event_type == "price_surge"
        assert evt.description == "BTC price surged 5% in 5 minutes"
        assert evt.severity == "high"
        assert evt.key_data == {"symbol": "BTCUSDT", "change_pct": 5.0}
        assert evt.timestamp == ts

    def test_create_with_default_timestamp(self):
        evt = TriggerEvent(
            event_type="volume_spike",
            description="Volume spike detected",
            severity="medium",
            key_data={"symbol": "ETHUSDT"},
        )
        assert evt.timestamp is not None
        assert isinstance(evt.timestamp, datetime)

    def test_format_for_prompt_contains_required_fields(self):
        evt = TriggerEvent(
            event_type="rsi_extreme",
            description="RSI hit 85 on BTCUSDT",
            severity="high",
            key_data={"symbol": "BTCUSDT", "rsi": 85},
            timestamp=datetime(2026, 2, 26, 12, 0, 0, tzinfo=timezone.utc),
        )
        prompt_text = evt.format_for_prompt()
        assert "rsi_extreme" in prompt_text
        assert "high" in prompt_text
        assert "RSI hit 85 on BTCUSDT" in prompt_text
        assert "BTCUSDT" in prompt_text

    def test_severity_values(self):
        for sev in ("high", "medium", "low"):
            evt = TriggerEvent(
                event_type="test",
                description="test",
                severity=sev,
                key_data={},
            )
            assert evt.severity == sev


class TestStrategyEventDefaults:
    def test_all_strategies_present(self):
        assert "trend_following" in STRATEGY_EVENT_DEFAULTS
        assert "mean_reversion" in STRATEGY_EVENT_DEFAULTS
        assert "breakout" in STRATEGY_EVENT_DEFAULTS

    def test_trend_following_events(self):
        events = STRATEGY_EVENT_DEFAULTS["trend_following"]
        assert "price_surge" in events
        assert "macd_cross" in events
        assert "market_state_change" in events
        assert "position_pnl" in events

    def test_mean_reversion_events(self):
        events = STRATEGY_EVENT_DEFAULTS["mean_reversion"]
        assert "rsi_extreme" in events
        assert "bollinger_break" in events

    def test_breakout_events(self):
        events = STRATEGY_EVENT_DEFAULTS["breakout"]
        assert "volume_spike" in events
        assert "bollinger_break" in events


class TestDefaultEventTriggerConfig:
    def test_top_level_keys(self):
        assert DEFAULT_EVENT_TRIGGER_CONFIG["enabled"] is True
        assert DEFAULT_EVENT_TRIGGER_CONFIG["scan_interval_seconds"] == 30
        assert DEFAULT_EVENT_TRIGGER_CONFIG["global_cooldown_seconds"] == 300
        assert DEFAULT_EVENT_TRIGGER_CONFIG["per_event_cooldown_seconds"] == 600
        assert DEFAULT_EVENT_TRIGGER_CONFIG["reset_decision_timer"] is True

    def test_all_event_types_present(self):
        events = DEFAULT_EVENT_TRIGGER_CONFIG["events"]
        expected = [
            "price_surge", "volume_spike", "rsi_extreme",
            "macd_cross", "bollinger_break", "market_state_change",
            "position_pnl",
        ]
        for name in expected:
            assert name in events, f"Missing event config: {name}"
            assert events[name]["enabled"] is True

    def test_price_surge_has_params(self):
        cfg = DEFAULT_EVENT_TRIGGER_CONFIG["events"]["price_surge"]
        assert "atr_multiplier" in cfg
        assert "lookback_seconds" in cfg

    def test_volume_spike_has_params(self):
        cfg = DEFAULT_EVENT_TRIGGER_CONFIG["events"]["volume_spike"]
        assert "volume_multiplier" in cfg
