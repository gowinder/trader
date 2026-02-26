"""BollingerBreakDetector — 布林带突破检测器。"""

from __future__ import annotations

from typing import Optional

from ai_trader.events.detectors.base import BaseDetector
from ai_trader.events.models import TriggerEvent
from ai_trader.models.market import Indicators, MarketData


class BollingerBreakDetector(BaseDetector):
    """检测价格是否突破布林带上/下轨。"""

    def check(
        self,
        market_data: MarketData,
        indicators: Indicators,
        position: object | None,
    ) -> Optional[TriggerEvent]:
        price = market_data.current_price
        middle = indicators.boll_middle

        if price > indicators.boll_upper:
            deviation_pct = ((price - middle) / middle) * 100 if middle else 0.0
            return TriggerEvent(
                event_type="bollinger_break",
                description=f"价格突破布林上轨: {price:.2f} > {indicators.boll_upper:.2f}",
                severity="medium",
                key_data={
                    "direction": "upper",
                    "deviation_pct": round(deviation_pct, 4),
                    "price": price,
                    "boll_upper": indicators.boll_upper,
                },
            )

        if price < indicators.boll_lower:
            deviation_pct = ((price - middle) / middle) * 100 if middle else 0.0
            return TriggerEvent(
                event_type="bollinger_break",
                description=f"价格突破布林下轨: {price:.2f} < {indicators.boll_lower:.2f}",
                severity="medium",
                key_data={
                    "direction": "lower",
                    "deviation_pct": round(deviation_pct, 4),
                    "price": price,
                    "boll_lower": indicators.boll_lower,
                },
            )

        return None
