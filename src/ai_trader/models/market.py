"""市场数据模型"""

from pydantic import BaseModel, Field
from typing import List, Optional


class Indicators(BaseModel):
    """技术指标"""

    ma7: float
    ma25: float
    ma99: float
    rsi: float
    macd: float
    macd_signal: float
    macd_histogram: float
    boll_upper: float
    boll_middle: float
    boll_lower: float
    atr: float


class Kline(BaseModel):
    """K线数据"""

    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float


class MarketData(BaseModel):
    """市场聚合数据"""

    symbol: str
    current_price: float
    klines: List[Kline]
    interval: str
    indicators: Indicators

    # 24h 统计
    high_24h: float
    low_24h: float
    change_24h: float
    volume_24h: float
