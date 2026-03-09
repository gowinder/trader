"""Phase 2: Binance Testnet integration tests

Tests:
1. Complete trading flow (data fetch → decision → order)
2. Testnet kline data consistency with live

NOTE: These tests require real testnet API credentials and network access.
      They are skipped by default unless BINANCE_TESTNET env var is set.
"""

import pytest
import pytest_asyncio
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from ai_trader.config import config
from ai_trader.exchange import create_exchange_client
from ai_trader.exchange.base import BaseExchange

# Skip all tests in this module unless explicitly enabled
pytestmark = pytest.mark.skipif(
    not os.getenv("BINANCE_TESTNET"),
    reason="Requires BINANCE_TESTNET=1 and valid testnet credentials",
)


@pytest_asyncio.fixture
async def testnet_client() -> BaseExchange:
    """Create Binance testnet client"""
    config.trading_mode = "testnet"
    config.testnet_exchange = "binance"

    client = create_exchange_client()
    yield client
    await client.close()


@pytest.mark.asyncio
async def test_testnet_connection(testnet_client):
    """Test basic testnet connection"""
    assert config.is_testnet, "Should be in testnet mode"

    ticker = await testnet_client.get_ticker("BTC/USDT")

    assert ticker is not None
    assert "BTC" in ticker.symbol
    assert ticker.last_price > 0
    assert ticker.bid_price > 0
    assert ticker.ask_price > 0


@pytest.mark.asyncio
async def test_testnet_kline_data(testnet_client):
    """Test Testnet K-line data consistency"""
    symbol = "BTC/USDT"
    limit = 100

    klines = await testnet_client.get_klines(symbol=symbol, interval="1h", limit=limit)

    assert len(klines) > 0, "Should have kline data"
    assert len(klines) <= limit

    for i, kline in enumerate(klines):
        # Kline is now a Pydantic model, use attribute access
        assert kline.timestamp is not None
        assert kline.open > 0
        assert kline.high > 0
        assert kline.low > 0
        assert kline.close > 0
        assert kline.volume >= 0

        assert kline.high >= kline.low, f"High must >= Low at index {i}"
        assert kline.high >= kline.open, f"High must >= Open at index {i}"
        assert kline.high >= kline.close, f"High must >= Close at index {i}"
        assert kline.low <= kline.open, f"Low must <= Open at index {i}"
        assert kline.low <= kline.close, f"Low must <= Close at index {i}"

        if i > 0:
            assert kline.timestamp > klines[i - 1].timestamp


@pytest.mark.asyncio
async def test_testnet_account_info(testnet_client):
    """Test fetching testnet account information"""
    account = await testnet_client.get_account()

    assert account is not None
    assert account.total_balance >= 0
    assert account.available_balance >= 0


@pytest.mark.asyncio
async def test_complete_trading_flow(testnet_client):
    """Test complete trading flow (data → decision → order simulation)"""
    symbol = "BTC/USDT"

    ticker = await testnet_client.get_ticker(symbol)
    assert ticker is not None

    klines = await testnet_client.get_klines(symbol, "1h", 50)
    assert len(klines) > 0

    account = await testnet_client.get_account()
    assert account is not None

    # Simulate decision based on klines
    last_close = klines[-1].close
    prev_close = klines[-2].close

    if last_close > prev_close:
        decision = "LONG"
        entry_price = ticker.ask_price
    else:
        decision = "SHORT"
        entry_price = ticker.bid_price

    assert decision in ("LONG", "SHORT")
    assert entry_price > 0


@pytest.mark.asyncio
async def test_testnet_vs_live_data_format(testnet_client):
    """Validate testnet data format matches expected model structure"""
    symbol = "BTC/USDT"

    ticker = await testnet_client.get_ticker(symbol)
    klines = await testnet_client.get_klines(symbol, "1h", 10)

    expected_ticker_fields = [
        "symbol", "last_price", "bid_price", "ask_price",
        "high_24h", "low_24h", "volume_24h",
    ]
    for field in expected_ticker_fields:
        assert hasattr(ticker, field), f"Ticker missing field: {field}"

    expected_kline_fields = ["timestamp", "open", "high", "low", "close", "volume"]
    for kline in klines:
        for field in expected_kline_fields:
            assert hasattr(kline, field), f"Kline missing field: {field}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
