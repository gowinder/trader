"""CCXT Spot adapter for spot trading (e.g., Kraken XStock tokenized stocks)"""

import ccxt.async_support as ccxt
from typing import List, Optional
from datetime import datetime

from .ccxt_adapter import CCXTAdapter
from .base import AccountInfo, Position, Ticker, OrderSide, OrderType
from ..models.market import Kline
from ..utils.logger import logger


class CCXTSpotAdapter(CCXTAdapter):
    """CCXT adapter for spot trading, extends CCXTAdapter with spot-specific overrides.

    Key differences from futures CCXTAdapter:
    - defaultType: "spot" instead of "swap"
    - get_account: uses USD balance instead of USDT
    - get_positions: derives from spot balance, not fetch_positions
    - set_leverage: no-op for spot
    - create_order: no reduceOnly parameter
    """

    @classmethod
    def from_config(
        cls,
        exchange_id: str,
        api_key: str,
        api_secret: str,
        passphrase: Optional[str] = None,
        testnet: bool = False,
        proxy: Optional[str] = None,
    ) -> "CCXTSpotAdapter":
        """Create spot adapter from configuration.

        Overrides CCXTAdapter.from_config to use defaultType='spot'.
        """
        exchange_class = getattr(ccxt, exchange_id, None)
        if exchange_class is None:
            raise ValueError(f"CCXT does not support exchange: {exchange_id}")

        config = {
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        }

        if passphrase:
            config["password"] = passphrase

        if proxy:
            config["proxies"] = {"http": proxy, "https": proxy}

        exchange = exchange_class(config)

        if testnet:
            if hasattr(exchange, "set_sandbox_mode"):
                exchange.set_sandbox_mode(True)
                logger.info(f"{exchange_id} switched to Testnet mode")

        return cls(exchange)

    async def get_account(self) -> AccountInfo:
        """Get account information using USD balance (for tokenized stocks)."""
        try:
            balance = await self._exchange.fetch_balance()
            usd = balance.get("USD", {})
            return AccountInfo(
                total_equity=float(usd.get("total", 0)),
                available_balance=float(usd.get("free", 0)),
                margin_used=float(usd.get("used", 0)),
                unrealized_pnl=0.0,
            )
        except ccxt.BaseError as e:
            logger.error(f"Spot get account failed: {e}")
            raise

    async def get_positions(self, symbol: str) -> List[Position]:
        """Get positions by checking spot balance.

        For spot trading, 'position' means holding the base currency.
        """
        try:
            balance = await self._exchange.fetch_balance()
            positions = []

            # Extract base currency from symbol (e.g., "AAPLx/USD" -> "AAPLx")
            base_currency = symbol.split("/")[0] if "/" in symbol else symbol
            amount = float(balance.get(base_currency, {}).get("total", 0))

            if amount > 0:
                ticker = await self._exchange.fetch_ticker(symbol)
                mark_price = float(ticker.get("last", 0))

                positions.append(Position(
                    symbol=symbol,
                    side="long",
                    size=float(amount),
                    entry_price=mark_price,
                    mark_price=mark_price,
                    unrealized_pnl=0.0,
                    leverage=1,
                    margin_mode="spot",
                    liquidation_price=None,
                    margin=float(amount) * mark_price,
                    roi=0.0,
                ))

            return positions
        except ccxt.BaseError as e:
            logger.error(f"Spot get positions failed: {e}")
            raise

    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        """No-op for spot trading (no leverage)."""
        return True

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
        """Create order for spot trading.

        No reduceOnly parameter for spot orders.
        """
        try:
            ccxt_side = (
                "buy"
                if side in [OrderSide.OPEN_LONG, OrderSide.CLOSE_SHORT]
                else "sell"
            )
            ccxt_type = order_type.value

            # Spot orders: no reduceOnly
            params = {}

            result = await self._exchange.create_order(
                symbol=symbol,
                type=ccxt_type,
                side=ccxt_side,
                amount=size,
                price=price,
                params=params,
            )

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
            logger.error(f"Spot create order failed: {e}")
            raise

    async def get_available_symbols(self) -> List[str]:
        """Get available spot trading pairs with USD quote."""
        try:
            markets = await self._exchange.load_markets()
            symbols = []
            for symbol, market in markets.items():
                if (
                    market.get("spot", False)
                    and market.get("active", True)
                    and market.get("quote") == "USD"
                ):
                    symbols.append(symbol)
            symbols.sort()
            return symbols
        except ccxt.BaseError as e:
            logger.error(f"Spot get available symbols failed: {e}")
            return []
