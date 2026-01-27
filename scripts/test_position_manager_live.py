"""Test Position Manager with real trading scenarios"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ai_trader.risk.position_manager import PositionManager


def test_position_sizing():
    """Test position sizing calculations"""
    print("=" * 60)
    print("💰 Testing Position Sizing Calculations")
    print("=" * 60)

    pm = PositionManager(
        default_risk_percentage=0.01,  # 1% risk per trade
        daily_loss_limit=0.03,  # 3% daily loss limit
    )

    # Scenario 1: Conservative trade (BTC)
    print("\n📊 Scenario 1: Conservative BTC Long Trade")
    print("  Account Balance: 10,000 USDT")
    print("  Entry Price: 60,000 USDT")
    print("  Stop Loss: 59,000 USDT (1,000 USDT risk per BTC)")
    print("  Risk: 1%")

    result = pm.calculate_initial_position(
        account_balance=10000.0,
        entry_price=60000.0,
        stop_loss_price=59000.0,
        risk_percentage=0.01,
    )

    if result:
        print(f"\n✅ Position Calculation:")
        print(f"  Position Size: {result.position_size:.4f} BTC")
        print(f"  Position Value: {result.position_size * 60000:.2f} USDT")
        print(f"  Risk Amount: {result.risk_amount:.2f} USDT")
        print(f"  Risk %: {result.risk_percentage:.1%}")
        print(f"  Max Loss if stopped: {result.risk_amount:.2f} USDT")

    # Scenario 2: Aggressive trade (ETH)
    print("\n\n📊 Scenario 2: Aggressive ETH Short Trade")
    print("  Account Balance: 10,000 USDT")
    print("  Entry Price: 3,000 USDT")
    print("  Stop Loss: 3,060 USDT (60 USDT risk per ETH)")
    print("  Risk: 2%")

    result = pm.calculate_initial_position(
        account_balance=10000.0,
        entry_price=3000.0,
        stop_loss_price=3060.0,
        risk_percentage=0.02,
    )

    if result:
        print(f"\n✅ Position Calculation:")
        print(f"  Position Size: {result.position_size:.4f} ETH")
        print(f"  Position Value: {result.position_size * 3000:.2f} USDT")
        print(f"  Risk Amount: {result.risk_amount:.2f} USDT")
        print(f"  Risk %: {result.risk_percentage:.1%}")


def test_pyramid_scaling():
    """Test pyramid position scaling"""
    print("\n\n" + "=" * 60)
    print("📈 Testing Pyramid Position Scaling")
    print("=" * 60)

    pm = PositionManager()

    # Initial position
    print("\n📊 BTC Long Trade - Pyramid Scaling Example")
    print("  Entry Price: 60,000 USDT")
    print("  Stop Loss: 59,000 USDT")
    print("  Current Price: 63,000 USDT (+5%)")

    # Check if we should add
    should_add, reason = pm.should_add_position(
        current_price=63000.0,
        entry_price=60000.0,
        original_stop_loss=59000.0,
        current_profit_pct=0.05,
        trend_strong=True,
    )

    print(f"\n✅ Add Position Check:")
    print(f"  Should Add: {'✅ YES' if should_add else '❌ NO'}")
    print(f"  Reason: {reason}")

    if should_add:
        initial_size = 0.1  # BTC
        print(f"\n📊 Pyramid Position Sizes:")
        print(f"  Initial Position (Level 0): {initial_size:.4f} BTC")

        for level in range(1, 4):
            add_size = pm.calculate_pyramid_position_size(initial_size, level)
            print(f"  Add #{level} (Level {level}): {add_size:.4f} BTC ({add_size/initial_size:.0%} of initial)")

        total = initial_size + sum(
            pm.calculate_pyramid_position_size(initial_size, i) for i in range(1, 4)
        )
        avg_cost = (
            60000 * initial_size
            + 63000 * pm.calculate_pyramid_position_size(initial_size, 1)
            + 66000 * pm.calculate_pyramid_position_size(initial_size, 2)
            + 69000 * pm.calculate_pyramid_position_size(initial_size, 3)
        ) / total

        print(f"\n  Total Position: {total:.4f} BTC")
        print(f"  Average Cost: {avg_cost:.2f} USDT")


def test_trailing_stop():
    """Test trailing stop loss"""
    print("\n\n" + "=" * 60)
    print("📉 Testing Trailing Stop Loss")
    print("=" * 60)

    pm = PositionManager()

    scenarios = [
        {
            "name": "Phase 1: Initial (2% profit)",
            "current_price": 61200.0,
            "entry_price": 60000.0,
            "current_stop": 59000.0,
            "profit_pct": 0.02,
            "atr": 500.0,
        },
        {
            "name": "Phase 2: Break-even (4% profit)",
            "current_price": 62400.0,
            "entry_price": 60000.0,
            "current_stop": 59000.0,
            "profit_pct": 0.04,
            "atr": 500.0,
        },
        {
            "name": "Phase 3: Profit Protection (8% profit)",
            "current_price": 64800.0,
            "entry_price": 60000.0,
            "current_stop": 60000.0,
            "profit_pct": 0.08,
            "atr": 600.0,
        },
        {
            "name": "Phase 4: Accelerated (20% profit)",
            "current_price": 72000.0,
            "entry_price": 60000.0,
            "current_stop": 65000.0,
            "profit_pct": 0.20,
            "atr": 700.0,
        },
    ]

    for scenario in scenarios:
        print(f"\n📊 {scenario['name']}")
        print(f"  Entry: {scenario['entry_price']:.2f}")
        print(f"  Current: {scenario['current_price']:.2f}")
        print(f"  Current Stop: {scenario['current_stop']:.2f}")
        print(f"  Profit: {scenario['profit_pct']:.1%}")

        result = pm.calculate_trailing_stop(
            current_price=scenario["current_price"],
            entry_price=scenario["entry_price"],
            current_stop=scenario["current_stop"],
            atr=scenario["atr"],
            profit_pct=scenario["profit_pct"],
            method="atr",
            atr_multiplier=2.0,
        )

        print(f"\n  ✅ Trailing Stop Result:")
        print(f"    Should Move: {'✅ YES' if result.should_move_stop else '❌ NO'}")
        print(f"    New Stop: {result.new_stop_price:.2f} USDT")
        print(f"    Reason: {result.reason}")


def test_daily_loss_limit():
    """Test daily loss limit enforcement"""
    print("\n\n" + "=" * 60)
    print("🚨 Testing Daily Loss Limit")
    print("=" * 60)

    pm = PositionManager(daily_loss_limit=0.03)  # 3%

    scenarios = [
        {"name": "Within Limit", "daily_pnl": -200.0},
        {"name": "Approaching Limit", "daily_pnl": -280.0},
        {"name": "Exceeded Limit", "daily_pnl": -350.0},
        {"name": "Profitable Day", "daily_pnl": 150.0},
    ]

    for scenario in scenarios:
        print(f"\n📊 {scenario['name']}")
        print(f"  Account Balance: 10,000 USDT")
        print(f"  Daily P&L: {scenario['daily_pnl']:+.2f} USDT")

        exceeded, message = pm.check_daily_loss_limit(
            daily_pnl=scenario["daily_pnl"],
            account_balance=10000.0,
        )

        if exceeded:
            print(f"  ❌ LIMIT EXCEEDED - STOP TRADING")
        else:
            print(f"  ✅ Within Limits")

        print(f"  Message: {message}")


if __name__ == "__main__":
    test_position_sizing()
    test_pyramid_scaling()
    test_trailing_stop()
    test_daily_loss_limit()

    print("\n\n" + "=" * 60)
    print("✅ All Position Manager Tests Completed")
    print("=" * 60)
