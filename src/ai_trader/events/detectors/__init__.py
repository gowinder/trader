"""事件检测器集合 — 导出所有 7 个市场事件检测器。"""

from ai_trader.events.detectors.base import BaseDetector
from ai_trader.events.detectors.bollinger_break import BollingerBreakDetector
from ai_trader.events.detectors.macd_cross import MACDCrossDetector
from ai_trader.events.detectors.market_state_change import MarketStateChangeDetector
from ai_trader.events.detectors.position_pnl import PositionPnLDetector
from ai_trader.events.detectors.price_surge import PriceSurgeDetector
from ai_trader.events.detectors.rsi_extreme import RSIExtremeDetector
from ai_trader.events.detectors.volume_spike import VolumeSpikeDetector

__all__ = [
    "BaseDetector",
    "BollingerBreakDetector",
    "MACDCrossDetector",
    "MarketStateChangeDetector",
    "PositionPnLDetector",
    "PriceSurgeDetector",
    "RSIExtremeDetector",
    "VolumeSpikeDetector",
]
