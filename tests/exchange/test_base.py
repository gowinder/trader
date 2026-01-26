"""Unit tests for exchange base classes and models"""

import pytest
from ai_trader.exchange.base import (
    BaseExchange,
    AccountInfo,
    Ticker,
    Position,
    OrderSide,
    OrderType,
)


class TestAccountInfo:
    """Test AccountInfo model"""

    def test_account_info_valid(self):
        """Test valid AccountInfo creation"""
        account = AccountInfo(
            total_equity=10000.0,
            available_balance=5000.0,
            margin_used=5000.0,
            unrealized_pnl=100.0,
        )
        assert account.total_equity == 10000.0
        assert account.available_balance == 5000.0
        assert account.margin_used == 5000.0
        assert account.unrealized_pnl == 100.0

    def test_account_info_missing_field(self):
        """Test AccountInfo with missing required field"""
        with pytest.raises(Exception):  # Pydantic will raise ValidationError
            AccountInfo(
                total_equity=10000.0,
                available_balance=5000.0,
                # missing margin_used
            )


class TestTicker:
    """Test Ticker model"""

    def test_ticker_valid(self):
        """Test valid Ticker creation"""
        ticker = Ticker(
            symbol="BTC/USDT",
            last_price=50000.0,
            bid_price=49999.0,
            ask_price=50001.0,
            high_24h=51000.0,
            low_24h=49000.0,
            volume_24h=1000000.0,
            change_24h=2.5,
        )
        assert ticker.symbol == "BTC/USDT"
        assert ticker.last_price == 50000.0
        assert ticker.bid_price == 49999.0
        assert ticker.ask_price == 50001.0
        assert ticker.high_24h == 51000.0
        assert ticker.low_24h == 49000.0
        assert ticker.volume_24h == 1000000.0
        assert ticker.change_24h == 2.5


class TestPosition:
    """Test Position model"""

    def test_position_valid(self):
        """Test valid Position creation"""
        position = Position(
            symbol="BTC/USDT",
            side="long",
            size=1.0,
            entry_price=50000.0,
            mark_price=51000.0,
            unrealized_pnl=1000.0,
            leverage=10,
            margin_mode="cross",
            liquidation_price=45000.0,
        )
        assert position.symbol == "BTC/USDT"
        assert position.side == "long"
        assert position.size == 1.0
        assert position.entry_price == 50000.0
        assert position.mark_price == 51000.0
        assert position.unrealized_pnl == 1000.0
        assert position.leverage == 10
        assert position.margin_mode == "cross"
        assert position.liquidation_price == 45000.0

    def test_position_optional_liquidation_price(self):
        """Test Position with optional liquidation_price"""
        position = Position(
            symbol="BTC/USDT",
            side="long",
            size=1.0,
            entry_price=50000.0,
            mark_price=51000.0,
            unrealized_pnl=1000.0,
            leverage=10,
            margin_mode="cross",
            # liquidation_price is optional
        )
        assert position.liquidation_price is None


class TestOrderEnums:
    """Test Order enumerations"""

    def test_order_side_enum(self):
        """Test OrderSide enum values"""
        assert OrderSide.OPEN_LONG == "open_long"
        assert OrderSide.OPEN_SHORT == "open_short"
        assert OrderSide.CLOSE_LONG == "close_long"
        assert OrderSide.CLOSE_SHORT == "close_short"

    def test_order_type_enum(self):
        """Test OrderType enum values"""
        assert OrderType.MARKET == "market"
        assert OrderType.LIMIT == "limit"


class TestBaseExchange:
    """Test BaseExchange abstract class"""

    def test_cannot_instantiate_base_exchange(self):
        """Test that BaseExchange cannot be instantiated directly"""
        with pytest.raises(TypeError):
            BaseExchange()
