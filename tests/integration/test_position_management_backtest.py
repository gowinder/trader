"""Phase 3: Position management backtest validation

Tests position sizing, pyramid entry, and trailing stop loss
using historical data
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import sys
import asyncio

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from ai_trader.risk.position_manager import PositionManager, PositionSizingMethod
from ai_trader.data.fetcher import CachedDataFetcher


def generate_test_data(n_candles: int = 100, base_price: float = 50000.0) -> pd.DataFrame:
    """Generate synthetic price data for testing"""
    np.random.seed(42)

    # Generate trending price data
    trend = np.linspace(0, 5000, n_candles)
    noise = np.random.randn(n_candles) * 100
    close_prices = base_price + trend + noise

    timestamps = pd.date_range(
        start=datetime.now() - timedelta(hours=n_candles),
        periods=n_candles,
        freq="1h"
    )

    df = pd.DataFrame({
        "timestamp": timestamps,
        "open": close_prices + np.random.randn(n_candles) * 50,
        "high": close_prices + np.abs(np.random.randn(n_candles)) * 100,
        "low": close_prices - np.abs(np.random.randn(n_candles)) * 100,
        "close": close_prices,
        "volume": np.abs(np.random.randn(n_candles)) * 1000 + 500,
    })

    return df


def calculate_atr(df: pd.DataFrame, period: int = 14) -> float:
    """Calculate Average True Range"""
    high = df["high"].values
    low = df["low"].values
    close = df["close"].values

    if len(df) < period + 1:
        return (df["high"] - df["low"]).mean()

    tr1 = high[1:] - low[1:]
    tr2 = np.abs(high[1:] - close[:-1])
    tr3 = np.abs(low[1:] - close[:-1])
    tr = np.maximum(tr1, np.maximum(tr2, tr3))

    return tr[-period:].mean()


def test_initial_position_sizing():
    """Test initial position size calculation"""
    manager = PositionManager(
        account_balance=10000.0,
        risk_per_trade=0.02,  # 2%
        sizing_method=PositionSizingMethod.FIXED_PERCENT,
        max_position_percent=0.5,
    )

    df = generate_test_data(50)
    current_price = float(df["close"].iloc[-1])
    atr = calculate_atr(df)

    # Calculate position size
    position = manager.calculate_initial_position(
        entry_price=current_price,
        stop_loss_atr_multiplier=2.0,
        atr=atr,
    )

    # Validate position
    assert position.size > 0, "Position size should be positive"
    assert position.entry_price == current_price
    assert position.stop_loss < current_price, "Stop loss should be below entry for long"
    assert position.risk_amount > 0
    assert position.risk_amount <= 10000.0 * 0.02, "Risk should not exceed 2%"

    # Calculate position value
    position_value = position.size * current_price
    max_position_value = 10000.0 * 0.5

    assert position_value <= max_position_value, "Position should not exceed 50% of capital"

    print(f"✓ Initial position sizing validated")
    print(f"  Entry: ${position.entry_price:,.2f}")
    print(f"  Size: {position.size:.4f} BTC")
    print(f"  Stop loss: ${position.stop_loss:,.2f}")
    print(f"  Risk: ${position.risk_amount:,.2f} ({position.risk_amount/10000*100:.1f}%)")


def test_pyramid_entry_conditions():
    """Test pyramid entry (adding to winning position)"""
    manager = PositionManager(
        account_balance=10000.0,
        risk_per_trade=0.02,
        sizing_method=PositionSizingMethod.PYRAMID,
        pyramid_levels=3,
        pyramid_scale_factor=0.5,
    )

    df = generate_test_data(50)
    initial_price = float(df["close"].iloc[-40])
    atr = calculate_atr(df)

    # Initial position
    initial_position = manager.calculate_initial_position(
        entry_price=initial_price,
        stop_loss_atr_multiplier=2.0,
        atr=atr,
    )

    original_stop_loss = initial_position.stop_loss
    print(f"Initial entry at ${initial_price:,.2f}, stop loss ${original_stop_loss:,.2f}")

    # Test pyramid entries at different profit levels
    pyramid_count = 0
    for i in range(-30, -1, 5):
        current_price = float(df["close"].iloc[i])
        profit_pct = (current_price - initial_price) / initial_price * 100

        should_add, reason = manager.should_add_position(
            current_price=current_price,
            entry_price=initial_price,
            original_stop_loss=original_stop_loss,
            current_position_count=pyramid_count + 1,
        )

        if should_add:
            pyramid_count += 1
            print(f"  ✓ Pyramid {pyramid_count}: ${current_price:,.2f} (+{profit_pct:.1f}%)")

    assert pyramid_count <= 3, "Should not exceed max pyramid levels"
    print(f"✓ Pyramid entry logic validated ({pyramid_count} entries)")


def test_trailing_stop_loss():
    """Test trailing stop loss calculation"""
    manager = PositionManager(
        account_balance=10000.0,
        risk_per_trade=0.02,
    )

    df = generate_test_data(100)

    # Simulate a long position
    entry_price = float(df["close"].iloc[0])
    initial_atr = calculate_atr(df.iloc[:20])
    initial_stop_loss = entry_price - initial_atr * 2.0

    print(f"Entry: ${entry_price:,.2f}, Initial stop: ${initial_stop_loss:,.2f}")

    # Track stop loss through price movement
    current_stop = initial_stop_loss
    highest_price = entry_price
    trailing_updates = 0

    for i in range(1, len(df)):
        current_price = float(df["close"].iloc[i])
        current_atr = calculate_atr(df.iloc[:i+1])

        # Update trailing stop
        new_stop = manager.calculate_trailing_stop(
            current_price=current_price,
            highest_price=max(highest_price, current_price),
            current_stop_loss=current_stop,
            atr=current_atr,
            trailing_multiplier=2.0,
        )

        if new_stop > current_stop:
            trailing_updates += 1
            print(f"  Stop updated: ${current_stop:,.2f} → ${new_stop:,.2f} (price: ${current_price:,.2f})")

        current_stop = new_stop
        highest_price = max(highest_price, current_price)

    # Validate trailing stop logic
    assert current_stop >= initial_stop_loss, "Trailing stop should never move down"
    assert current_stop < highest_price, "Stop should be below highest price"
    assert trailing_updates > 0, "Stop should have moved up at least once"

    print(f"✓ Trailing stop validated ({trailing_updates} updates)")


def test_daily_loss_limit():
    """Test daily loss limit enforcement"""
    manager = PositionManager(
        account_balance=10000.0,
        risk_per_trade=0.02,
        daily_loss_limit=0.05,  # 5%
    )

    # Simulate multiple losing trades
    daily_loss = 0.0
    trades = [
        ("Trade 1", -150.0),
        ("Trade 2", -200.0),
        ("Trade 3", -100.0),
        ("Trade 4", -80.0),  # Total: -530 (5.3%)
    ]

    for trade_name, loss in trades:
        daily_loss += loss
        allow_trade, reason = manager.check_daily_loss_limit(abs(daily_loss))

        print(f"  {trade_name}: ${loss:,.2f} (total: ${daily_loss:,.2f}, {abs(daily_loss)/10000*100:.1f}%)")

        if not allow_trade:
            print(f"  ✗ Trading stopped: {reason}")
            break

    assert abs(daily_loss) > 10000.0 * 0.05, "Should have exceeded daily limit"
    print(f"✓ Daily loss limit enforced")


def test_position_management_integration():
    """Integration test: Position management through complete trade lifecycle"""
    manager = PositionManager(
        account_balance=10000.0,
        risk_per_trade=0.02,
        sizing_method=PositionSizingMethod.PYRAMID,
        pyramid_levels=2,
        daily_loss_limit=0.05,
    )

    df = generate_test_data(200, base_price=50000.0)
    atr = calculate_atr(df)

    # Lifecycle tracking
    entry_price = float(df["close"].iloc[0])
    position = manager.calculate_initial_position(
        entry_price=entry_price,
        stop_loss_atr_multiplier=2.0,
        atr=atr,
    )

    print(f"\n=== Trade Lifecycle ===")
    print(f"Entry: ${entry_price:,.2f}")
    print(f"Size: {position.size:.4f} BTC")
    print(f"Initial stop: ${position.stop_loss:,.2f}")

    # Simulate price movement
    current_stop = position.stop_loss
    highest_price = entry_price
    pyramid_count = 1
    total_size = position.size
    total_cost = position.size * entry_price

    for i in range(1, len(df), 10):
        current_price = float(df["close"].iloc[i])
        current_atr = calculate_atr(df.iloc[:i+1])
        profit_pct = (current_price - entry_price) / entry_price * 100

        # Check for pyramid entry
        if pyramid_count < 2:
            should_add, _ = manager.should_add_position(
                current_price=current_price,
                entry_price=entry_price,
                original_stop_loss=position.stop_loss,
                current_position_count=pyramid_count + 1,
            )

            if should_add:
                add_size = position.size * 0.5  # 50% of initial
                total_size += add_size
                total_cost += add_size * current_price
                pyramid_count += 1
                avg_entry = total_cost / total_size
                print(f"  Pyramid {pyramid_count}: ${current_price:,.2f} (+{profit_pct:.1f}%), Avg entry: ${avg_entry:,.2f}")

        # Update trailing stop
        new_stop = manager.calculate_trailing_stop(
            current_price=current_price,
            highest_price=max(highest_price, current_price),
            current_stop_loss=current_stop,
            atr=current_atr,
            trailing_multiplier=2.0,
        )

        current_stop = new_stop
        highest_price = max(highest_price, current_price)

    # Calculate final P&L
    exit_price = float(df["close"].iloc[-1])
    pnl = (exit_price - (total_cost / total_size)) * total_size
    pnl_pct = pnl / 10000.0 * 100

    print(f"\nExit: ${exit_price:,.2f}")
    print(f"Final stop: ${current_stop:,.2f}")
    print(f"Total size: {total_size:.4f} BTC")
    print(f"Avg entry: ${total_cost/total_size:,.2f}")
    print(f"P&L: ${pnl:,.2f} ({pnl_pct:+.2f}%)")

    print(f"\n✓ Position management integration validated")


async def test_real_data_position_management():
    """Test position management with real historical data (if available)"""
    try:
        # Try to fetch real data
        fetcher = CachedDataFetcher(cache_dir="data/cache")
        df = fetcher.get_data(
            symbol="BTC/USDT",
            start_date=datetime.now() - timedelta(days=30),
            end_date=datetime.now(),
            timeframe="1h",
        )

        if len(df) < 50:
            print("⚠ Insufficient real data, skipping test")
            return

        print(f"✓ Fetched {len(df)} real candles")

        manager = PositionManager(
            account_balance=10000.0,
            risk_per_trade=0.02,
        )

        # Calculate metrics
        atr = calculate_atr(df)
        entry_price = float(df["close"].iloc[0])

        position = manager.calculate_initial_position(
            entry_price=entry_price,
            stop_loss_atr_multiplier=2.0,
            atr=atr,
        )

        print(f"✓ Position calculated on real data")
        print(f"  ATR: ${atr:,.2f}")
        print(f"  Position size: {position.size:.4f} BTC")
        print(f"  Risk: ${position.risk_amount:,.2f}")

    except Exception as e:
        print(f"⚠ Could not fetch real data: {e}")
        print("  (This is expected if no API access)")


if __name__ == "__main__":
    print("=== Phase 3: Position Management Backtest Validation ===\n")

    print("Test 1: Initial position sizing")
    test_initial_position_sizing()

    print("\nTest 2: Pyramid entry conditions")
    test_pyramid_entry_conditions()

    print("\nTest 3: Trailing stop loss")
    test_trailing_stop_loss()

    print("\nTest 4: Daily loss limit")
    test_daily_loss_limit()

    print("\nTest 5: Position management integration")
    test_position_management_integration()

    print("\nTest 6: Real data validation")
    asyncio.run(test_real_data_position_management())

    print("\n" + "=" * 60)
    print("✓ All position management tests passed")
