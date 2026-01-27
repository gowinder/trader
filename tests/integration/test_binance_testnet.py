"""Phase 2: Binance Testnet integration tests

Tests:
1. Complete trading flow (data fetch → decision → order)
2. Testnet kline data consistency with live
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from typing import Optional
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from ai_trader.config import config
from ai_trader.exchange.factory import create_exchange_client
from ai_trader.exchange.base import BaseExchange


@pytest.fixture
async def testnet_client() -> BaseExchange:
    """Create Binance testnet client"""
    # Ensure we're in testnet mode
    config.trading_mode = "testnet"
    config.testnet_exchange = "binance"

    client = create_exchange_client()
    yield client
    await client.close()


@pytest.mark.asyncio
async def test_testnet_connection(testnet_client):
    """Test basic testnet connection"""
    # Verify client is configured for testnet
    assert config.is_testnet, "Should be in testnet mode"

    # Test connection by fetching ticker
    ticker = await testnet_client.get_ticker("BTC/USDT")

    assert ticker is not None
    assert ticker.symbol == "BTC/USDT"
    assert ticker.last_price > 0
    assert ticker.bid_price > 0
    assert ticker.ask_price > 0

    print(f"✓ Testnet connection successful")
    print(f"  BTC/USDT price: ${ticker.last_price:,.2f}")


@pytest.mark.asyncio
async def test_testnet_kline_data(testnet_client):
    """Phase 2: Test Testnet K-line data consistency"""
    symbol = "BTC/USDT"
    interval = "1h"
    limit = 100

    # Fetch kline data from testnet
    klines = await testnet_client.get_klines(
        symbol=symbol,
        interval=interval,
        limit=limit
    )

    # Validate data structure
    assert len(klines) > 0, "Should have kline data"
    assert len(klines) <= limit, f"Should not exceed limit of {limit}"

    # Validate each kline
    for i, kline in enumerate(klines):
        # Basic structure validation
        assert kline["timestamp"] is not None
        assert kline["open"] > 0
        assert kline["high"] > 0
        assert kline["low"] > 0
        assert kline["close"] > 0
        assert kline["volume"] >= 0

        # OHLC consistency
        assert kline["high"] >= kline["low"], f"High must >= Low at index {i}"
        assert kline["high"] >= kline["open"], f"High must >= Open at index {i}"
        assert kline["high"] >= kline["close"], f"High must >= Close at index {i}"
        assert kline["low"] <= kline["open"], f"Low must <= Open at index {i}"
        assert kline["low"] <= kline["close"], f"Low must <= Close at index {i}"

        # Time ordering
        if i > 0:
            prev_time = klines[i-1]["timestamp"]
            curr_time = kline["timestamp"]
            assert curr_time > prev_time, f"Timestamps must be ascending at index {i}"

    print(f"✓ Kline data validation passed")
    print(f"  Received {len(klines)} klines")
    print(f"  Price range: ${klines[0]['low']:,.2f} - ${klines[-1]['high']:,.2f}")
    print(f"  Time range: {klines[0]['timestamp']} to {klines[-1]['timestamp']}")


@pytest.mark.asyncio
async def test_testnet_account_info(testnet_client):
    """Test fetching testnet account information"""
    account = await testnet_client.get_account_info()

    assert account is not None
    assert account.total_balance >= 0
    assert account.available_balance >= 0
    assert account.margin_balance >= 0

    print(f"✓ Account info retrieved")
    print(f"  Total: ${account.total_balance:,.2f}")
    print(f"  Available: ${account.available_balance:,.2f}")


@pytest.mark.asyncio
async def test_complete_trading_flow(testnet_client):
    """Phase 2: Test complete trading flow (data → decision → order simulation)

    Note: We simulate order placement without actual execution
    to avoid affecting testnet account state
    """
    symbol = "BTC/USDT"

    # Step 1: Fetch market data
    print("Step 1: Fetching market data...")
    ticker = await testnet_client.get_ticker(symbol)
    assert ticker is not None
    print(f"  ✓ Current price: ${ticker.last_price:,.2f}")

    # Step 2: Fetch klines for analysis
    print("Step 2: Fetching klines...")
    klines = await testnet_client.get_klines(symbol, "1h", 50)
    assert len(klines) > 0
    print(f"  ✓ Received {len(klines)} klines")

    # Step 3: Fetch account info
    print("Step 3: Fetching account info...")
    account = await testnet_client.get_account_info()
    assert account is not None
    print(f"  ✓ Available balance: ${account.available_balance:,.2f}")

    # Step 4: Simulate trading decision
    print("Step 4: Simulating trading decision...")
    # Calculate simple decision based on last klines
    last_close = klines[-1]["close"]
    prev_close = klines[-2]["close"]

    if last_close > prev_close:
        decision = "LONG"
        entry_price = ticker.ask_price
    else:
        decision = "SHORT"
        entry_price = ticker.bid_price

    print(f"  ✓ Decision: {decision} at ${entry_price:,.2f}")

    # Step 5: Calculate order parameters (simulation only)
    print("Step 5: Calculating order parameters...")
    position_size = 0.001  # BTC
    stop_loss_percent = 0.02  # 2%
    take_profit_percent = 0.03  # 3%

    if decision == "LONG":
        stop_loss = entry_price * (1 - stop_loss_percent)
        take_profit = entry_price * (1 + take_profit_percent)
    else:
        stop_loss = entry_price * (1 + stop_loss_percent)
        take_profit = entry_price * (1 - take_profit_percent)

    print(f"  ✓ Position size: {position_size} BTC")
    print(f"  ✓ Stop loss: ${stop_loss:,.2f}")
    print(f"  ✓ Take profit: ${take_profit:,.2f}")

    # Complete flow validation
    print("\n✓ Complete trading flow validated successfully")
    print("  [Data Fetch] → [Analysis] → [Decision] → [Order Params]")


@pytest.mark.asyncio
async def test_testnet_vs_live_data_format(testnet_client):
    """Phase 2: Compare testnet and live data format consistency

    We cannot access live API without credentials, so we validate
    that testnet data format matches expected format
    """
    symbol = "BTC/USDT"

    # Fetch data from testnet
    ticker = await testnet_client.get_ticker(symbol)
    klines = await testnet_client.get_klines(symbol, "1h", 10)

    # Expected ticker fields
    expected_ticker_fields = [
        "symbol", "last_price", "bid_price", "ask_price",
        "high_24h", "low_24h", "volume_24h", "timestamp"
    ]

    for field in expected_ticker_fields:
        assert hasattr(ticker, field), f"Ticker missing field: {field}"

    # Expected kline fields
    expected_kline_fields = [
        "timestamp", "open", "high", "low", "close", "volume"
    ]

    for kline in klines:
        for field in expected_kline_fields:
            assert field in kline, f"Kline missing field: {field}"

    print("✓ Data format validation passed")
    print("  Testnet data structure matches expected format")


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "-s"])
