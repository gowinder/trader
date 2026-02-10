import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ai_trader.advisory.telegram import format_advisory_message
from ai_trader.models.advisory import AdvisoryResult, Suggestion, SuggestionType, Urgency


def test_format_advisory_message():
    result = AdvisoryResult(
        urgency=Urgency.HIGH,
        suggestions=[
            Suggestion(
                type=SuggestionType.PARAM_ADJUST,
                target="global",
                action="reduce_leverage",
                detail={"leverage_max": 5},
                reasoning="\u5e02\u573a\u6ce2\u52a8\u52a0\u5267",
                risk_note="\u53ef\u80fd\u5f71\u54cd\u6536\u76ca",
            ),
        ],
        market_summary="BTC \u5927\u5e45\u4e0b\u8dcc",
    )
    msg = format_advisory_message(result, advisory_id="test-123")
    assert "\U0001f534" in msg
    assert "BTC \u5927\u5e45\u4e0b\u8dcc" in msg
    assert "reduce_leverage" in msg
    assert "test-123" in msg


def test_format_advisory_message_no_suggestions():
    result = AdvisoryResult(
        urgency=Urgency.LOW,
        suggestions=[],
        market_summary="\u5e02\u573a\u5e73\u7a33",
    )
    msg = format_advisory_message(result, advisory_id="test-456")
    assert "\U0001f7e2" in msg
    assert "\u5f53\u524d\u65e0\u9700\u8c03\u6574" in msg


@pytest.mark.asyncio
async def test_notifier_disabled_when_no_token():
    from ai_trader.advisory.telegram import TelegramNotifier
    notifier = TelegramNotifier(bot_token="", chat_id="123")
    assert notifier.enabled is False
    result = AdvisoryResult(urgency=Urgency.LOW, suggestions=[], market_summary="test")
    msg_id = await notifier.send_advisory(result, "test-id")
    assert msg_id is None
