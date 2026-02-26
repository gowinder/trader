"""MarketStateChangeDetector — 市场状态变更检测器。"""

from __future__ import annotations

from typing import Optional

from ai_trader.events.models import TriggerEvent


class MarketStateChangeDetector:
    """有状态检测器：检测市场状态切换（如 sideways -> breakout）。

    注意：此检测器接口与 BaseDetector 不同，使用 check_state_change(state)。
    """

    def __init__(self):
        self._prev_state: str | None = None

    def check_state_change(self, current_state: str) -> Optional[TriggerEvent]:
        """检测状态变更，返回 TriggerEvent 或 None。"""
        if self._prev_state is None:
            self._prev_state = current_state
            return None

        if current_state == self._prev_state:
            return None

        prev = self._prev_state
        self._prev_state = current_state

        severity = "high" if current_state == "breakout" else "medium"

        return TriggerEvent(
            event_type="market_state_change",
            description=f"市场状态变更: {prev} -> {current_state}",
            severity=severity,
            key_data={
                "prev_state": prev,
                "new_state": current_state,
            },
        )
