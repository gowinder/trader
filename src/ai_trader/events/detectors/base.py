"""BaseDetector — 事件检测器抽象基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ai_trader.events.models import TriggerEvent
    from ai_trader.models.market import Indicators, MarketData


class BaseDetector(ABC):
    """所有市场事件检测器的抽象基类。"""

    @abstractmethod
    def check(
        self,
        market_data: MarketData,
        indicators: Indicators,
        position: object | None,
    ) -> Optional[TriggerEvent]:
        """检测市场事件，返回 TriggerEvent 或 None。"""
        ...
