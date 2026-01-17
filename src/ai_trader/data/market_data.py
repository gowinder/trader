"""市场数据聚合模块"""

from typing import List, Optional
from ..exchange.weex_client import WeexClient
from ..models.market import MarketData, Kline, Indicators
from .indicators import calculate_indicators
from ..utils.logger import logger


class MarketDataManager:
    """市场数据管理器"""

    def __init__(self, client: WeexClient):
        self.client = client

    async def get_market_data(
        self, symbol: str, interval: str = "15m", limit: int = 150
    ) -> Optional[MarketData]:
        """获取并聚合市场数据"""
        try:
            # 1. 并行获取 K线 和 Ticker (Plan sequence shows serial, but parallel is better. Let's do serial for simplicity as per plan)
            # Fetch Ticker
            ticker_res = await self.client.get_ticker(symbol)
            if ticker_res.get("code") != "00000":
                logger.error(
                    f"Failed to get ticker for {symbol}: code={ticker_res.get('code')}, "
                    f"msg={ticker_res.get('msg')}, data={ticker_res.get('data')}"
                )
                return None

            ticker_data = ticker_res.get("data", {})
            current_price = float(ticker_data.get("last", 0))

            # Fetch Klines
            raw_klines = await self.client.get_klines(symbol, interval, limit)
            if not raw_klines:
                logger.warning(f"No klines found for {symbol}")
                return None

            # Parse Klines
            klines: List[Kline] = []
            for k in raw_klines:
                # WEEX candles format: [timestamp, open, high, low, close, volume, value]
                # Raw array format
                try:
                    klines.append(
                        Kline(
                            timestamp=int(k[0]),
                            open=float(k[1]),
                            high=float(k[2]),
                            low=float(k[3]),
                            close=float(k[4]),
                            volume=float(k[5]),
                        )
                    )
                except (ValueError, IndexError) as e:
                    logger.warning(f"Error parsing kline: {k}, {e}")
                    continue

            # Sort by time just in case
            klines.sort(key=lambda x: x.timestamp)

            # Calculate Indicators
            indicators = calculate_indicators(klines)

            # Calculate 24h change
            # Use ticker data if available
            high_24h = float(ticker_data.get("high24h", 0))
            low_24h = float(ticker_data.get("low24h", 0))
            # Weex might not provide 'change_24h' directly, or calculated from open24h
            # Let's assume ticker provides it or calculate approx
            # Some APIs provide 'open24h'
            open_24h = float(ticker_data.get("open24h", current_price))  # fallback
            change_24h = (
                ((current_price - open_24h) / open_24h * 100) if open_24h else 0.0
            )
            volume_24h = float(
                ticker_data.get("vol24h", 0)
            )  # Volume in base asset usually

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
