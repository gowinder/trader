"""VolumeSpikeDetector — 成交量异常放大检测器。"""

from __future__ import annotations

from typing import Optional

from ai_trader.events.detectors.base import BaseDetector
from ai_trader.events.models import TriggerEvent
from ai_trader.models.market import Indicators, MarketData


class VolumeSpikeDetector(BaseDetector):
    """检测最新 K 线成交量是否相比前 20 根均值异常放大。"""

    def __init__(self, volume_multiplier: float = 2.5):
        self.volume_multiplier = volume_multiplier

    def check(
        self,
        market_data: MarketData,
        indicators: Indicators,
        position: object | None,
    ) -> Optional[TriggerEvent]:
        klines = market_data.klines
        if len(klines) < 2:
            return None

        latest_vol = klines[-1].volume
        prev_klines = klines[-21:-1] if len(klines) >= 21 else klines[:-1]

        if not prev_klines:
            return None

        avg_vol = sum(k.volume for k in prev_klines) / len(prev_klines)
        if avg_vol <= 0:
            return None

        ratio = latest_vol / avg_vol
        if ratio <= self.volume_multiplier:
            return None

        severity = "high" if ratio > 4.0 else "medium"

        return TriggerEvent(
            event_type="volume_spike",
            description=f"成交量异常放大: {ratio:.1f}x (均值 {avg_vol:.0f})",
            severity=severity,
            key_data={
                "volume_ratio": round(ratio, 4),
                "latest_volume": latest_vol,
                "avg_volume": round(avg_vol, 2),
            },
        )
