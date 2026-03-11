"""CCXT unified adapter for multiple exchanges"""

import ccxt.async_support as ccxt
from typing import List, Optional
from datetime import datetime

from .base import (
    BaseExchange,
    AccountInfo,
    Ticker,
    Position,
    OrderSide,
    OrderType,
)
from ..models.market import Kline
from ..models.order import Order
from ..utils.logger import logger


class CCXTAdapter(BaseExchange):
    """CCXT unified exchange adapter"""

    # Interval mapping: internal format -> CCXT format
    INTERVAL_MAP = {
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "30m": "30m",
        "1h": "1h",
        "4h": "4h",
        "1d": "1d",
        "1w": "1w",
    }

    def __init__(self, exchange: ccxt.Exchange):
        self._exchange = exchange
        self._exchange_id = exchange.id

    @classmethod
    def from_config(
        cls,
        exchange_id: str,
        api_key: str,
        api_secret: str,
        passphrase: Optional[str] = None,
        testnet: bool = False,
        proxy: Optional[str] = None,
    ) -> "CCXTAdapter":
        """Create adapter from configuration

        Args:
            exchange_id: Exchange identifier (e.g., 'binance', 'bybit')
            api_key: API key
            api_secret: API secret
            passphrase: API passphrase (for exchanges like OKX)
            testnet: Use testnet/sandbox mode
            proxy: Proxy URL (e.g., 'http://127.0.0.1:7890')

        Returns:
            CCXTAdapter instance

        Raises:
            ValueError: If exchange is not supported or testnet mode unavailable
        """
        exchange_class = getattr(ccxt, exchange_id, None)
        if exchange_class is None:
            raise ValueError(f"CCXT does not support exchange: {exchange_id}")

        config = {
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "options": {"defaultType": "swap"},  # Use perpetual futures
        }

        if passphrase:
            config["password"] = passphrase

        if proxy:
            config["proxies"] = {"http": proxy, "https": proxy}

        exchange = exchange_class(config)

        # Testnet switching - strict mode: reject if not supported
        # Binance futures testnet is deprecated, use demo trading instead
        if testnet:
            if exchange_id == "binance" and hasattr(exchange, "enable_demo_trading"):
                exchange.enable_demo_trading(True)
                logger.info(f"{exchange_id} switched to Demo Trading mode")
            elif hasattr(exchange, "set_sandbox_mode"):
                exchange.set_sandbox_mode(True)
                logger.info(f"{exchange_id} switched to Testnet mode")
            else:
                raise ValueError(
                    f"{exchange_id} does not support testnet/demo mode. "
                    f"Exchanges supporting Testnet: binance (demo), bybit (sandbox)"
                )

        return cls(exchange)

    async def get_account(self) -> AccountInfo:
        """Get account information"""
        try:
            balance = await self._exchange.fetch_balance()
            usdt = balance.get("USDT", {})
            return AccountInfo(
                total_equity=float(usdt.get("total", 0)),
                available_balance=float(usdt.get("free", 0)),
                margin_used=float(usdt.get("used", 0)),
                unrealized_pnl=0.0,  # Need to aggregate from positions
            )
        except ccxt.BaseError as e:
            logger.error(f"CCXT get account failed: {e}")
            raise

    async def get_klines(
        self, symbol: str, interval: str = "15m", limit: int = 100
    ) -> List[Kline]:
        """Get kline/candlestick data"""
        try:
            ccxt_interval = self.INTERVAL_MAP.get(interval, interval)
            ohlcv = await self._exchange.fetch_ohlcv(
                symbol, timeframe=ccxt_interval, limit=limit
            )
            return [
                Kline(
                    timestamp=int(candle[0]),
                    open=float(candle[1]),
                    high=float(candle[2]),
                    low=float(candle[3]),
                    close=float(candle[4]),
                    volume=float(candle[5]),
                )
                for candle in ohlcv
            ]
        except ccxt.BaseError as e:
            logger.error(f"CCXT get klines failed: {e}")
            raise

    async def get_ticker(self, symbol: str) -> Ticker:
        """Get real-time market ticker"""
        try:
            ticker = await self._exchange.fetch_ticker(symbol)
            return Ticker(
                symbol=symbol,
                last_price=float(ticker.get("last", 0)),
                bid_price=float(ticker.get("bid", 0)),
                ask_price=float(ticker.get("ask", 0)),
                high_24h=float(ticker.get("high", 0)),
                low_24h=float(ticker.get("low", 0)),
                volume_24h=float(ticker.get("baseVolume", 0)),
                change_24h=float(ticker.get("percentage", 0)),
            )
        except ccxt.BaseError as e:
            logger.error(f"CCXT get ticker failed: {e}")
            raise

    async def get_positions(self, symbol: str) -> List[Position]:
        """Get position information"""
        try:
            positions = await self._exchange.fetch_positions([symbol])
            return [
                Position(
                    symbol=pos["symbol"],
                    side="long" if pos["side"] == "long" else "short",
                    size=abs(float(pos.get("contracts", 0))),
                    entry_price=float(pos.get("entryPrice", 0)),
                    mark_price=float(pos.get("markPrice", 0)),
                    unrealized_pnl=float(pos.get("unrealizedPnl", 0)),
                    leverage=int(pos.get("leverage", 1)),
                    margin_mode=pos.get("marginMode", "cross"),
                    liquidation_price=pos.get("liquidationPrice"),
                )
                for pos in positions
                if float(pos.get("contracts", 0)) != 0
            ]
        except ccxt.BaseError as e:
            logger.error(f"CCXT get positions failed: {e}")
            raise

    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        """Set leverage multiplier"""
        try:
            await self._exchange.set_leverage(leverage, symbol)
            return True
        except ccxt.BaseError as e:
            logger.error(f"CCXT set leverage failed: {e}")
            return False

    async def create_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        size: float,
        price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> dict:
        """Create order

        Note: Stop loss/take profit parameter format varies by exchange
        - Binance: Requires separate stop loss/take profit orders
        - Bybit: Supports attaching when placing order
        - This is a simplified version; actual usage requires exchange-specific adaptation
        - Recommended: Use dedicated adapters (e.g., BinanceAdapter) for stop loss/take profit
        """
        try:
            # Map direction
            ccxt_side = (
                "buy"
                if side in [OrderSide.OPEN_LONG, OrderSide.CLOSE_SHORT]
                else "sell"
            )
            ccxt_type = order_type.value

            params = {}
            if side in [OrderSide.CLOSE_LONG, OrderSide.CLOSE_SHORT]:
                params["reduceOnly"] = True

            # Note: stopLoss/takeProfit parameter format varies by exchange
            if stop_loss and self._exchange_id in ["bybit", "okx"]:
                params["stopLoss"] = {"triggerPrice": stop_loss}
            if take_profit and self._exchange_id in ["bybit", "okx"]:
                params["takeProfit"] = {"triggerPrice": take_profit}

            result = await self._exchange.create_order(
                symbol=symbol,
                type=ccxt_type,
                side=ccxt_side,
                amount=size,
                price=price,
                params=params,
            )

            # Return WEEX-compatible format for OrderManager compatibility
            return {
                "code": "00000",
                "data": {
                    "orderId": result["id"],
                    "symbol": symbol,
                    "side": side.value,
                    "orderType": order_type.value,
                    "size": size,
                    "price": price,
                    "status": result.get("status", "unknown"),
                    "filledSize": float(result.get("filled", 0)),
                    "avgPrice": result.get("average"),
                    "createdAt": datetime.now().isoformat(),
                },
            }
        except ccxt.BaseError as e:
            logger.error(f"CCXT create order failed: {e}")
            raise

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """Cancel order"""
        try:
            await self._exchange.cancel_order(order_id, symbol)
            return True
        except ccxt.BaseError as e:
            logger.error(f"CCXT cancel order failed: {e}")
            return False

    async def get_available_symbols(self) -> List[str]:
        """Get all available USDT perpetual contract symbols."""
        try:
            markets = await self._exchange.load_markets()
            symbols = []
            for symbol, market in markets.items():
                if (
                    market.get("swap", False)
                    and market.get("active", True)
                    and market.get("quote") == "USDT"
                    and market.get("settle") == "USDT"
                ):
                    symbols.append(symbol)
            symbols.sort()
            return symbols
        except ccxt.BaseError as e:
            logger.error(f"CCXT get available symbols failed: {e}")
            return []

    async def get_all_tickers(self) -> dict[str, float]:
        """获取所有交易对的 24h 成交量(USDT)，返回 {symbol: quoteVolume}"""
        try:
            tickers = await self._exchange.fetch_tickers()
            result = {}
            for symbol, t in tickers.items():
                qv = t.get("quoteVolume")
                if qv is not None:
                    result[symbol] = float(qv)
            return result
        except Exception as e:
            logger.warning(f"CCXT fetch tickers failed: {e}")
            return {}

    async def close(self):
        """Close connection and cleanup resources"""
        await self._exchange.close()
