"""ai_trader.events — 市场事件驱动触发模块。"""

from ai_trader.events.models import TriggerEvent
from ai_trader.events.config import DEFAULT_EVENT_TRIGGER_CONFIG, STRATEGY_EVENT_DEFAULTS

__all__ = [
    "TriggerEvent",
    "STRATEGY_EVENT_DEFAULTS",
    "DEFAULT_EVENT_TRIGGER_CONFIG",
]
