"""PositionPnLDetector — 持仓盈亏阈值检测器。"""

from __future__ import annotations

from typing import Optional

from ai_trader.events.detectors.base import BaseDetector
from ai_trader.events.models import TriggerEvent
from ai_trader.models.market import Indicators, MarketData


class PositionPnLDetector(BaseDetector):
    """检测持仓 ROI 是否触及盈利/亏损阈值。"""

    def __init__(self, profit_threshold: float = 3.0, loss_threshold: float = -2.0):
        self.profit_threshold = profit_threshold
        self.loss_threshold = loss_threshold

    def check(
        self,
        market_data: MarketData,
        indicators: Indicators,
        position: object | None,
    ) -> Optional[TriggerEvent]:
        if position is None or position.size <= 0:
            return None

        roi = position.roi

        if roi >= self.profit_threshold:
            return TriggerEvent(
                event_type="position_pnl",
                description=f"持仓盈利达标: ROI={roi:.2f}% (阈值 {self.profit_threshold}%)",
                severity="medium",
                key_data={
                    "roi": roi,
                    "zone": "profit",
                    "threshold": self.profit_threshold,
                },
            )

        if roi <= self.loss_threshold:
            return TriggerEvent(
                event_type="position_pnl",
                description=f"持仓亏损预警: ROI={roi:.2f}% (阈值 {self.loss_threshold}%)",
                severity="high",
                key_data={
                    "roi": roi,
                    "zone": "loss",
                    "threshold": self.loss_threshold,
                },
            )

        return None
