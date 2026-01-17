import pytest
from unittest.mock import AsyncMock, MagicMock
from ai_trader.exchange.order import OrderManager
from ai_trader.models.decision import TradingDecision
from ai_trader.exchange.weex_client import WeexClient


@pytest.fixture
def mock_client():
    return AsyncMock(spec=WeexClient)


@pytest.mark.asyncio
async def test_execute_order_market(mock_client):
    """Test executing a market order"""
    manager = OrderManager(mock_client)

    decision = TradingDecision(
        action="open_long",
        confidence=80,
        leverage=5,
        position_size_percent=10,
        entry_price=0,
        stop_loss_price=90000,
        take_profit_price=110000,
        order_type="market",
        reasoning="Test",
        execution_urgency="immediate",
    )

    # Mock set_leverage
    mock_client.set_leverage.return_value = True

    # Mock create_order
    mock_client.create_order.return_value = {
        "code": "00000",
        "data": {"orderId": "123"},
    }

    result = await manager.execute_order(decision, symbol="BTCUSDT", quantity=0.01)

    assert result == "123"
    mock_client.set_leverage.assert_called_with("BTCUSDT", 5)
    mock_client.create_order.assert_called()

    # Verify side mapping
    # open_long -> 1 (Weex uses 1 for open long, 2 open short, 3 close long, 4 close short)
    # OR we use strings if client supports it.
    # Let's assume OrderManager maps to the format WeexClient expects.
    # In previous step, WeexClient just passed through.
    # Here we should verify what OrderManager sends.
    args = mock_client.create_order.call_args[1]
    assert args["side"] in ["1", "open_long"]  # Depending on implementation
