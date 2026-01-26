"""Unit tests for CCXT adapter"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from ai_trader.exchange.ccxt_adapter import CCXTAdapter
from ai_trader.exchange.base import AccountInfo, Ticker, Position, OrderSide, OrderType
from ai_trader.models.market import Kline


class TestCCXTAdapter:
    """Test CCXTAdapter data format conversion"""

    @pytest.fixture
    def mock_exchange(self):
        """Create a mock CCXT exchange"""
        exchange = Mock()
        exchange.id = "binance"
        exchange.fetch_balance = AsyncMock()
        exchange.fetch_ohlcv = AsyncMock()
        exchange.fetch_ticker = AsyncMock()
        exchange.fetch_positions = AsyncMock()
        exchange.set_leverage = AsyncMock()
        exchange.create_order = AsyncMock()
        exchange.cancel_order = AsyncMock()
        exchange.close = AsyncMock()
        return exchange

    @pytest.fixture
    def adapter(self, mock_exchange):
        """Create CCXTAdapter instance with mock exchange"""
        return CCXTAdapter(mock_exchange)

    @pytest.mark.asyncio
    async def test_get_account_conversion(self, adapter, mock_exchange):
        """Test AccountInfo data format conversion"""
        # Mock CCXT balance response
        mock_exchange.fetch_balance.return_value = {
            "USDT": {
                "total": 10000.0,
                "free": 5000.0,
                "used": 5000.0,
            }
        }

        account = await adapter.get_account()

        assert isinstance(account, AccountInfo)
        assert account.total_equity == 10000.0
        assert account.available_balance == 5000.0
        assert account.margin_used == 5000.0
        assert account.unrealized_pnl == 0.0

    @pytest.mark.asyncio
    async def test_get_klines_conversion(self, adapter, mock_exchange):
        """Test Kline data format conversion"""
        # Mock CCXT OHLCV response: [[timestamp, open, high, low, close, volume], ...]
        mock_exchange.fetch_ohlcv.return_value = [
            [1609459200000, 29000.0, 29500.0, 28500.0, 29200.0, 1000.0],
            [1609459260000, 29200.0, 29600.0, 29000.0, 29400.0, 1200.0],
        ]

        klines = await adapter.get_klines("BTC/USDT", "15m", 100)

        assert isinstance(klines, list)
        assert len(klines) == 2
        assert isinstance(klines[0], Kline)
        assert klines[0].timestamp == 1609459200000
        assert klines[0].open == 29000.0
        assert klines[0].high == 29500.0
        assert klines[0].low == 28500.0
        assert klines[0].close == 29200.0
        assert klines[0].volume == 1000.0

    @pytest.mark.asyncio
    async def test_get_ticker_conversion(self, adapter, mock_exchange):
        """Test Ticker data format conversion"""
        # Mock CCXT ticker response
        mock_exchange.fetch_ticker.return_value = {
            "symbol": "BTC/USDT",
            "last": 50000.0,
            "bid": 49999.0,
            "ask": 50001.0,
            "high": 51000.0,
            "low": 49000.0,
            "baseVolume": 1000000.0,
            "percentage": 2.5,
        }

        ticker = await adapter.get_ticker("BTC/USDT")

        assert isinstance(ticker, Ticker)
        assert ticker.symbol == "BTC/USDT"
        assert ticker.last_price == 50000.0
        assert ticker.bid_price == 49999.0
        assert ticker.ask_price == 50001.0
        assert ticker.high_24h == 51000.0
        assert ticker.low_24h == 49000.0
        assert ticker.volume_24h == 1000000.0
        assert ticker.change_24h == 2.5

    @pytest.mark.asyncio
    async def test_get_positions_conversion(self, adapter, mock_exchange):
        """Test Position data format conversion"""
        # Mock CCXT positions response
        mock_exchange.fetch_positions.return_value = [
            {
                "symbol": "BTC/USDT",
                "side": "long",
                "contracts": 1.0,
                "entryPrice": 50000.0,
                "markPrice": 51000.0,
                "unrealizedPnl": 1000.0,
                "leverage": 10,
                "marginMode": "cross",
                "liquidationPrice": 45000.0,
            },
            {
                "symbol": "ETH/USDT",
                "side": "short",
                "contracts": 0.0,  # Empty position, should be filtered
            },
        ]

        positions = await adapter.get_positions("BTC/USDT")

        assert isinstance(positions, list)
        assert len(positions) == 1  # Empty position filtered
        assert isinstance(positions[0], Position)
        assert positions[0].symbol == "BTC/USDT"
        assert positions[0].side == "long"
        assert positions[0].size == 1.0
        assert positions[0].entry_price == 50000.0
        assert positions[0].mark_price == 51000.0
        assert positions[0].unrealized_pnl == 1000.0
        assert positions[0].leverage == 10
        assert positions[0].margin_mode == "cross"
        assert positions[0].liquidation_price == 45000.0

    @pytest.mark.asyncio
    async def test_create_order_side_mapping(self, adapter, mock_exchange):
        """Test order side mapping (OPEN_LONG -> buy, OPEN_SHORT -> sell)"""
        mock_exchange.create_order.return_value = {
            "id": "12345",
            "status": "open",
            "filled": 0.0,
            "average": None,
        }

        # Test OPEN_LONG
        await adapter.create_order(
            symbol="BTC/USDT",
            side=OrderSide.OPEN_LONG,
            order_type=OrderType.MARKET,
            size=1.0,
        )
        mock_exchange.create_order.assert_called_once()
        call_kwargs = mock_exchange.create_order.call_args[1]
        assert call_kwargs["side"] == "buy"

        # Test OPEN_SHORT
        mock_exchange.create_order.reset_mock()
        await adapter.create_order(
            symbol="BTC/USDT",
            side=OrderSide.OPEN_SHORT,
            order_type=OrderType.MARKET,
            size=1.0,
        )
        call_kwargs = mock_exchange.create_order.call_args[1]
        assert call_kwargs["side"] == "sell"

    @pytest.mark.asyncio
    async def test_interval_mapping(self, adapter, mock_exchange):
        """Test interval mapping (15m -> 15m, 1h -> 1h)"""
        mock_exchange.fetch_ohlcv.return_value = []

        await adapter.get_klines("BTC/USDT", "15m", 100)
        mock_exchange.fetch_ohlcv.assert_called_once()
        call_args = mock_exchange.fetch_ohlcv.call_args
        assert call_args[1]["timeframe"] == "15m"

    def test_from_config_testnet_strict_mode(self):
        """Test testnet mode requires sandbox support"""
        # Mock exchange without set_sandbox_mode
        with patch("ai_trader.exchange.ccxt_adapter.ccxt") as mock_ccxt:
            mock_exchange_class = Mock()
            mock_exchange_instance = Mock(spec=[])  # Empty spec prevents attribute access
            mock_exchange_instance.id = "test_exchange"
            # Explicitly do not add set_sandbox_mode attribute
            mock_exchange_class.return_value = mock_exchange_instance
            mock_ccxt.test_exchange = mock_exchange_class

            with pytest.raises(ValueError, match="does not support set_sandbox_mode"):
                CCXTAdapter.from_config(
                    exchange_id="test_exchange",
                    api_key="test_key",
                    api_secret="test_secret",
                    testnet=True,
                )

    def test_from_config_unsupported_exchange(self):
        """Test from_config with unsupported exchange"""
        with patch("ai_trader.exchange.ccxt_adapter.ccxt") as mock_ccxt:
            # Simulate exchange not available in ccxt
            delattr(mock_ccxt, "nonexistent_exchange") if hasattr(
                mock_ccxt, "nonexistent_exchange"
            ) else None

            with pytest.raises(ValueError, match="does not support exchange"):
                CCXTAdapter.from_config(
                    exchange_id="nonexistent_exchange",
                    api_key="test_key",
                    api_secret="test_secret",
                )
