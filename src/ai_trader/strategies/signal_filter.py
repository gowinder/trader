"""Signal filtering utilities"""

from datetime import datetime, timedelta
from typing import Optional
from .strategy_base import SignalAction


class SignalFilter:
    """Filter signals to reduce overtrading"""

    def __init__(self, min_interval_hours: float = 6, reverse_cooldown_hours: float = 24):
        """Initialize signal filter

        Args:
            min_interval_hours: Minimum hours between trades
            reverse_cooldown_hours: Cooldown hours before allowing direction flip
        """
        self.min_interval_hours = min_interval_hours
        self.reverse_cooldown_hours = reverse_cooldown_hours
        self.last_trade_time: Optional[datetime] = None
        self.last_action: Optional[SignalAction] = None

    def should_allow_signal(
        self, action: SignalAction, current_time: datetime
    ) -> tuple[bool, str]:
        """Check if signal should be allowed

        Args:
            action: Signal action
            current_time: Current timestamp

        Returns:
            Tuple of (allowed, reason)
        """
        # Always allow HOLD
        if action == SignalAction.HOLD:
            return True, "HOLD signal"

        # Check minimum interval
        if self.last_trade_time is not None:
            time_since_last = current_time - self.last_trade_time
            min_interval = timedelta(hours=self.min_interval_hours)

            if time_since_last < min_interval:
                hours_remaining = (min_interval - time_since_last).total_seconds() / 3600
                return (
                    False,
                    f"Too soon since last trade ({hours_remaining:.1f}h remaining)",
                )

        # Check for action flip (LONG->SHORT or SHORT->LONG too quickly)
        if self.last_action is not None:
            if self._is_opposite_action(self.last_action, action):
                time_since_last = current_time - self.last_trade_time
                if time_since_last < timedelta(hours=self.reverse_cooldown_hours):
                    return (
                        False,
                        f"Action flip too quick ({self.last_action.value} -> {action.value})",
                    )

        return True, "Signal allowed"

    def record_trade(self, action: SignalAction, timestamp: datetime):
        """Record a trade

        Args:
            action: Action taken
            timestamp: Trade timestamp
        """
        self.last_trade_time = timestamp
        self.last_action = action

    def reset(self):
        """Reset filter state"""
        self.last_trade_time = None
        self.last_action = None

    def _is_opposite_action(self, action1: SignalAction, action2: SignalAction) -> bool:
        """Check if two actions are opposite

        Args:
            action1: First action
            action2: Second action

        Returns:
            True if opposite
        """
        opposites = {
            (SignalAction.LONG, SignalAction.SHORT),
            (SignalAction.SHORT, SignalAction.LONG),
        }
        return (action1, action2) in opposites or (action2, action1) in opposites
