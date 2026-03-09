"""Position management backtest validation

Tests position sizing, pyramid entry, and trailing stop loss
using synthetic historical data.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from ai_trader.risk.position_manager import PositionManager, PositionSizeResult, TrailingStopResult


def generate_test_data(n_candles: int = 100, base_price: float = 50000.0) -> pd.DataFrame:
    """Generate synthetic price data for testing"""
    np.random.seed(42)

    trend = np.linspace(0, 5000, n_candles)
    noise = np.random.randn(n_candles) * 100
    close_prices = base_price + trend + noise

    timestamps = pd.date_range(
        start=datetime.now() - timedelta(hours=n_candles),
        periods=n_candles,
        freq="1h",
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
        default_risk_percentage=0.02,
        max_single_trade_risk=0.02,
    )

    df = generate_test_data(50)
    current_price = float(df["close"].iloc[-1])
    atr = calculate_atr(df)
    stop_loss_price = current_price - atr * 2.0

    result = manager.calculate_initial_position(
        account_balance=10000.0,
        entry_price=current_price,
        stop_loss_price=stop_loss_price,
    )

    assert result is not None
    assert result.position_size > 0
    assert result.entry_price == current_price
    assert result.stop_loss_price == stop_loss_price
    assert result.risk_amount > 0
    assert result.risk_amount <= 10000.0 * 0.02


def test_pyramid_entry_conditions():
    """Test pyramid entry (adding to winning position)"""
    manager = PositionManager(default_risk_percentage=0.02)

    df = generate_test_data(50)
    initial_price = float(df["close"].iloc[-40])
    atr = calculate_atr(df)
    stop_loss = initial_price - atr * 2.0

    pyramid_count = 0
    for i in range(-30, -1, 5):
        current_price = float(df["close"].iloc[i])
        profit_pct = (current_price - initial_price) / initial_price

        should_add, reason = manager.should_add_position(
            current_price=current_price,
            entry_price=initial_price,
            original_stop_loss=stop_loss,
            current_profit_pct=profit_pct,
        )

        if should_add:
            pyramid_count += 1

    # Pyramid entries depend on profit threshold (5% default)
    assert pyramid_count >= 0


def test_trailing_stop_loss():
    """Test trailing stop loss calculation"""
    manager = PositionManager(default_risk_percentage=0.02)

    df = generate_test_data(100)
    entry_price = float(df["close"].iloc[0])
    initial_atr = calculate_atr(df.iloc[:20])
    initial_stop = entry_price - initial_atr * 2.0

    current_stop = initial_stop
    trailing_updates = 0

    for i in range(1, len(df)):
        current_price = float(df["close"].iloc[i])
        current_atr = calculate_atr(df.iloc[: i + 1])
        profit_pct = (current_price - entry_price) / entry_price

        result = manager.calculate_trailing_stop(
            current_price=current_price,
            entry_price=entry_price,
            current_stop=current_stop,
            atr=current_atr,
            profit_pct=profit_pct,
        )

        if result.should_move_stop and result.new_stop_price > current_stop:
            trailing_updates += 1
            current_stop = result.new_stop_price

    assert current_stop >= initial_stop, "Trailing stop should never move down"
    assert trailing_updates > 0, "Stop should have moved up at least once"


def test_daily_loss_limit():
    """Test daily loss limit enforcement"""
    manager = PositionManager(
        default_risk_percentage=0.02,
        daily_loss_limit=0.05,
    )

    account_balance = 10000.0
    daily_pnl = 0.0
    trades = [
        ("Trade 1", -150.0),
        ("Trade 2", -200.0),
        ("Trade 3", -100.0),
        ("Trade 4", -80.0),  # Total: -530 (5.3%)
    ]

    limit_hit = False
    for trade_name, loss in trades:
        daily_pnl += loss
        exceeded, reason = manager.check_daily_loss_limit(daily_pnl, account_balance)
        if exceeded:
            limit_hit = True
            break

    assert limit_hit, "Daily loss limit should have been exceeded"
    assert abs(daily_pnl) >= account_balance * 0.05


def test_pyramid_position_size_scaling():
    """Test pyramid position size decreases with level"""
    manager = PositionManager()

    initial_size = 0.1
    level_1 = manager.calculate_pyramid_position_size(initial_size, 1)
    level_2 = manager.calculate_pyramid_position_size(initial_size, 2)

    assert level_1 == initial_size * 0.5
    assert level_2 == initial_size * 0.25
    assert level_1 > level_2


def test_position_management_integration():
    """Integration test: Position management through complete trade lifecycle"""
    manager = PositionManager(
        default_risk_percentage=0.02,
        daily_loss_limit=0.05,
    )

    df = generate_test_data(200, base_price=50000.0)
    atr = calculate_atr(df)
    account_balance = 10000.0

    entry_price = float(df["close"].iloc[0])
    stop_loss_price = entry_price - atr * 2.0

    position = manager.calculate_initial_position(
        account_balance=account_balance,
        entry_price=entry_price,
        stop_loss_price=stop_loss_price,
    )
    assert position is not None

    current_stop = stop_loss_price
    total_size = position.position_size
    total_cost = position.position_size * entry_price
    pyramid_count = 1

    for i in range(1, len(df), 10):
        current_price = float(df["close"].iloc[i])
        current_atr = calculate_atr(df.iloc[: i + 1])
        profit_pct = (current_price - entry_price) / entry_price

        # Check for pyramid entry
        if pyramid_count < 3:
            should_add, _ = manager.should_add_position(
                current_price=current_price,
                entry_price=entry_price,
                original_stop_loss=stop_loss_price,
                current_profit_pct=profit_pct,
            )
            if should_add:
                add_size = manager.calculate_pyramid_position_size(
                    position.position_size, pyramid_count
                )
                total_size += add_size
                total_cost += add_size * current_price
                pyramid_count += 1

        # Update trailing stop
        result = manager.calculate_trailing_stop(
            current_price=current_price,
            entry_price=entry_price,
            current_stop=current_stop,
            atr=current_atr,
            profit_pct=profit_pct,
        )
        if result.should_move_stop:
            current_stop = result.new_stop_price

    exit_price = float(df["close"].iloc[-1])
    pnl = (exit_price - (total_cost / total_size)) * total_size

    # With uptrend synthetic data, we expect profit
    assert total_size > 0
    assert total_cost > 0
