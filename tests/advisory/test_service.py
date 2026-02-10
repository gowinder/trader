import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from ai_trader.advisory.service import AdvisoryService
from ai_trader.models.advisory import AdvisoryResult, Urgency


@pytest.fixture
def mock_service_deps():
    engine = AsyncMock()
    engine.generate_advisory = AsyncMock(return_value=uuid4())
    engine.last_result = AdvisoryResult(urgency=Urgency.MEDIUM, suggestions=[], market_summary="test")

    trigger_mgr = MagicMock()
    trigger_mgr.should_run_scheduled = MagicMock(return_value=True)
    trigger_mgr.mark_scheduled_run = MagicMock()
    trigger_mgr.config = MagicMock()
    trigger_mgr.config.price_volatility_enabled = True
    trigger_mgr.config.consecutive_loss_enabled = True
    trigger_mgr.config.unrealized_pnl_enabled = True
    trigger_mgr.config.sentiment_shift_enabled = True
    trigger_mgr.price_volatility = MagicMock()
    trigger_mgr.price_volatility.check = MagicMock(return_value=None)
    trigger_mgr.consecutive_loss = MagicMock()
    trigger_mgr.consecutive_loss.check = MagicMock(return_value=None)
    trigger_mgr.unrealized_pnl = MagicMock()
    trigger_mgr.unrealized_pnl.check = MagicMock(return_value=None)
    trigger_mgr.sentiment_shift = MagicMock()
    trigger_mgr.sentiment_shift.check = MagicMock(return_value=None)

    notifier = AsyncMock()
    notifier.enabled = True
    notifier.send_advisory = AsyncMock(return_value=42)

    persistence = AsyncMock()

    return engine, trigger_mgr, notifier, persistence


@pytest.mark.asyncio
async def test_service_scheduled_run(mock_service_deps):
    engine, trigger_mgr, notifier, persistence = mock_service_deps
    service = AdvisoryService(engine=engine, trigger_manager=trigger_mgr, notifier=notifier, persistence=persistence)
    await service.check_and_run(
        symbols=["BTC/USDT:USDT"], positions=[],
        market_data={"BTC/USDT:USDT": {"current_price": 50000.0, "change_24h": -1.0}},
        sentiment=None, current_config={"stop_loss_percent": 5.0}, consecutive_losses=0,
    )
    engine.generate_advisory.assert_called_once()
    trigger_mgr.mark_scheduled_run.assert_called_once()
    notifier.send_advisory.assert_called_once()


@pytest.mark.asyncio
async def test_service_event_trigger(mock_service_deps):
    engine, trigger_mgr, notifier, persistence = mock_service_deps
    trigger_mgr.should_run_scheduled.return_value = False
    trigger_mgr.price_volatility.check.return_value = {"change_pct": -6.0}
    service = AdvisoryService(engine=engine, trigger_manager=trigger_mgr, notifier=notifier, persistence=persistence)
    await service.check_and_run(
        symbols=["BTC/USDT:USDT"], positions=[],
        market_data={"BTC/USDT:USDT": {"current_price": 47000.0, "change_24h": -6.0}},
        sentiment=None, current_config={}, consecutive_losses=0,
        price_context={"BTC/USDT:USDT": {"current": 47000.0, "previous": 50000.0}},
    )
    engine.generate_advisory.assert_called_once()


@pytest.mark.asyncio
async def test_service_no_trigger(mock_service_deps):
    engine, trigger_mgr, notifier, persistence = mock_service_deps
    trigger_mgr.should_run_scheduled.return_value = False
    service = AdvisoryService(engine=engine, trigger_manager=trigger_mgr, notifier=notifier, persistence=persistence)
    await service.check_and_run(
        symbols=["BTC/USDT:USDT"], positions=[],
        market_data={}, sentiment=None, current_config={}, consecutive_losses=0,
    )
    engine.generate_advisory.assert_not_called()
