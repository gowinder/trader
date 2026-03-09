import pytest
from unittest.mock import AsyncMock, patch
from ai_trader.data.market_data import MarketDataManager
from ai_trader.exchange.base import BaseExchange, Ticker
from ai_trader.models.market import MarketData, Kline


@pytest.fixture
def mock_client():
    return AsyncMock(spec=BaseExchange)


@pytest.mark.asyncio
async def test_fetch_market_data(mock_client):
    """Test fetching and aggregating market data"""
    manager = MarketDataManager(mock_client)

    # Mock ticker - returns Ticker model
    mock_client.get_ticker.return_value = Ticker(
        symbol="BTCUSDT",
        last_price=10000.0,
        bid_price=9999.0,
        ask_price=10001.0,
        high_24h=10100.0,
        low_24h=9900.0,
        volume_24h=1000.0,
        change_24h=0.5,
    )

    # Mock klines - returns List[Kline]
    import time

    now = int(time.time() * 1000)
    klines_data = []
    for i in range(100):
        klines_data.append(
            Kline(
                timestamp=now + i * 60000,
                open=10000.0,
                high=10005.0,
                low=9995.0,
                close=10002.0,
                volume=100.0,
            )
        )

    mock_client.get_klines.return_value = klines_data

    market_data = await manager.get_market_data("BTCUSDT")

    assert isinstance(market_data, MarketData)
    assert market_data.symbol == "BTCUSDT"
    assert market_data.current_price == 10000.0
    assert len(market_data.klines) == 100
    assert market_data.indicators.ma99 > 0
