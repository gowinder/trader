"""Binance exchange adapter using CCXT

Supports both live and testnet environments for futures trading.
"""

from typing import List, Optional, Dict, Any
import ccxt.async_support as ccxt
from .base import (
    BaseExchange,
    AccountInfo,
    Ticker,
    Position,
    OrderSide,
    OrderType,
)
from ..models.market import Kline
from ..utils.logger import logger


class BinanceAdapter(BaseExchange):
    """Binance exchange implementation via CCXT

    Supports:
    - USDT-Margined Futures (perpetual contracts)
    - Testnet environment
    - Hedge mode (dual-direction positions)
    - Isolated and Cross margin modes
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        testnet: bool = False,
        proxy: Optional[str] = None,
    ):
        """Initialize Binance adapter

        Args:
            api_key: API key (testnet or production)
            api_secret: API secret
            testnet: Use testnet environment if True
            proxy: HTTP proxy URL (optional)
        """
        self.testnet = testnet

        # Initialize CCXT exchange
        config: Dict[str, Any] = {
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "options": {
                "defaultType": "future",  # USDT-M Futures
            },
        }

        # Add proxy if explicitly provided (do not auto-detect from env for testnet)
        if proxy:
            config["aiohttp_proxy"] = proxy
        elif testnet:
            # Explicitly disable proxy for testnet to prevent aiohttp auto-detection
            config["aiohttp_proxy"] = None
            config["aiohttp_trust_env"] = False
        else:
            # Only use env proxy for production, not testnet
            import os
            http_proxy = os.getenv('HTTP_PROXY') or os.getenv('http_proxy')
            if http_proxy:
                config["aiohttp_proxy"] = http_proxy

        self.exchange = ccxt.binance(config)

        # Enable sandbox mode for testnet
        # Note: CCXT uses set_sandbox_mode() to configure testnet URLs
        if testnet:
            self.exchange.set_sandbox_mode(True)
            # Override spot testnet URLs to use futures testnet
            # This avoids 451 errors from spot testnet geo-restrictions
            if hasattr(self.exchange, 'urls') and isinstance(self.exchange.urls, dict):
                api = self.exchange.urls.get('api', {})
                if isinstance(api, dict):
                    # Point spot endpoints to futures testnet to avoid geo-restrictions
                    api['public'] = 'https://testnet.binancefuture.com/fapi/v1'
                    api['private'] = 'https://testnet.binancefuture.com/fapi/v1'

        # Safe URL logging
        url_info = "testnet" if testnet else "production"
        if hasattr(self.exchange, "urls") and isinstance(self.exchange.urls, dict):
            try:
                url_info = self.exchange.urls.get("api", {}).get("fapi", url_info)
            except (AttributeError, TypeError):
                pass

        logger.info(f"BinanceAdapter initialized (testnet={testnet}, url={url_info})")

    async def close(self):
        """Close exchange connection"""
        if hasattr(self.exchange, "close"):
            await self.exchange.close()

    async def get_account(self) -> AccountInfo:
        """Retrieve account balance and equity

        Returns:
            AccountInfo: Account information with balances
        """
        try:
            balance = await self.exchange.fetch_balance({"type": "future"})

            # Binance futures balance structure:
            # balance['total']['USDT'] = total equity
            # balance['free']['USDT'] = available balance
            # balance['used']['USDT'] = margin used

            total = balance.get("total", {})
            free = balance.get("free", {})
            used = balance.get("used", {})

            # Extract USDT balance (default currency for USDT-M futures)
            total_equity = float(total.get("USDT", 0.0))
            available_balance = float(free.get("USDT", 0.0))
            margin_used = float(used.get("USDT", 0.0))

            # Calculate unrealized PnL from positions
            positions = await self._fetch_positions()
            unrealized_pnl = sum(
                float(pos.get("unrealizedPnl", 0)) for pos in positions
            )

            return AccountInfo(
                total_equity=total_equity,
                available_balance=available_balance,
                margin_used=margin_used,
                unrealized_pnl=unrealized_pnl,
            )

        except Exception as e:
            logger.error(f"Failed to fetch account: {e}")
            raise

    async def get_ticker(self, symbol: str) -> Ticker:
        """Retrieve ticker data

        Args:
            symbol: Trading symbol (e.g., 'BTC/USDT:USDT')

        Returns:
            Ticker: Current ticker information
        """
        try:
            ticker = await self.exchange.fetch_ticker(symbol)

            # Helper to safely convert to float
            def safe_float(value, default=0.0):
                return float(value) if value is not None else default

            return Ticker(
                symbol=ticker["symbol"],
                last_price=safe_float(ticker.get("last") or ticker.get("close"), 0),
                bid_price=safe_float(ticker.get("bid"), 0),
                ask_price=safe_float(ticker.get("ask"), 0),
                high_24h=safe_float(ticker.get("high"), 0),
                low_24h=safe_float(ticker.get("low"), 0),
                volume_24h=safe_float(ticker.get("baseVolume"), 0),
                change_24h=safe_float(ticker.get("percentage"), 0),
                timestamp=ticker.get("timestamp", 0),
            )

        except Exception as e:
            logger.error(f"Failed to fetch ticker for {symbol}: {e}")
            raise

    async def get_klines(
        self, symbol: str, interval: str = "15m", limit: int = 100
    ) -> List[Kline]:
        """Retrieve candlestick data

        Args:
            symbol: Trading symbol
            interval: Timeframe (e.g., '1m', '5m', '15m', '1h', '4h', '1d')
            limit: Number of klines to retrieve

        Returns:
            List[Kline]: List of kline objects
        """
        try:
            ohlcv = await self.exchange.fetch_ohlcv(symbol, interval, limit=limit)

            return [
                Kline(
                    timestamp=k[0],
                    open=float(k[1]),
                    high=float(k[2]),
                    low=float(k[3]),
                    close=float(k[4]),
                    volume=float(k[5]),
                )
                for k in ohlcv
            ]

        except Exception as e:
            logger.error(f"Failed to fetch klines for {symbol}: {e}")
            raise

    async def get_positions(self, symbol: str) -> List[Position]:
        """Retrieve open positions

        Args:
            symbol: Trading symbol (e.g., 'BTC/USDT:USDT')

        Returns:
            List[Position]: List of open positions (may contain both LONG and SHORT in hedge mode)
        """
        try:
            positions = await self._fetch_positions()

            # Filter by symbol and convert to Position model
            result = []
            for pos in positions:
                if pos["symbol"] != symbol:
                    continue

                size = abs(float(pos.get("contracts", 0)))
                if size == 0:
                    continue

                # Determine side (LONG or SHORT in CCXT, convert to lowercase)
                side_str = pos.get("side", "").lower()
                if side_str not in ["long", "short"]:
                    continue

                entry_price = float(pos.get("entryPrice", 0))
                mark_price = float(pos.get("markPrice", 0))
                unrealized_pnl = float(pos.get("unrealizedPnl", 0))
                leverage = int(pos.get("leverage", 1))

                # Calculate margin and ROI
                margin = (size * entry_price) / leverage if leverage > 0 and entry_price > 0 else 0.0
                roi = (unrealized_pnl / margin * 100) if margin > 0 else 0.0

                result.append(
                    Position(
                        symbol=pos["symbol"],
                        side=side_str,
                        size=size,
                        entry_price=entry_price,
                        mark_price=mark_price,
                        liquidation_price=float(pos.get("liquidationPrice", 0)),
                        unrealized_pnl=unrealized_pnl,
                        leverage=leverage,
                        margin_mode=pos.get("marginType", "cross").lower(),
                        margin=margin,
                        roi=roi,
                    )
                )

            return result

        except Exception as e:
            logger.error(f"Failed to fetch positions for {symbol}: {e}")
            raise

    async def _fetch_positions(self) -> List[Dict[str, Any]]:
        """Internal method to fetch all positions from exchange

        Returns:
            List[Dict]: Raw position data from CCXT
        """
        positions = await self.exchange.fetch_positions()
        return positions if positions else []

    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        """Set leverage for symbol

        Args:
            symbol: Trading symbol
            leverage: Leverage value (1-125 for Binance)

        Returns:
            bool: True if successful
        """
        try:
            await self.exchange.set_leverage(leverage, symbol)
            logger.info(f"Set leverage {leverage}x for {symbol}")
            return True

        except Exception as e:
            logger.error(f"Failed to set leverage for {symbol}: {e}")
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
        reduce_only: bool = False,
    ) -> dict:
        """Create order

        Args:
            symbol: Trading symbol
            side: Order side (OPEN_LONG, OPEN_SHORT, CLOSE_LONG, CLOSE_SHORT)
            order_type: Order type (MARKET or LIMIT)
            size: Order size (contracts)
            price: Limit price (required for LIMIT orders)
            stop_loss: Stop-loss price (optional)
            take_profit: Take-profit price (optional)
            reduce_only: Reduce-only flag (for closing positions)

        Returns:
            dict: Order result from exchange
        """
        try:
            # Map internal side to CCXT side and position side
            ccxt_side, position_side = self._map_order_side(side)

            # Validate limit order price
            if order_type == OrderType.LIMIT and price is None:
                raise ValueError("Limit order requires price parameter")

            # Build order parameters
            params = {
                "positionSide": position_side,  # LONG or SHORT (hedge mode)
            }

            if reduce_only:
                params["reduceOnly"] = True

            # Create main order
            order = await self.exchange.create_order(
                symbol=symbol,
                type=order_type.value.lower(),  # 'market' or 'limit'
                side=ccxt_side,  # 'buy' or 'sell'
                amount=size,
                price=price,
                params=params,
            )

            logger.info(
                f"Order created: {order['id']} - {side.value} {size} {symbol} @ {price or 'market'}"
            )

            # Create stop-loss order if specified
            if stop_loss:
                await self._create_stop_order(
                    symbol, size, stop_loss, "STOP_LOSS", position_side
                )

            # Create take-profit order if specified
            if take_profit:
                await self._create_stop_order(
                    symbol, size, take_profit, "TAKE_PROFIT", position_side
                )

            return {
                "code": "00000",
                "data": {
                    "orderId": order["id"],
                    "symbol": order["symbol"],
                    "status": order["status"],
                },
            }

        except Exception as e:
            logger.error(f"Failed to create order: {e}")
            return {"code": "ERROR", "msg": str(e)}

    def _map_order_side(self, side: OrderSide) -> tuple[str, str]:
        """Map internal OrderSide to CCXT side and position side

        Args:
            side: Internal order side enum

        Returns:
            tuple: (ccxt_side, position_side)
                ccxt_side: 'buy' or 'sell'
                position_side: 'LONG' or 'SHORT' (for hedge mode)
        """
        mapping = {
            OrderSide.OPEN_LONG: ("buy", "LONG"),
            OrderSide.OPEN_SHORT: ("sell", "SHORT"),
            OrderSide.CLOSE_LONG: ("sell", "LONG"),
            OrderSide.CLOSE_SHORT: ("buy", "SHORT"),
        }
        return mapping[side]

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """Cancel order

        Args:
            symbol: Trading symbol
            order_id: Order ID to cancel

        Returns:
            bool: True if successful
        """
        try:
            await self.exchange.cancel_order(order_id, symbol)
            logger.info(f"Order cancelled: {order_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

    async def _create_stop_order(
        self,
        symbol: str,
        size: float,
        stop_price: float,
        order_type: str,
        position_side: str,
    ):
        """Create stop-loss or take-profit order

        Args:
            symbol: Trading symbol
            size: Order size
            stop_price: Stop trigger price
            order_type: 'STOP_LOSS' or 'TAKE_PROFIT'
            position_side: 'LONG' or 'SHORT'
        """
        try:
            # Determine order side based on position side
            # For LONG position: stop/tp orders are SELL
            # For SHORT position: stop/tp orders are BUY
            side = "sell" if position_side == "LONG" else "buy"

            # Use different order types for stop-loss vs take-profit
            binance_order_type = "STOP_MARKET" if order_type == "STOP_LOSS" else "TAKE_PROFIT_MARKET"
            ccxt_order_type = "stop_market" if order_type == "STOP_LOSS" else "take_profit_market"

            params = {
                "positionSide": position_side,
                "stopPrice": stop_price,
                "type": binance_order_type,
            }

            order = await self.exchange.create_order(
                symbol=symbol,
                type=ccxt_order_type,
                side=side,
                amount=size,
                params=params,
            )

            logger.info(
                f"{order_type} order created: {order['id']} @ {stop_price} ({position_side})"
            )

        except Exception as e:
            logger.warning(f"Failed to create {order_type} order: {e}")
