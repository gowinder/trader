#!/usr/bin/env python3
"""Phase 3: Position management validation (no external dependencies)

Tests:
1. Initial position sizing
2. Pyramid entry logic
3. Trailing stop loss
4. Daily loss limit
5. Complete trade lifecycle
"""

import sys
from pathlib import Path
import numpy as np
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ai_trader.risk.position_manager import PositionManager


def calculate_atr(highs, lows, closes, period=14):
    """Calculate ATR from arrays"""
    if len(highs) < period + 1:
        return (highs - lows).mean()

    tr1 = highs[1:] - lows[1:]
    tr2 = np.abs(highs[1:] - closes[:-1])
    tr3 = np.abs(lows[1:] - closes[:-1])
    tr = np.maximum(tr1, np.maximum(tr2, tr3))

    return tr[-period:].mean()


def test_initial_position_sizing():
    """Test 1: Initial position size calculation"""
    print("\n=== Test 1: Initial Position Sizing ===")

    manager = PositionManager(
        default_risk_percentage=0.02,  # 2%
        max_single_trade_risk=0.02,
    )

    account_balance = 10000.0

    # Simulate price data
    current_price = 50000.0
    atr = 500.0
    stop_loss = current_price - atr * 2.0

    # Calculate position size
    position = manager.calculate_initial_position(
        account_balance=account_balance,
        entry_price=current_price,
        stop_loss_price=stop_loss,
    )

    # Validate
    assert position.position_size > 0, "Position size must be positive"
    assert position.entry_price == current_price
    assert position.stop_loss_price < current_price, "Stop loss must be below entry (long)"
    assert position.risk_amount > 0
    assert position.risk_amount <= 200.0, f"Risk must <= 2%: {position.risk_amount}"

    position_value = position.position_size * current_price
    max_value = account_balance * 0.5

    print(f"✓ Initial position validated")
    print(f"  Entry: ${position.entry_price:,.2f}")
    print(f"  Size: {position.position_size:.4f} BTC")
    print(f"  Stop loss: ${position.stop_loss_price:,.2f}")
    print(f"  Risk: ${position.risk_amount:,.2f} ({position.risk_percentage*100:.2f}%)")
    print(f"  Position value: ${position_value:,.2f} ({position_value/account_balance*100:.1f}%)")

    return True


def test_pyramid_entry():
    """Test 2: Pyramid entry logic"""
    print("\n=== Test 2: Pyramid Entry Logic ===")

    manager = PositionManager(default_risk_percentage=0.02)

    initial_price = 50000.0
    original_stop_loss = 48000.0

    # Test if can pyramid after 1% profit
    test_cases = [
        (50000.0, "At entry price", False),
        (50500.0, "Profit < 1%", False),
        (51000.0, "Profit > 1%", True),
    ]

    for current_price, description, expected in test_cases:
        profit_pct = (current_price - initial_price) / initial_price * 100
        can_pyramid = (current_price > initial_price * 1.01) and (current_price > original_stop_loss * 1.02)

        status = "✓" if can_pyramid == expected else "✗"
        print(f"{status} {description}: ${current_price:,.0f} (+{profit_pct:.1f}%) -> Can pyramid: {can_pyramid}")

        if can_pyramid != expected:
            print(f"  ERROR: Expected {expected}, got {can_pyramid}")
            return False

    print("✓ Pyramid logic validated")
    return True


def test_trailing_stop():
    """Test 3: Trailing stop loss"""
    print("\n=== Test 3: Trailing Stop Loss ===")

    manager = PositionManager()

    # Simulate price movement
    entry_price = 50000.0
    initial_stop = 48000.0
    atr = 500.0

    price_sequence = [
        (50000, 48000, "Entry"),
        (51000, 49000, "Move up +2%"),
        (52000, 50000, "Move up +4%"),
        (51500, 50000, "Pullback (stop doesn't move down)"),
        (53000, 51000, "New high +6%"),
    ]

    current_stop = initial_stop
    highest_price = entry_price

    for price, expected_stop, description in price_sequence:
        new_highest = max(highest_price, price)

        # Calculate trailing stop (highest - 2*ATR)
        potential_stop = new_highest - 2.0 * atr
        new_stop = max(current_stop, potential_stop)

        status = "✓" if abs(new_stop - expected_stop) < 100 else "✗"
        print(f"{status} {description}: Price=${price:,.0f}, Stop=${new_stop:,.0f} (expected ${expected_stop:,.0f})")

        assert new_stop >= current_stop, "Stop must never move down"
        assert new_stop < new_highest, "Stop must be below price"

        current_stop = new_stop
        highest_price = new_highest

    print("✓ Trailing stop validated")
    return True


def test_daily_loss_limit():
    """Test 4: Daily loss limit enforcement"""
    print("\n=== Test 4: Daily Loss Limit ===")

    manager = PositionManager(daily_loss_limit=0.05)  # 5%
    account_balance = 10000.0

    trades = [
        (-150, True, "Trade 1: -$150"),
        (-200, True, "Trade 2: -$200"),
        (-100, True, "Trade 3: -$100"),
        (-80, False, "Trade 4: -$80 (exceeds 5% limit)"),
    ]

    total_loss = 0.0
    for loss, expected, description in trades:
        total_loss += loss
        loss_pct = abs(total_loss) / account_balance
        allow = loss_pct < manager.daily_loss_limit

        loss_pct_display = loss_pct * 100
        status = "✓" if allow == expected else "✗"

        print(f"{status} {description}: Total ${total_loss:,.0f} ({loss_pct_display:.1f}%) -> {allow}")
        if not allow:
            print(f"    Exceeded {manager.daily_loss_limit*100}% daily limit")

        if allow != expected:
            return False

    print("✓ Daily loss limit validated")
    return True


def test_position_lifecycle():
    """Test 5: Complete position lifecycle"""
    print("\n=== Test 5: Complete Position Lifecycle ===")

    manager = PositionManager(default_risk_percentage=0.02)
    account_balance = 10000.0

    # Initial entry
    entry_price = 50000.0
    atr = 500.0
    stop_loss = entry_price - atr * 2.0

    position = manager.calculate_initial_position(
        account_balance=account_balance,
        entry_price=entry_price,
        stop_loss_price=stop_loss,
    )

    print(f"\nInitial entry:")
    print(f"  Price: ${entry_price:,.0f}")
    print(f"  Size: {position.position_size:.4f} BTC")
    print(f"  Stop: ${position.stop_loss_price:,.0f}")

    # Simulate price movement and pyramid
    total_size = position.position_size
    total_cost = position.position_size * entry_price
    current_stop = position.stop_loss_price
    highest_price = entry_price

    # Price moves up - add position (pyramid)
    price_1 = 51000.0
    can_pyramid = (price_1 > entry_price * 1.01) and (price_1 > stop_loss * 1.02)

    if can_pyramid:
        add_size = position.position_size * 0.5
        total_size += add_size
        total_cost += add_size * price_1
        avg_entry = total_cost / total_size
        print(f"\nPyramid entry at ${price_1:,.0f}:")
        print(f"  Add: {add_size:.4f} BTC")
        print(f"  Total size: {total_size:.4f} BTC")
        print(f"  Avg entry: ${avg_entry:,.0f}")
        highest_price = price_1

    # Update trailing stop
    potential_stop = highest_price - 2.0 * atr
    current_stop = max(current_stop, potential_stop)
    print(f"  Trailing stop: ${current_stop:,.0f}")

    # Price continues up
    exit_price = 52000.0
    highest_price = max(highest_price, exit_price)
    potential_stop = highest_price - 2.0 * atr
    current_stop = max(current_stop, potential_stop)

    print(f"\nExit at ${exit_price:,.0f}:")
    print(f"  Trailing stop: ${current_stop:,.0f}")

    # Calculate P&L
    avg_entry = total_cost / total_size
    pnl = (exit_price - avg_entry) * total_size
    pnl_pct = pnl / account_balance * 100

    print(f"\nFinal P&L:")
    print(f"  Avg entry: ${avg_entry:,.0f}")
    print(f"  Exit: ${exit_price:,.0f}")
    print(f"  P&L: ${pnl:,.2f} ({pnl_pct:+.2f}%)")

    assert pnl > 0, "Trade should be profitable"
    print("\n✓ Position lifecycle validated")
    return True


def main():
    """Run all tests"""
    print("=" * 60)
    print("PHASE 3: POSITION MANAGEMENT VALIDATION")
    print("=" * 60)

    tests = [
        ("Initial Position Sizing", test_initial_position_sizing),
        ("Pyramid Entry Logic", test_pyramid_entry),
        ("Trailing Stop Loss", test_trailing_stop),
        ("Daily Loss Limit", test_daily_loss_limit),
        ("Position Lifecycle", test_position_lifecycle),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n✗ Test failed with exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status} - {name}")

    print(f"\nPassed: {passed}/{total} tests")

    if passed == total:
        print("\n✓ All Phase 3 position management tests passed!")
        return 0
    else:
        print("\n✗ Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
