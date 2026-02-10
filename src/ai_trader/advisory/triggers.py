"""Advisory 触发器系统"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from ..utils.logger import logger


@dataclass
class TriggerConfig:
    interval_minutes: int = 60
    price_volatility_enabled: bool = True
    price_volatility_threshold: float = 5.0
    consecutive_loss_enabled: bool = True
    consecutive_loss_threshold: int = 3
    unrealized_pnl_enabled: bool = True
    unrealized_pnl_threshold: float = -5.0
    sentiment_shift_enabled: bool = True
    cooldown_minutes: int = 30


class BaseTrigger:
    def __init__(self, cooldown_minutes: int = 30):
        self.cooldown_minutes = cooldown_minutes
        self._last_fired: Optional[datetime] = None

    def _is_cooldown(self) -> bool:
        if self._last_fired is None:
            return False
        return datetime.now() - self._last_fired < timedelta(minutes=self.cooldown_minutes)

    def _mark_fired(self):
        self._last_fired = datetime.now()


class PriceVolatilityTrigger(BaseTrigger):
    def __init__(self, threshold: float = 5.0, cooldown_minutes: int = 30):
        super().__init__(cooldown_minutes)
        self.threshold = threshold

    def check(self, current_price: float, previous_price: float, interval_minutes: int = 5) -> Optional[Dict[str, Any]]:
        if self._is_cooldown():
            return None
        if previous_price == 0:
            return None
        change_pct = ((current_price - previous_price) / previous_price) * 100
        if abs(change_pct) >= self.threshold:
            self._mark_fired()
            return {
                "change_pct": round(change_pct, 2),
                "current_price": current_price,
                "previous_price": previous_price,
                "interval_minutes": interval_minutes,
            }
        return None


class ConsecutiveLossTrigger(BaseTrigger):
    def __init__(self, threshold: int = 3, cooldown_minutes: int = 30):
        super().__init__(cooldown_minutes)
        self.threshold = threshold

    def check(self, consecutive_losses: int) -> Optional[Dict[str, Any]]:
        if self._is_cooldown():
            return None
        if consecutive_losses >= self.threshold:
            self._mark_fired()
            return {"consecutive_losses": consecutive_losses}
        return None


class UnrealizedPnLTrigger(BaseTrigger):
    def __init__(self, threshold: float = -5.0, cooldown_minutes: int = 30):
        super().__init__(cooldown_minutes)
        self.threshold = threshold

    def check(self, unrealized_pnl_pct: float) -> Optional[Dict[str, Any]]:
        if self._is_cooldown():
            return None
        if unrealized_pnl_pct <= self.threshold:
            self._mark_fired()
            return {"unrealized_pnl_pct": round(unrealized_pnl_pct, 2)}
        return None


class SentimentShiftTrigger(BaseTrigger):
    def __init__(self, cooldown_minutes: int = 30):
        super().__init__(cooldown_minutes)

    def check(self, extreme_fear: bool = False, extreme_greed: bool = False) -> Optional[Dict[str, Any]]:
        if self._is_cooldown():
            return None
        if extreme_fear or extreme_greed:
            self._mark_fired()
            return {"extreme_fear": extreme_fear, "extreme_greed": extreme_greed}
        return None


class TriggerManager:
    def __init__(self, config: Optional[TriggerConfig] = None):
        self.config = config or TriggerConfig()
        self._last_scheduled: Optional[datetime] = None

        self.price_volatility = PriceVolatilityTrigger(
            threshold=self.config.price_volatility_threshold,
            cooldown_minutes=self.config.cooldown_minutes,
        )
        self.consecutive_loss = ConsecutiveLossTrigger(
            threshold=self.config.consecutive_loss_threshold,
            cooldown_minutes=self.config.cooldown_minutes,
        )
        self.unrealized_pnl = UnrealizedPnLTrigger(
            threshold=self.config.unrealized_pnl_threshold,
            cooldown_minutes=self.config.cooldown_minutes,
        )
        self.sentiment_shift = SentimentShiftTrigger(
            cooldown_minutes=self.config.cooldown_minutes,
        )

    def should_run_scheduled(self) -> bool:
        if self._last_scheduled is None:
            return True
        return datetime.now() - self._last_scheduled >= timedelta(minutes=self.config.interval_minutes)

    def mark_scheduled_run(self):
        self._last_scheduled = datetime.now()

    def update_config(self, new_config: TriggerConfig):
        self.config = new_config
        self.price_volatility.threshold = new_config.price_volatility_threshold
        self.price_volatility.cooldown_minutes = new_config.cooldown_minutes
        self.consecutive_loss.threshold = new_config.consecutive_loss_threshold
        self.consecutive_loss.cooldown_minutes = new_config.cooldown_minutes
        self.unrealized_pnl.threshold = new_config.unrealized_pnl_threshold
        self.unrealized_pnl.cooldown_minutes = new_config.cooldown_minutes
        self.sentiment_shift.cooldown_minutes = new_config.cooldown_minutes
