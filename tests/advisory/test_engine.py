import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from ai_trader.advisory.engine import AdvisoryEngine
from ai_trader.models.advisory import TriggerType


@pytest.fixture
def mock_deps():
    llm = AsyncMock()
    llm.chat = AsyncMock(return_value={
        "urgency": "medium",
        "market_summary": "市场平稳",
        "suggestions": [
            {
                "type": "param_adjust",
                "target": "global",
                "action": "reduce_leverage",
                "detail": {"leverage_max": 5},
                "reasoning": "波动加剧，降低杠杆",
                "risk_note": "可能影响收益",
            }
        ],
    })
    llm.provider_name = "openrouter"
    llm.model_name = "deepseek/deepseek-chat"

    persistence = AsyncMock()
    persistence.create_running_advisory = AsyncMock(return_value=uuid4())
    persistence.complete_advisory = AsyncMock()
    persistence.fail_advisory = AsyncMock()
    persistence.save_advisory = AsyncMock(return_value=uuid4())

    context_builder = AsyncMock()
    context_builder.build = AsyncMock(return_value="test context")

    return llm, persistence, context_builder


@pytest.mark.asyncio
async def test_engine_generate_advisory(mock_deps):
    llm, persistence, context_builder = mock_deps
    engine = AdvisoryEngine(llm_client=llm, persistence=persistence, context_builder=context_builder)
    advisory_id = await engine.generate_advisory(
        trigger_type=TriggerType.SCHEDULED,
        trigger_detail={},
        symbols=["BTC/USDT:USDT"],
        positions=[],
        market_data={},
        sentiment=None,
        current_config={},
    )
    assert advisory_id is not None
    llm.chat.assert_called_once()
    persistence.create_running_advisory.assert_called_once()
    persistence.complete_advisory.assert_called_once()
    assert engine.last_result is not None
    assert engine.last_result.urgency.value == "medium"


@pytest.mark.asyncio
async def test_engine_handles_llm_error(mock_deps):
    llm, persistence, context_builder = mock_deps
    llm.chat.side_effect = Exception("LLM timeout")
    engine = AdvisoryEngine(llm_client=llm, persistence=persistence, context_builder=context_builder)
    advisory_id = await engine.generate_advisory(
        trigger_type=TriggerType.SCHEDULED,
        trigger_detail={},
        symbols=["BTC/USDT:USDT"],
        positions=[],
        market_data={},
        sentiment=None,
        current_config={},
    )
    assert advisory_id is None


@pytest.mark.asyncio
async def test_engine_no_persistence(mock_deps):
    llm, _, context_builder = mock_deps
    engine = AdvisoryEngine(llm_client=llm, persistence=None, context_builder=context_builder)
    advisory_id = await engine.generate_advisory(
        trigger_type=TriggerType.SCHEDULED,
        trigger_detail={},
        symbols=["BTC/USDT:USDT"],
        positions=[],
        market_data={},
        sentiment=None,
        current_config={},
    )
    assert advisory_id is None
    assert engine.last_result is not None
