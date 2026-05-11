import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from ai_trader.exchange.ccxt_spot_adapter import CCXTSpotAdapter
from ai_trader.exchange.base import OrderSide, OrderType


@pytest.mark.asyncio
async def test_spot_adapter_init():
    """Test that spot adapter creates exchange with defaultType=spot"""
    mock_exchange = MagicMock()
    mock_exchange.id = "kraken"
    adapter = CCXTSpotAdapter(mock_exchange)
    assert adapter._exchange is mock_exchange


@pytest.mark.asyncio
async def test_spot_adapter_set_leverage_noop():
    """set_leverage should be a no-op for spot trading"""
    mock_exchange = MagicMock()
    mock_exchange.id = "kraken"
    adapter = CCXTSpotAdapter(mock_exchange)

    result = await adapter.set_leverage("AAPLx/USD", 5)
    assert result is True
    # Should NOT call exchange.set_leverage
    mock_exchange.set_leverage.assert_not_called()


@pytest.mark.asyncio
async def test_spot_adapter_get_positions_from_balance():
    """get_positions should derive positions from spot balance"""
    mock_exchange = MagicMock()
    mock_exchange.id = "kraken"
    mock_exchange.fetch_balance = AsyncMock(return_value={
        "AAPLx": {"total": 10.0, "free": 10.0},
        "USD": {"total": 1000.0, "free": 500.0},
    })
    mock_exchange.fetch_ticker = AsyncMock(return_value={"last": 150.0})

    adapter = CCXTSpotAdapter(mock_exchange)
    positions = await adapter.get_positions("AAPLx/USD")

    assert len(positions) == 1
    assert positions[0].symbol == "AAPLx/USD"
    assert positions[0].side == "long"
    assert positions[0].size == 10.0
    assert positions[0].mark_price == 150.0
    assert positions[0].leverage == 1
    assert positions[0].margin_mode == "spot"


@pytest.mark.asyncio
async def test_spot_adapter_get_account_usd():
    """get_account should use USD balance for spot trading"""
    mock_exchange = MagicMock()
    mock_exchange.id = "kraken"
    mock_exchange.fetch_balance = AsyncMock(return_value={
        "USD": {"total": 5000.0, "free": 3000.0, "used": 2000.0},
    })

    adapter = CCXTSpotAdapter(mock_exchange)
    account = await adapter.get_account()

    assert account.total_equity == 5000.0
    assert account.available_balance == 3000.0
    assert account.margin_used == 2000.0


@pytest.mark.asyncio
async def test_spot_adapter_create_order_no_reduce_only():
    """Spot orders should not have reduceOnly parameter"""
    mock_exchange = MagicMock()
    mock_exchange.id = "kraken"
    mock_exchange.create_order = AsyncMock(return_value={"id": "order123", "status": "open"})

    adapter = CCXTSpotAdapter(mock_exchange)
    result = await adapter.create_order(
        symbol="AAPLx/USD",
        side=OrderSide.OPEN_LONG,
        order_type=OrderType.MARKET,
        size=1.0,
    )

    assert result["code"] == "00000"
    assert result["data"]["orderId"] == "order123"
    # Verify create_order was called
    mock_exchange.create_order.assert_called_once()
    call_kwargs = mock_exchange.create_order.call_args
    # reduceOnly should NOT be in params for spot
    params = call_kwargs.kwargs.get("params", {})
    assert "reduceOnly" not in params
