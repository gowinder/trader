import pytest
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from ai_trader.advisory.persistence import AdvisoryPersistenceService
from ai_trader.models.advisory import (
    AdvisoryResult, Suggestion, SuggestionType, Urgency, TriggerType,
)


@pytest.fixture
def mock_db():
    db = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.fetchval = AsyncMock(return_value=uuid4())
    mock_conn.execute = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=[])

    @asynccontextmanager
    async def fake_transaction():
        yield mock_conn

    db.transaction = fake_transaction
    db.pool = AsyncMock()
    db.pool.fetchrow = AsyncMock(return_value=None)
    db.pool.fetch = AsyncMock(return_value=[])
    return db


@pytest.mark.asyncio
async def test_save_advisory(mock_db):
    service = AdvisoryPersistenceService(mock_db)
    result = AdvisoryResult(
        urgency=Urgency.HIGH,
        suggestions=[
            Suggestion(
                type=SuggestionType.PARAM_ADJUST,
                target="global",
                action="reduce_leverage",
                detail={"leverage_max": 5},
                reasoning="降低风险",
                risk_note="可能影响收益",
            )
        ],
        market_summary="市场波动加剧",
    )
    advisory_id = await service.save_advisory(
        result=result,
        trigger_type=TriggerType.PRICE_VOLATILITY,
        trigger_detail={"symbol": "BTC/USDT", "change_pct": 6.5},
        llm_provider="openrouter",
        llm_model="deepseek/deepseek-chat",
        tokens_used=1500,
    )
    assert advisory_id is not None


@pytest.mark.asyncio
async def test_update_suggestion_status(mock_db):
    service = AdvisoryPersistenceService(mock_db)
    mock_db.pool.execute = AsyncMock()
    suggestion_id = uuid4()
    await service.update_suggestion_status(suggestion_id, "accepted")
    mock_db.pool.execute.assert_called_once()
