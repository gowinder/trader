"""MACDCrossDetector — MACD 金叉/死叉检测器。"""

from __future__ import annotations

from typing import Optional

from ai_trader.events.detectors.base import BaseDetector
from ai_trader.events.models import TriggerEvent
from ai_trader.models.market import Indicators, MarketData


class MACDCrossDetector(BaseDetector):
    """有状态检测器：比较本次与上次 MACD/Signal 判断金叉或死叉。"""

    def __init__(self):
        self._prev_macd: float | None = None
        self._prev_signal: float | None = None

    def check(
        self,
        market_data: MarketData,
        indicators: Indicators,
        position: object | None,
    ) -> Optional[TriggerEvent]:
        curr_macd = indicators.macd
        curr_signal = indicators.macd_signal

        if self._prev_macd is None or self._prev_signal is None:
            self._prev_macd = curr_macd
            self._prev_signal = curr_signal
            return None

        prev_diff = self._prev_macd - self._prev_signal
        curr_diff = curr_macd - curr_signal

        cross_type: str | None = None
        if prev_diff < 0 and curr_diff > 0:
            cross_type = "golden"
        elif prev_diff > 0 and curr_diff < 0:
            cross_type = "death"

        self._prev_macd = curr_macd
        self._prev_signal = curr_signal

        if cross_type is None:
            return None

        label = "金叉" if cross_type == "golden" else "死叉"
        return TriggerEvent(
            event_type="macd_cross",
            description=f"MACD {label} (MACD={curr_macd:.4f}, Signal={curr_signal:.4f})",
            severity="medium",
            key_data={
                "cross_type": cross_type,
                "macd": curr_macd,
                "macd_signal": curr_signal,
            },
        )
