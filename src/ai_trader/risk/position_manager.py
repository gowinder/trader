"""Position sizing and risk management module implementing professional trading strategies"""

from typing import Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from ..utils.logger import logger


@dataclass
class PositionSizeResult:
    """Result of position size calculation"""

    position_size: float  # Calculated position size
    risk_amount: float  # Dollar amount at risk
    risk_percentage: float  # Percentage of account at risk
    entry_price: float  # Entry price used in calculation
    stop_loss_price: float  # Stop loss price used in calculation


@dataclass
class TrailingStopResult:
    """Result of trailing stop calculation"""

    new_stop_price: float  # New trailing stop price
    should_move_stop: bool  # Whether stop should be moved
    reason: str  # Explanation for decision


class PositionManager:
    """Position sizing and risk management following professional trader methodology

    Implements:
    - Fixed percentage position sizing (1-2% risk per trade)
    - Pyramid position scaling (first heavy, then light)
    - Trailing stop loss (ATR-based and percentage-based)
    - Daily loss limit enforcement
    """

    def __init__(
        self,
        default_risk_percentage: float = 0.01,  # 1% default risk
        daily_loss_limit: float = 0.03,  # 3% daily loss limit
        max_single_trade_risk: float = 0.02,  # 2% maximum risk per trade
    ):
        """Initialize position manager with risk parameters

        Args:
            default_risk_percentage: Default risk per trade (0.01 = 1%)
            daily_loss_limit: Maximum daily loss (0.03 = 3%)
            max_single_trade_risk: Maximum risk per single trade (0.02 = 2%)
        """
        self.default_risk_percentage = default_risk_percentage
        self.daily_loss_limit = daily_loss_limit
        self.max_single_trade_risk = max_single_trade_risk

        # Track daily P&L
        self.daily_pnl_tracker: dict[str, float] = {}  # {date: pnl}
        self.current_date = datetime.now().date()

    def calculate_initial_position(
        self,
        account_balance: float,
        entry_price: float,
        stop_loss_price: float,
        risk_percentage: Optional[float] = None,
    ) -> Optional[PositionSizeResult]:
        """Calculate initial position size based on fixed percentage risk

        Formula:
            Position Size = (Account Balance × Risk %) / (Entry Price - Stop Loss Price)

        Args:
            account_balance: Total account balance in USDT
            entry_price: Planned entry price
            stop_loss_price: Planned stop loss price
            risk_percentage: Risk per trade (default: self.default_risk_percentage)

        Returns:
            PositionSizeResult with calculated position size or None on error

        Example:
            account_balance = 10000 USDT
            entry_price = 60000 USDT (BTC)
            stop_loss_price = 59000 USDT
            risk_percentage = 0.01 (1%)
            -> risk_amount = 100 USDT
            -> price_diff = 1000 USDT
            -> position_size = 100 / 1000 = 0.1 BTC (value: 6000 USDT)
        """
        if risk_percentage is None:
            risk_percentage = self.default_risk_percentage

        # Validate risk percentage
        if risk_percentage > self.max_single_trade_risk:
            logger.warning(
                f"Risk percentage {risk_percentage:.1%} exceeds maximum {self.max_single_trade_risk:.1%}, "
                f"using maximum instead"
            )
            risk_percentage = self.max_single_trade_risk

        # Validate inputs
        if account_balance <= 0:
            logger.error(f"Invalid account balance: {account_balance}")
            return None

        if entry_price <= 0 or stop_loss_price <= 0:
            logger.error(
                f"Invalid prices: entry={entry_price}, stop_loss={stop_loss_price}"
            )
            return None

        price_diff = abs(entry_price - stop_loss_price)
        if price_diff == 0:
            logger.error("Entry price and stop loss price cannot be the same")
            return None

        # Calculate position size
        risk_amount = account_balance * risk_percentage
        position_size = risk_amount / price_diff

        logger.info(
            f"Position size calculated: {position_size:.6f} units "
            f"(risk: {risk_amount:.2f} USDT, {risk_percentage:.1%})"
        )

        return PositionSizeResult(
            position_size=position_size,
            risk_amount=risk_amount,
            risk_percentage=risk_percentage,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
        )

    def should_add_position(
        self,
        current_price: float,
        entry_price: float,
        original_stop_loss: float,
        current_profit_pct: float,
        min_profit_for_add: float = 0.05,  # 5% minimum profit before adding
        trend_strong: bool = True,  # Multi-timeframe trend confirmation
    ) -> Tuple[bool, str]:
        """Check if conditions are met for pyramid position scaling

        Pyramid Position Rules (First Heavy, Then Light):
        1. Initial position must be profitable (>5%)
        2. Price must be moving in favorable direction
        3. Original stop loss must not be violated
        4. Trend must remain strong across multiple timeframes

        Args:
            current_price: Current market price
            entry_price: Original entry price
            original_stop_loss: Original stop loss price (must be preserved)
            current_profit_pct: Current profit percentage (e.g., 0.05 = 5%)
            min_profit_for_add: Minimum profit required before adding (default 5%)
            trend_strong: Whether trend is still strong (from multi-timeframe analysis)

        Returns:
            Tuple[bool, str]: (should_add, reason)

        Example (Long Position):
            entry_price = 60000
            original_stop_loss = 59000
            current_price = 63000 (+5%)
            -> should_add = True (if trend_strong and all conditions met)
        """
        # Determine if long or short position based on stop loss position
        # Long: stop loss is below entry, Short: stop loss is above entry
        is_long = original_stop_loss < entry_price

        # Condition 1: Initial position must be profitable
        if current_profit_pct < min_profit_for_add:
            return False, f"Profit {current_profit_pct:.1%} < minimum {min_profit_for_add:.1%}"

        # Condition 2: Price must be moving in favorable direction
        if is_long:
            if current_price <= entry_price:
                return False, f"Price {current_price} not above entry {entry_price}"
        else:  # Short position
            if current_price >= entry_price:
                return False, f"Price {current_price} not below entry {entry_price}"

        # Condition 3: Original stop loss must not be violated
        if is_long:
            if current_price <= original_stop_loss:
                return (
                    False,
                    f"Price {current_price} too close to stop loss {original_stop_loss}",
                )
        else:  # Short position
            if current_price >= original_stop_loss:
                return (
                    False,
                    f"Price {current_price} too close to stop loss {original_stop_loss}",
                )

        # Condition 4: Trend must remain strong
        if not trend_strong:
            return False, "Trend no longer strong (multi-timeframe divergence)"

        # All conditions met
        logger.info(
            f"Pyramid add signal: profit={current_profit_pct:.1%}, "
            f"price={current_price}, entry={entry_price}, stop={original_stop_loss}"
        )
        return True, "All pyramid conditions met"

    def calculate_trailing_stop(
        self,
        current_price: float,
        entry_price: float,
        current_stop: float,
        atr: float,
        profit_pct: float,
        method: str = "atr",  # "atr", "percentage", or "structure"
        atr_multiplier: float = 2.0,
        percentage: float = 0.05,  # 5% trailing distance
    ) -> TrailingStopResult:
        """Calculate dynamic trailing stop loss

        Implements professional trailing stop strategies:
        - ATR-based: Stop = Current Price - (ATR × Multiplier)
        - Percentage-based: Stop = Current Price × (1 - Percentage)
        - Structure-based: Stop below recent swing lows (long) or highs (short)

        Trailing Stop Phases:
        1. Initial (0-3% profit): Don't move stop
        2. Break-even (3-5% profit): Move stop to entry price
        3. Profit protection (>5% profit): Activate trailing stop
        4. Accelerated trailing (>15% profit): Tighten stop distance

        Args:
            current_price: Current market price
            entry_price: Original entry price
            current_stop: Current stop loss price
            atr: Average True Range (volatility measure)
            profit_pct: Current profit percentage (e.g., 0.05 = 5%)
            method: Trailing stop method ("atr", "percentage", "structure")
            atr_multiplier: ATR multiplier for stop distance (default 2.0)
            percentage: Percentage distance for trailing stop (default 5%)

        Returns:
            TrailingStopResult with new stop price and recommendation
        """
        is_long = entry_price < current_price

        # Phase 1: Initial protection (0-3% profit) - Don't move stop
        if profit_pct < 0.03:
            return TrailingStopResult(
                new_stop_price=current_stop,
                should_move_stop=False,
                reason=f"Initial phase (profit {profit_pct:.1%} < 3%), keeping original stop",
            )

        # Phase 2: Break-even (3-5% profit) - Move to entry price
        if 0.03 <= profit_pct < 0.05:
            if is_long:
                breakeven_stop = entry_price
                if breakeven_stop > current_stop:
                    return TrailingStopResult(
                        new_stop_price=breakeven_stop,
                        should_move_stop=True,
                        reason=f"Break-even phase (profit {profit_pct:.1%}), moving stop to entry",
                    )
            else:  # Short position
                breakeven_stop = entry_price
                if breakeven_stop < current_stop:
                    return TrailingStopResult(
                        new_stop_price=breakeven_stop,
                        should_move_stop=True,
                        reason=f"Break-even phase (profit {profit_pct:.1%}), moving stop to entry",
                    )

            return TrailingStopResult(
                new_stop_price=current_stop,
                should_move_stop=False,
                reason="Already at or past break-even",
            )

        # Phase 3-4: Profit protection (>5% profit) - Activate trailing stop
        # Phase 4: Accelerated trailing (>15% profit) - Tighten stop
        if profit_pct >= 0.15:
            # Accelerate trailing: reduce ATR multiplier or percentage
            atr_multiplier = max(1.5, atr_multiplier - 0.5)
            percentage = max(0.03, percentage - 0.02)
            logger.info(
                f"Accelerated trailing: profit={profit_pct:.1%}, "
                f"tightening stop (ATR×{atr_multiplier}, {percentage:.1%})"
            )

        # Calculate new stop based on method
        if method == "atr":
            new_stop = self._calculate_atr_stop(
                current_price, atr, atr_multiplier, is_long
            )
        elif method == "percentage":
            new_stop = self._calculate_percentage_stop(
                current_price, percentage, is_long
            )
        else:
            logger.warning(f"Unknown trailing stop method: {method}, using ATR")
            new_stop = self._calculate_atr_stop(
                current_price, atr, atr_multiplier, is_long
            )

        # Only move stop in favorable direction (up for long, down for short)
        if is_long:
            if new_stop > current_stop:
                return TrailingStopResult(
                    new_stop_price=new_stop,
                    should_move_stop=True,
                    reason=f"Trailing stop ({method}): {current_stop:.2f} -> {new_stop:.2f}",
                )
        else:  # Short position
            if new_stop < current_stop:
                return TrailingStopResult(
                    new_stop_price=new_stop,
                    should_move_stop=True,
                    reason=f"Trailing stop ({method}): {current_stop:.2f} -> {new_stop:.2f}",
                )

        return TrailingStopResult(
            new_stop_price=current_stop,
            should_move_stop=False,
            reason=f"New stop ({new_stop:.2f}) not better than current ({current_stop:.2f})",
        )

    def _calculate_atr_stop(
        self, current_price: float, atr: float, multiplier: float, is_long: bool
    ) -> float:
        """Calculate ATR-based trailing stop

        Formula:
            Long: Stop = Current Price - (ATR × Multiplier)
            Short: Stop = Current Price + (ATR × Multiplier)
        """
        if is_long:
            return current_price - (atr * multiplier)
        else:
            return current_price + (atr * multiplier)

    def _calculate_percentage_stop(
        self, current_price: float, percentage: float, is_long: bool
    ) -> float:
        """Calculate percentage-based trailing stop

        Formula:
            Long: Stop = Current Price × (1 - Percentage)
            Short: Stop = Current Price × (1 + Percentage)
        """
        if is_long:
            return current_price * (1 - percentage)
        else:
            return current_price * (1 + percentage)

    def check_daily_loss_limit(
        self,
        daily_pnl: float,
        account_balance: float,
    ) -> Tuple[bool, str]:
        """Check if daily loss limit is exceeded

        Purpose: Prevent single-day catastrophic losses and emotional trading

        Rules:
        1. Daily max loss: 3-5% of account balance (configurable)
        2. If exceeded: STOP TRADING immediately, resume next day
        3. If triggered 2 consecutive days: Take 1-week break

        Args:
            daily_pnl: Today's total P&L (negative for loss)
            account_balance: Current account balance

        Returns:
            Tuple[bool, str]: (limit_exceeded, message)
        """
        # Update current date tracker
        today = datetime.now().date()
        if today != self.current_date:
            # New day, reset tracker
            self.current_date = today
            self.daily_pnl_tracker[str(today)] = daily_pnl
        else:
            self.daily_pnl_tracker[str(today)] = daily_pnl

        max_loss = account_balance * self.daily_loss_limit

        # Check if loss limit exceeded (only check for losses, not profits)
        if daily_pnl < 0 and abs(daily_pnl) >= max_loss:
            logger.warning(
                f"⚠️ DAILY LOSS LIMIT EXCEEDED: {daily_pnl:.2f} USDT (limit: {max_loss:.2f})"
            )

            # Check for consecutive trigger (pass account_balance for proper threshold calculation)
            consecutive_days = self._check_consecutive_loss_days(account_balance)
            if consecutive_days >= 2:
                return (
                    True,
                    f"Daily loss limit exceeded for {consecutive_days} consecutive days. "
                    f"MANDATORY 1-WEEK BREAK REQUIRED.",
                )

            return (
                True,
                f"Daily loss limit exceeded: {daily_pnl:.2f} USDT / {max_loss:.2f} USDT. "
                f"STOP TRADING for today.",
            )

        # Within limits (or profitable)
        if daily_pnl >= 0:
            return (
                False,
                f"Daily P&L: +{daily_pnl:.2f} USDT (profitable)",
            )
        else:
            remaining = max_loss - abs(daily_pnl)
            return (
                False,
                f"Daily P&L: {daily_pnl:.2f} USDT, Remaining loss allowance: {remaining:.2f} USDT",
            )

    def _check_consecutive_loss_days(self, account_balance: float) -> int:
        """Check how many consecutive days have exceeded loss limit

        Args:
            account_balance: Current account balance for calculating threshold

        Returns:
            Number of consecutive days with loss limit exceeded
        """
        consecutive = 0
        today = datetime.now().date()

        # Calculate the loss threshold based on current balance
        loss_threshold = account_balance * self.daily_loss_limit

        # Check up to last 7 days
        for i in range(7):
            check_date = today - timedelta(days=i)
            date_str = str(check_date)

            if date_str in self.daily_pnl_tracker:
                daily_pnl = self.daily_pnl_tracker[date_str]
                # Check if this day's loss exceeded the threshold
                if daily_pnl < 0 and abs(daily_pnl) >= loss_threshold:
                    consecutive += 1
                else:
                    break
            else:
                break

        return consecutive

    def calculate_pyramid_position_size(
        self,
        initial_position_size: float,
        pyramid_level: int,  # 1 = first add, 2 = second add
    ) -> float:
        """Calculate position size for pyramid scaling (first heavy, then light)

        Formula:
            Level 0 (initial): 100% (base position)
            Level 1 (first add): 50% of initial
            Level 2 (second add): 25% of initial

        Args:
            initial_position_size: Size of initial position
            pyramid_level: Current pyramid level (1, 2, 3, ...)

        Returns:
            Position size for this pyramid level

        Example:
            initial_position_size = 0.1 BTC
            pyramid_level = 1 -> 0.05 BTC (50%)
            pyramid_level = 2 -> 0.025 BTC (25%)
        """
        if pyramid_level == 0:
            return initial_position_size

        # Each level is half the previous: 50%, 25%, 12.5%, ...
        multiplier = 0.5**pyramid_level
        add_size = initial_position_size * multiplier

        logger.info(
            f"Pyramid level {pyramid_level}: {multiplier:.1%} of initial "
            f"({add_size:.6f} units)"
        )

        return add_size
