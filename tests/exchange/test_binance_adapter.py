"""Unit tests for BinanceAdapter"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from ai_trader.exchange.binance_adapter import BinanceAdapter
from ai_trader.exchange.base import AccountInfo, Ticker, Position, OrderSide, OrderType
from ai_trader.models.market import Kline


@pytest.fixture
def mock_ccxt_binance():
    """Create a mock CCXT binance exchange"""
    with patch("ai_trader.exchange.binance_adapter.ccxt.binance") as mock:
        exchange_instance = Mock()
        exchange_instance.fetch_balance = AsyncMock()
        exchange_instance.fetch_ticker = AsyncMock()
        exchange_instance.fetch_ohlcv = AsyncMock()
        exchange_instance.fetch_positions = AsyncMock()
        exchange_instance.set_leverage = AsyncMock()
        exchange_instance.create_order = AsyncMock()
        exchange_instance.close = AsyncMock()

        mock.return_value = exchange_instance
        yield mock, exchange_instance


class TestBinanceAdapterInit:
    """Test adapter initialization"""

    def test_init_testnet_mode(self, mock_ccxt_binance):
        """Test testnet mode initialization with demo trading enabled"""
        mock_ccxt, exchange_instance = mock_ccxt_binance
        exchange_instance.enable_demo_trading = Mock()

        adapter = BinanceAdapter(
            api_key="test_key",
            api_secret="test_secret",
            testnet=True
        )

        # Verify CCXT was called with correct config
        call_args = mock_ccxt.call_args[0][0]
        assert call_args["apiKey"] == "test_key"
        assert call_args["secret"] == "test_secret"
        assert call_args["enableRateLimit"] is True
        assert call_args["options"]["defaultType"] == "future"
        # Testnet now uses enable_demo_trading instead of URL override
        exchange_instance.enable_demo_trading.assert_called_once_with(True)
        assert adapter.testnet is True

    def test_init_live_mode(self, mock_ccxt_binance):
        """Test live mode initialization without URL override"""
        mock_ccxt, _ = mock_ccxt_binance

        adapter = BinanceAdapter(
            api_key="live_key",
            api_secret="live_secret",
            testnet=False
        )

        # Verify no testnet URL override
        call_args = mock_ccxt.call_args[0][0]
        assert "urls" not in call_args.get("options", {})
        assert adapter.testnet is False

    def test_init_with_proxy(self, mock_ccxt_binance):
        """Test initialization with proxy configuration"""
        mock_ccxt, _ = mock_ccxt_binance

        adapter = BinanceAdapter(
            api_key="test_key",
            api_secret="test_secret",
            proxy="http://proxy.example.com:8080"
        )

        call_args = mock_ccxt.call_args[0][0]
        assert call_args["aiohttp_proxy"] == "http://proxy.example.com:8080"


class TestBinanceAdapterAccount:
    """Test account-related methods"""

    @pytest.mark.asyncio
    async def test_get_account_success(self, mock_ccxt_binance):
        """Test successful account balance retrieval"""
        _, exchange = mock_ccxt_binance

        # Mock balance response
        exchange.fetch_balance.return_value = {
            "total": {"USDT": 10000.0},
            "free": {"USDT": 8000.0},
            "used": {"USDT": 2000.0},
        }

        # Mock positions for unrealized PnL
        exchange.fetch_positions.return_value = [
            {"symbol": "BTC/USDT:USDT", "unrealizedPnl": 150.5},
            {"symbol": "ETH/USDT:USDT", "unrealizedPnl": -30.2},
        ]

        adapter = BinanceAdapter("key", "secret")
        account = await adapter.get_account()

        assert isinstance(account, AccountInfo)
        assert account.total_equity == 10000.0
        assert account.available_balance == 8000.0
        assert account.margin_used == 2000.0
        assert account.unrealized_pnl == 120.3  # 150.5 - 30.2


class TestBinanceAdapterMarketData:
    """Test market data retrieval methods"""

    @pytest.mark.asyncio
    async def test_get_ticker_success(self, mock_ccxt_binance):
        """Test ticker data retrieval"""
        _, exchange = mock_ccxt_binance

        exchange.fetch_ticker.return_value = {
            "symbol": "BTC/USDT:USDT",
            "last": 50000.0,
            "bid": 49995.0,
            "ask": 50005.0,
            "high": 51000.0,
            "low": 49000.0,
            "baseVolume": 12345.6,
            "timestamp": 1700000000000,
        }

        adapter = BinanceAdapter("key", "secret")
        ticker = await adapter.get_ticker("BTC/USDT:USDT")

        assert isinstance(ticker, Ticker)
        assert ticker.symbol == "BTC/USDT:USDT"
        assert ticker.last_price == 50000.0
        assert ticker.bid_price == 49995.0
        assert ticker.high_24h == 51000.0

    @pytest.mark.asyncio
    async def test_get_klines_success(self, mock_ccxt_binance):
        """Test kline data retrieval"""
        _, exchange = mock_ccxt_binance

        exchange.fetch_ohlcv.return_value = [
            [1700000000000, 50000.0, 50100.0, 49900.0, 50050.0, 100.5],
            [1700000060000, 50050.0, 50200.0, 50000.0, 50150.0, 120.3],
        ]

        adapter = BinanceAdapter("key", "secret")
        klines = await adapter.get_klines("BTC/USDT:USDT", "1m", limit=2)

        assert len(klines) == 2
        assert isinstance(klines[0], Kline)
        assert klines[0].open == 50000.0
        assert klines[0].close == 50050.0
        assert klines[1].volume == 120.3


class TestBinanceAdapterPositions:
    """Test position management"""

    @pytest.mark.asyncio
    async def test_get_positions_hedge_mode(self, mock_ccxt_binance):
        """Test position retrieval in hedge mode (both LONG and SHORT)"""
        _, exchange = mock_ccxt_binance

        exchange.fetch_positions.return_value = [
            {
                "symbol": "BTC/USDT:USDT",
                "side": "long",  # Changed to lowercase
                "contracts": 2.5,
                "entryPrice": 49000.0,
                "markPrice": 50000.0,
                "liquidationPrice": 45000.0,
                "unrealizedPnl": 2500.0,
                "leverage": 10,
                "marginType": "cross",
            },
            {
                "symbol": "BTC/USDT:USDT",
                "side": "short",  # Changed to lowercase
                "contracts": -1.0,
                "entryPrice": 51000.0,
                "markPrice": 50000.0,
                "liquidationPrice": 55000.0,
                "unrealizedPnl": 1000.0,
                "leverage": 10,
                "marginType": "isolated",
            },
            {
                "symbol": "ETH/USDT:USDT",  # Different symbol, should be filtered
                "side": "long",  # Changed to lowercase
                "contracts": 10.0,
                "entryPrice": 3000.0,
                "markPrice": 3100.0,
                "liquidationPrice": 2500.0,
                "unrealizedPnl": 1000.0,
                "leverage": 5,
                "marginType": "cross",
            },
        ]

        adapter = BinanceAdapter("key", "secret")
        positions = await adapter.get_positions("BTC/USDT:USDT")

        assert len(positions) == 2
        assert positions[0].side == "long"  # Expect lowercase
        assert positions[0].size == 2.5
        assert positions[0].margin > 0  # Check margin is calculated
        assert positions[1].side == "short"  # Expect lowercase
        assert positions[1].size == 1.0  # abs(-1.0)

    @pytest.mark.asyncio
    async def test_get_positions_no_position(self, mock_ccxt_binance):
        """Test when no position exists"""
        _, exchange = mock_ccxt_binance

        exchange.fetch_positions.return_value = [
            {"symbol": "BTC/USDT:USDT", "side": "long", "contracts": 0},
        ]

        adapter = BinanceAdapter("key", "secret")
        positions = await adapter.get_positions("BTC/USDT:USDT")

        assert len(positions) == 0


class TestBinanceAdapterOrders:
    """Test order creation and management"""

    @pytest.mark.asyncio
    async def test_set_leverage(self, mock_ccxt_binance):
        """Test leverage setting"""
        _, exchange = mock_ccxt_binance

        adapter = BinanceAdapter("key", "secret")
        result = await adapter.set_leverage("BTC/USDT:USDT", 10)

        assert result is True
        exchange.set_leverage.assert_called_once_with(10, "BTC/USDT:USDT")

    @pytest.mark.asyncio
    async def test_create_market_order_open_long(self, mock_ccxt_binance):
        """Test market order creation for opening LONG position"""
        _, exchange = mock_ccxt_binance

        exchange.create_order.return_value = {
            "id": "12345",
            "symbol": "BTC/USDT:USDT",
            "status": "closed",
        }

        adapter = BinanceAdapter("key", "secret")
        result = await adapter.create_order(
            symbol="BTC/USDT:USDT",
            side=OrderSide.OPEN_LONG,
            order_type=OrderType.MARKET,
            size=1.0,
        )

        assert result["code"] == "00000"
        assert result["data"]["orderId"] == "12345"

        # Verify create_order was called with correct parameters
        call_args = exchange.create_order.call_args
        assert call_args[1]["symbol"] == "BTC/USDT:USDT"
        assert call_args[1]["type"] == "market"
        assert call_args[1]["side"] == "buy"
        assert call_args[1]["amount"] == 1.0
        assert call_args[1]["params"]["positionSide"] == "LONG"

    @pytest.mark.asyncio
    async def test_create_limit_order_close_short(self, mock_ccxt_binance):
        """Test limit order creation for closing SHORT position"""
        _, exchange = mock_ccxt_binance

        exchange.create_order.return_value = {
            "id": "67890",
            "symbol": "BTC/USDT:USDT",
            "status": "open",
        }

        adapter = BinanceAdapter("key", "secret")
        result = await adapter.create_order(
            symbol="BTC/USDT:USDT",
            side=OrderSide.CLOSE_SHORT,
            order_type=OrderType.LIMIT,
            size=0.5,
            price=50000.0,
            reduce_only=True,
        )

        assert result["code"] == "00000"

        call_args = exchange.create_order.call_args
        assert call_args[1]["type"] == "limit"
        assert call_args[1]["side"] == "buy"  # Buy to close SHORT
        assert call_args[1]["price"] == 50000.0
        assert call_args[1]["params"]["positionSide"] == "SHORT"
        assert call_args[1]["params"]["reduceOnly"] is True

    @pytest.mark.asyncio
    async def test_create_order_with_stop_loss_take_profit(self, mock_ccxt_binance):
        """Test order creation with stop-loss and take-profit"""
        _, exchange = mock_ccxt_binance

        exchange.create_order.return_value = {
            "id": "main_order",
            "symbol": "BTC/USDT:USDT",
            "status": "closed",
        }

        adapter = BinanceAdapter("key", "secret")
        await adapter.create_order(
            symbol="BTC/USDT:USDT",
            side=OrderSide.OPEN_LONG,
            order_type=OrderType.MARKET,
            size=1.0,
            stop_loss=48000.0,
            take_profit=52000.0,
        )

        # Should call create_order 3 times: main + stop-loss + take-profit
        assert exchange.create_order.call_count == 3

    @pytest.mark.asyncio
    async def test_create_limit_order_without_price_fails(self, mock_ccxt_binance):
        """Test that limit order without price raises ValueError"""
        _, exchange = mock_ccxt_binance

        adapter = BinanceAdapter("key", "secret")

        result = await adapter.create_order(
            symbol="BTC/USDT:USDT",
            side=OrderSide.OPEN_LONG,
            order_type=OrderType.LIMIT,
            size=1.0,
            # Missing price parameter
        )

        assert result["code"] == "ERROR"
        assert "price" in result["msg"].lower()


class TestBinanceAdapterOrderSideMapping:
    """Test internal order side mapping logic"""

    def test_map_order_side(self, mock_ccxt_binance):
        """Test all order side mappings"""
        _, _ = mock_ccxt_binance
        adapter = BinanceAdapter("key", "secret")

        # OPEN_LONG: buy LONG position
        ccxt_side, pos_side = adapter._map_order_side(OrderSide.OPEN_LONG)
        assert ccxt_side == "buy" and pos_side == "LONG"

        # OPEN_SHORT: sell SHORT position
        ccxt_side, pos_side = adapter._map_order_side(OrderSide.OPEN_SHORT)
        assert ccxt_side == "sell" and pos_side == "SHORT"

        # CLOSE_LONG: sell LONG position
        ccxt_side, pos_side = adapter._map_order_side(OrderSide.CLOSE_LONG)
        assert ccxt_side == "sell" and pos_side == "LONG"

        # CLOSE_SHORT: buy SHORT position
        ccxt_side, pos_side = adapter._map_order_side(OrderSide.CLOSE_SHORT)
        assert ccxt_side == "buy" and pos_side == "SHORT"


class TestBinanceAdapterClose:
    """Test connection cleanup"""

    @pytest.mark.asyncio
    async def test_close(self, mock_ccxt_binance):
        """Test that close method calls exchange.close()"""
        _, exchange = mock_ccxt_binance

        adapter = BinanceAdapter("key", "secret")
        await adapter.close()

        exchange.close.assert_called_once()
