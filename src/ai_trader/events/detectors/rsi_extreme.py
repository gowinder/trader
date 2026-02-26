"""RSIExtremeDetector — RSI 超买/超卖检测器。"""

from __future__ import annotations

from typing import Optional

from ai_trader.events.detectors.base import BaseDetector
from ai_trader.events.models import TriggerEvent
from ai_trader.models.market import Indicators, MarketData


class RSIExtremeDetector(BaseDetector):
    """检测 RSI 是否达到超买/超卖极值。"""

    def __init__(self, upper_threshold: float = 75, lower_threshold: float = 25):
        self.upper_threshold = upper_threshold
        self.lower_threshold = lower_threshold

    def check(
        self,
        market_data: MarketData,
        indicators: Indicators,
        position: object | None,
    ) -> Optional[TriggerEvent]:
        rsi = indicators.rsi

        if rsi >= self.upper_threshold:
            return TriggerEvent(
                event_type="rsi_extreme",
                description=f"RSI 超买: {rsi:.1f} (阈值 {self.upper_threshold})",
                severity="medium",
                key_data={"rsi": rsi, "zone": "overbought"},
            )

        if rsi <= self.lower_threshold:
            return TriggerEvent(
                event_type="rsi_extreme",
                description=f"RSI 超卖: {rsi:.1f} (阈值 {self.lower_threshold})",
                severity="medium",
                key_data={"rsi": rsi, "zone": "oversold"},
            )

        return None
