import pytest
from unittest.mock import AsyncMock, patch
from ai_trader.data.market_data import MarketDataManager
from ai_trader.exchange.weex_client import WeexClient
from ai_trader.models.market import MarketData


@pytest.fixture
def mock_client():
    return AsyncMock(spec=WeexClient)


@pytest.mark.asyncio
async def test_fetch_market_data(mock_client):
    """Test fetching and aggregating market data"""
    manager = MarketDataManager(mock_client)

    # Mock ticker
    mock_client.get_ticker.return_value = {
        "code": "00000",
        "data": {
            "last": "10000.0",
            "high24h": "10100",
            "low24h": "9900",
            "vol24h": "1000",
        },
    }

    # Mock klines
    # Need enough klines for indicators (>=99)
    # Generate 100 mock klines
    import time

    now = int(time.time() * 1000)
    klines_data = []
    for i in range(100):
        # [timestamp, open, high, low, close, volume, ...]
        klines_data.append(
            [str(now + i * 60000), "10000", "10005", "9995", "10002", "100"]
        )

    mock_client.get_klines.return_value = klines_data

    market_data = await manager.get_market_data("BTCUSDT")

    assert isinstance(market_data, MarketData)
    assert market_data.symbol == "BTCUSDT"
    assert market_data.current_price == 10000.0
    assert len(market_data.klines) == 100
    assert market_data.indicators.ma99 > 0
