"""Unit tests for position sizing and risk management"""

import pytest
from ai_trader.risk.position_manager import (
    PositionManager,
    PositionSizeResult,
    TrailingStopResult,
)


class TestPositionSizeCalculation:
    """Test position size calculation formulas"""

    def test_calculate_initial_position_long(self):
        """Test position size calculation for long position"""
        pm = PositionManager(default_risk_percentage=0.01)

        result = pm.calculate_initial_position(
            account_balance=10000.0,  # 10k USDT
            entry_price=60000.0,  # BTC entry
            stop_loss_price=59000.0,  # 1k USDT stop
            risk_percentage=0.01,  # 1% risk
        )

        assert result is not None
        assert result.risk_amount == 100.0  # 1% of 10k
        assert result.position_size == 0.1  # 100 / 1000
        assert result.risk_percentage == 0.01

    def test_calculate_initial_position_short(self):
        """Test position size calculation for short position"""
        pm = PositionManager(default_risk_percentage=0.01)

        result = pm.calculate_initial_position(
            account_balance=10000.0,
            entry_price=60000.0,
            stop_loss_price=61000.0,  # Stop above entry for short
            risk_percentage=0.02,  # 2% risk
        )

        assert result is not None
        assert result.risk_amount == 200.0  # 2% of 10k
        assert result.position_size == 0.2  # 200 / 1000

    def test_calculate_position_with_different_risk_percentages(self):
        """Test varying risk percentages"""
        pm = PositionManager()

        # 0.5% risk
        result_conservative = pm.calculate_initial_position(
            account_balance=10000.0,
            entry_price=60000.0,
            stop_loss_price=59000.0,
            risk_percentage=0.005,
        )
        assert result_conservative.risk_amount == 50.0
        assert result_conservative.position_size == 0.05

        # 1.5% risk
        result_aggressive = pm.calculate_initial_position(
            account_balance=10000.0,
            entry_price=60000.0,
            stop_loss_price=59000.0,
            risk_percentage=0.015,
        )
        assert result_aggressive.risk_amount == 150.0
        assert result_aggressive.position_size == 0.15

    def test_calculate_position_invalid_inputs(self):
        """Test error handling for invalid inputs"""
        pm = PositionManager()

        # Negative balance
        result = pm.calculate_initial_position(
            account_balance=-1000.0,
            entry_price=60000.0,
            stop_loss_price=59000.0,
        )
        assert result is None

        # Zero price difference
        result = pm.calculate_initial_position(
            account_balance=10000.0,
            entry_price=60000.0,
            stop_loss_price=60000.0,  # Same as entry
        )
        assert result is None

    def test_max_risk_limit_enforcement(self):
        """Test that excessive risk percentage is capped at maximum"""
        pm = PositionManager(max_single_trade_risk=0.02)

        result = pm.calculate_initial_position(
            account_balance=10000.0,
            entry_price=60000.0,
            stop_loss_price=59000.0,
            risk_percentage=0.05,  # 5% risk - exceeds max
        )

        # Should be capped at 2%
        assert result.risk_percentage == 0.02
        assert result.risk_amount == 200.0


class TestPyramidPositionScaling:
    """Test pyramid position scaling (first heavy, then light)"""

    def test_should_add_position_profitable(self):
        """Test adding to profitable position"""
        pm = PositionManager()

        should_add, reason = pm.should_add_position(
            current_price=63000.0,  # +5% from entry
            entry_price=60000.0,
            original_stop_loss=59000.0,
            current_profit_pct=0.05,  # 5% profit
            min_profit_for_add=0.05,
            trend_strong=True,
        )

        assert should_add is True
        assert "All pyramid conditions met" in reason

    def test_should_not_add_position_insufficient_profit(self):
        """Test rejecting add when profit is insufficient"""
        pm = PositionManager()

        should_add, reason = pm.should_add_position(
            current_price=61500.0,  # Only 2.5% profit
            entry_price=60000.0,
            original_stop_loss=59000.0,
            current_profit_pct=0.025,  # 2.5% profit
            min_profit_for_add=0.05,  # Require 5%
            trend_strong=True,
        )

        assert should_add is False
        assert "Profit" in reason and "minimum" in reason

    def test_should_not_add_position_price_reversed(self):
        """Test rejecting add when price moved against us"""
        pm = PositionManager()

        should_add, reason = pm.should_add_position(
            current_price=59500.0,  # Below entry
            entry_price=60000.0,
            original_stop_loss=59000.0,
            current_profit_pct=0.05,  # Still showing profit from earlier
            trend_strong=True,
        )

        assert should_add is False
        assert "not above entry" in reason

    def test_should_not_add_position_near_stop_loss(self):
        """Test rejecting add when price at/below stop loss (edge case)"""
        pm = PositionManager()

        # Price exactly at stop loss
        should_add, reason = pm.should_add_position(
            current_price=59000.0,  # At stop loss
            entry_price=60000.0,
            original_stop_loss=59000.0,
            current_profit_pct=0.05,  # Shouldn't matter if at stop
            trend_strong=True,
        )

        assert should_add is False
        # Will trigger "not above entry" check first, which is correct behavior
        assert should_add is False

    def test_should_not_add_position_weak_trend(self):
        """Test rejecting add when trend weakens"""
        pm = PositionManager()

        should_add, reason = pm.should_add_position(
            current_price=63000.0,
            entry_price=60000.0,
            original_stop_loss=59000.0,
            current_profit_pct=0.05,
            trend_strong=False,  # Trend no longer strong
        )

        assert should_add is False
        assert "Trend no longer strong" in reason

    def test_calculate_pyramid_position_sizes(self):
        """Test pyramid position size calculation (50%, 25%, 12.5%)"""
        pm = PositionManager()

        initial_size = 0.1  # BTC

        # First add: 50% of initial
        add_1 = pm.calculate_pyramid_position_size(initial_size, pyramid_level=1)
        assert add_1 == pytest.approx(0.05, rel=1e-6)

        # Second add: 25% of initial
        add_2 = pm.calculate_pyramid_position_size(initial_size, pyramid_level=2)
        assert add_2 == pytest.approx(0.025, rel=1e-6)

        # Third add: 12.5% of initial
        add_3 = pm.calculate_pyramid_position_size(initial_size, pyramid_level=3)
        assert add_3 == pytest.approx(0.0125, rel=1e-6)


class TestTrailingStopLoss:
    """Test trailing stop loss logic"""

    def test_trailing_stop_initial_phase_no_move(self):
        """Test that stop doesn't move in initial phase (0-3% profit)"""
        pm = PositionManager()

        result = pm.calculate_trailing_stop(
            current_price=61500.0,  # 2.5% profit
            entry_price=60000.0,
            current_stop=59000.0,
            atr=1000.0,
            profit_pct=0.025,  # 2.5% profit
            method="atr",
        )

        assert result.should_move_stop is False
        assert "Initial phase" in result.reason
        assert result.new_stop_price == 59000.0  # No change

    def test_trailing_stop_breakeven_phase(self):
        """Test moving stop to break-even at 3-5% profit"""
        pm = PositionManager()

        result = pm.calculate_trailing_stop(
            current_price=62400.0,  # 4% profit
            entry_price=60000.0,
            current_stop=59000.0,  # Still at original
            atr=1000.0,
            profit_pct=0.04,  # 4% profit
            method="atr",
        )

        assert result.should_move_stop is True
        assert "Break-even" in result.reason
        assert result.new_stop_price == 60000.0  # Moved to entry

    def test_trailing_stop_atr_method(self):
        """Test ATR-based trailing stop"""
        pm = PositionManager()

        result = pm.calculate_trailing_stop(
            current_price=66000.0,  # 10% profit
            entry_price=60000.0,
            current_stop=60000.0,  # At break-even
            atr=1200.0,
            profit_pct=0.10,
            method="atr",
            atr_multiplier=2.0,
        )

        expected_stop = 66000.0 - (1200.0 * 2.0)  # 63,600
        assert result.should_move_stop is True
        assert result.new_stop_price == pytest.approx(expected_stop, rel=1e-2)

    def test_trailing_stop_percentage_method(self):
        """Test percentage-based trailing stop"""
        pm = PositionManager()

        result = pm.calculate_trailing_stop(
            current_price=66000.0,  # 10% profit
            entry_price=60000.0,
            current_stop=60000.0,
            atr=1000.0,
            profit_pct=0.10,
            method="percentage",
            percentage=0.05,  # 5% trailing distance
        )

        expected_stop = 66000.0 * 0.95  # 62,700
        assert result.should_move_stop is True
        assert result.new_stop_price == pytest.approx(expected_stop, rel=1e-2)

    def test_trailing_stop_accelerated_phase(self):
        """Test tightening stop at >15% profit"""
        pm = PositionManager()

        result = pm.calculate_trailing_stop(
            current_price=72000.0,  # 20% profit
            entry_price=60000.0,
            current_stop=65000.0,
            atr=1200.0,
            profit_pct=0.20,  # 20% profit
            method="atr",
            atr_multiplier=2.0,
        )

        # ATR multiplier should be reduced to 1.5 (2.0 - 0.5)
        expected_stop = 72000.0 - (1200.0 * 1.5)  # 70,200
        assert result.should_move_stop is True
        assert result.new_stop_price == pytest.approx(expected_stop, rel=1e-2)

    def test_trailing_stop_only_moves_favorably(self):
        """Test that stop only moves in favorable direction (never down for long)"""
        pm = PositionManager()

        # Stop should NOT move down even if calculation suggests it
        result = pm.calculate_trailing_stop(
            current_price=61000.0,  # 1.67% profit (weak)
            entry_price=60000.0,
            current_stop=60500.0,  # Current stop is higher
            atr=3000.0,  # Large ATR
            profit_pct=0.0167,
            method="atr",
            atr_multiplier=2.0,
        )

        # Calculated stop would be 61000 - 6000 = 55000, but current is 60500
        # Should NOT move down
        assert result.new_stop_price == 60500.0  # Keep current


class TestDailyLossLimit:
    """Test daily loss limit enforcement"""

    def test_daily_loss_within_limit(self):
        """Test that trading continues within daily loss limit"""
        pm = PositionManager(daily_loss_limit=0.03)

        limit_exceeded, message = pm.check_daily_loss_limit(
            daily_pnl=-200.0,  # Lost 200 USDT
            account_balance=10000.0,  # 2% loss - within 3% limit
        )

        assert limit_exceeded is False
        assert "Remaining loss allowance" in message

    def test_daily_loss_limit_exceeded(self):
        """Test that trading stops when daily loss limit exceeded"""
        pm = PositionManager(daily_loss_limit=0.03)

        limit_exceeded, message = pm.check_daily_loss_limit(
            daily_pnl=-350.0,  # Lost 350 USDT
            account_balance=10000.0,  # 3.5% loss - exceeds 3% limit
        )

        assert limit_exceeded is True
        assert "STOP TRADING" in message

    def test_daily_loss_limit_exact_boundary(self):
        """Test behavior at exact boundary (edge case)"""
        pm = PositionManager(daily_loss_limit=0.03)

        limit_exceeded, message = pm.check_daily_loss_limit(
            daily_pnl=-300.0,  # Exactly 3%
            account_balance=10000.0,
        )

        assert limit_exceeded is True  # >= limit triggers stop

    def test_daily_profit_no_limit(self):
        """Test that positive P&L doesn't trigger limit"""
        pm = PositionManager(daily_loss_limit=0.03)

        limit_exceeded, message = pm.check_daily_loss_limit(
            daily_pnl=500.0,  # Profit
            account_balance=10000.0,
        )

        assert limit_exceeded is False
