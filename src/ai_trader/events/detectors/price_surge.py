"""PriceSurgeDetector — 价格急变检测器。"""

from __future__ import annotations

import re
from typing import Optional

from ai_trader.events.detectors.base import BaseDetector
from ai_trader.events.models import TriggerEvent
from ai_trader.models.market import Indicators, MarketData


class PriceSurgeDetector(BaseDetector):
    """检测价格在 lookback 窗口内是否发生超过 ATR 倍数的急变。"""

    def __init__(self, atr_multiplier: float = 1.5, lookback_seconds: int = 300):
        self.atr_multiplier = atr_multiplier
        self.lookback_seconds = lookback_seconds

    def check(
        self,
        market_data: MarketData,
        indicators: Indicators,
        position: object | None,
    ) -> Optional[TriggerEvent]:
        if not market_data.klines or indicators.atr <= 0:
            return None

        interval_minutes = self._parse_interval(market_data.interval)
        bars_back = max(1, int(self.lookback_seconds / (interval_minutes * 60)))

        if bars_back >= len(market_data.klines):
            return None

        ref_price = market_data.klines[-(bars_back + 1)].close
        price_change = market_data.current_price - ref_price
        abs_change = abs(price_change)
        threshold = indicators.atr * self.atr_multiplier

        if abs_change <= threshold:
            return None

        atr_ratio = abs_change / indicators.atr
        direction = "up" if price_change > 0 else "down"
        severity = "high" if abs_change > 2 * indicators.atr else "medium"
        pct = (price_change / ref_price) * 100 if ref_price != 0 else 0.0

        return TriggerEvent(
            event_type="price_surge",
            description=f"价格急变 {direction}: {pct:+.2f}% (ATR ratio {atr_ratio:.1f}x)",
            severity=severity,
            key_data={
                "price_change_pct": round(pct, 4),
                "atr_ratio": round(atr_ratio, 4),
                "direction": direction,
            },
        )

    @staticmethod
    def _parse_interval(interval: str) -> int:
        """将 '5m', '1h', '15m' 等解析为分钟数。"""
        m = re.match(r"(\d+)([mhd])", interval.lower())
        if not m:
            return 5  # fallback
        val, unit = int(m.group(1)), m.group(2)
        if unit == "h":
            return val * 60
        if unit == "d":
            return val * 1440
        return val
