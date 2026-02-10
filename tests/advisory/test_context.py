import pytest
from unittest.mock import AsyncMock

from ai_trader.advisory.context import AdvisoryContextBuilder


@pytest.mark.asyncio
async def test_context_builder_builds_prompt():
    mock_db = AsyncMock()
    mock_db.pool = AsyncMock()
    mock_db.pool.fetch = AsyncMock(return_value=[
        {"symbol": "BTC/USDT", "action": "open_long", "realized_pnl": -50.0,
         "pnl_percent": -2.5, "entry_price": 50000.0, "exit_price": 48750.0,
         "entry_time": None, "exit_time": None, "leverage": 5},
    ])

    builder = AdvisoryContextBuilder(db=mock_db)
    context = await builder.build(
        symbols=["BTC/USDT:USDT"],
        positions=[],
        market_data={"BTC/USDT:USDT": {"current_price": 48000.0, "change_24h": -5.2}},
        sentiment=None,
        trigger_reason="scheduled",
        current_config={"stop_loss_percent": 5.0, "leverage_max": 10},
    )

    assert "BTC/USDT" in context
    assert "scheduled" in context
    assert "-50" in context


@pytest.mark.asyncio
async def test_context_builder_no_db():
    builder = AdvisoryContextBuilder(db=None)
    context = await builder.build(
        symbols=["BTC/USDT:USDT"],
        positions=[{"symbol": "BTC/USDT", "side": "long", "entry_price": 50000, "unrealized_pnl": -100, "roi": -2.0, "leverage": 5}],
        market_data={"BTC/USDT:USDT": {"current_price": 49000.0, "change_24h": -2.0}},
        sentiment=None,
        trigger_reason="price_volatility",
        current_config={"stop_loss_percent": 5.0},
    )

    assert "无近期交易记录" in context
    assert "price_volatility" in context
    assert "long" in context
