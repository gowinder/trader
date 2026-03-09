"""Tests for TriggerEvent model."""

import json
from datetime import datetime, timezone

from ai_trader.events.models import TriggerEvent


class TestTriggerEvent:

    def test_trigger_event_creation(self):
        ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ev = TriggerEvent(
            event_type="price_spike",
            description="BTC surged 5%",
            severity="high",
            key_data={"change": 0.05},
            timestamp=ts,
        )
        assert ev.event_type == "price_spike"
        assert ev.description == "BTC surged 5%"
        assert ev.severity == "high"
        assert ev.key_data == {"change": 0.05}
        assert ev.timestamp == ts

    def test_trigger_event_default_timestamp(self):
        before = datetime.now(timezone.utc)
        ev = TriggerEvent(
            event_type="volume_surge",
            description="Volume up",
            severity="medium",
            key_data={},
        )
        after = datetime.now(timezone.utc)
        assert before <= ev.timestamp <= after

    def test_format_for_prompt_basic(self):
        ts = datetime(2024, 6, 15, 8, 30, 0, tzinfo=timezone.utc)
        ev = TriggerEvent(
            event_type="price_spike",
            description="BTC surged 5%",
            severity="high",
            key_data={"change": 0.05},
            timestamp=ts,
        )
        result = ev.format_for_prompt()
        assert "[Event] price_spike | severity=high" in result
        assert "description: BTC surged 5%" in result
        assert '"change": 0.05' in result
        assert ts.isoformat() in result

    def test_format_for_prompt_with_chinese(self):
        ev = TriggerEvent(
            event_type="news",
            description="breaking news",
            severity="low",
            key_data={"headline": "比特币突破新高"},
        )
        result = ev.format_for_prompt()
        assert "比特币突破新高" in result

    def test_format_for_prompt_with_nested_data(self):
        ev = TriggerEvent(
            event_type="composite",
            description="multi-signal",
            severity="medium",
            key_data={
                "signals": {"rsi": 75, "macd": "bullish"},
                "levels": [100, 200],
            },
        )
        result = ev.format_for_prompt()
        parsed = json.loads(result.split("key_data: ")[1].split("\n")[0])
        assert parsed["signals"]["rsi"] == 75
        assert parsed["levels"] == [100, 200]
