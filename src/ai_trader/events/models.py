"""TriggerEvent 数据模型 — 市场事件驱动 LLM 触发的核心数据容器。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class TriggerEvent:
    """表示一个可触发 LLM 决策的市场事件。"""

    event_type: str
    description: str
    severity: str  # "high" / "medium" / "low"
    key_data: dict
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def format_for_prompt(self) -> str:
        """将事件格式化为可注入 LLM prompt 的文本。"""
        key_data_str = json.dumps(self.key_data, ensure_ascii=False, default=str)
        return (
            f"[Event] {self.event_type} | severity={self.severity}\n"
            f"  description: {self.description}\n"
            f"  key_data: {key_data_str}\n"
            f"  timestamp: {self.timestamp.isoformat()}"
        )
