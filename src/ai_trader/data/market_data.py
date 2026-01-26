"""市场数据聚合模块"""

from typing import List, Optional
from ..exchange.base import BaseExchange
from ..models.market import MarketData, Kline, Indicators
from .indicators import calculate_indicators
from ..utils.logger import logger


class MarketDataManager:
    """市场数据管理器"""

    def __init__(self, client: BaseExchange):
        self.client = client

    async def get_market_data(
        self, symbol: str, interval: str = "15m", limit: int = 150
    ) -> Optional[MarketData]:
        """获取并聚合市场数据"""
        try:
            # Fetch Ticker - now returns Ticker model
            ticker = await self.client.get_ticker(symbol)
            current_price = ticker.last_price

            # Fetch Klines - now returns List[Kline]
            klines = await self.client.get_klines(symbol, interval, limit)
            if not klines:
                logger.warning(f"No klines found for {symbol}")
                return None

            # Sort by time just in case
            klines.sort(key=lambda x: x.timestamp)

            # Calculate Indicators
            indicators = calculate_indicators(klines)

            # Extract 24h data from ticker
            high_24h = ticker.high_24h
            low_24h = ticker.low_24h
            change_24h = ticker.change_24h
            volume_24h = ticker.volume_24h

            return MarketData(
                symbol=symbol,
                current_price=current_price,
                klines=klines,
                interval=interval,
                indicators=indicators,
                high_24h=high_24h,
                low_24h=low_24h,
                change_24h=round(change_24h, 2),
                volume_24h=volume_24h,
            )

        except Exception as e:
            logger.error(f"Error getting market data: {e}")
            return None
