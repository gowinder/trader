"""订单与持仓模型单元测试"""

import pytest
from pydantic import ValidationError

from ai_trader.models.order import Order, Position


class TestOrder:
    def test_order_create(self):
        o = Order(
            symbol="BTC/USDT",
            order_id="123",
            side="open_long",
            size=0.01,
            status="filled",
            order_type="market",
            created_at=1700000000,
        )
        assert o.symbol == "BTC/USDT"
        assert o.side == "open_long"
        assert o.price is None
        assert o.order_type == "market"

    def test_order_with_price(self):
        o = Order(
            symbol="ETH/USDT",
            order_id="456",
            side="close_short",
            price=3000.0,
            size=1.0,
            status="open",
            order_type="limit",
            created_at=1700000000,
        )
        assert o.price == 3000.0
        assert o.order_type == "limit"

    def test_order_all_valid_sides(self):
        for side in ["open_long", "open_short", "close_long", "close_short"]:
            o = Order(
                symbol="BTC/USDT", order_id="x", side=side,
                size=1.0, status="new", order_type="market", created_at=0,
            )
            assert o.side == side

    def test_order_invalid_side(self):
        with pytest.raises(ValidationError):
            Order(
                symbol="BTC/USDT", order_id="x", side="buy",
                size=1.0, status="new", order_type="market", created_at=0,
            )

    def test_order_invalid_order_type(self):
        with pytest.raises(ValidationError):
            Order(
                symbol="BTC/USDT", order_id="x", side="open_long",
                size=1.0, status="new", order_type="stop_limit", created_at=0,
            )


class TestPosition:
    def test_position_create_long(self):
        p = Position(
            symbol="BTC/USDT", side="long", size=0.1, entry_price=50000.0,
            mark_price=51000.0, liquidation_price=40000.0, leverage=10,
            margin=500.0, unrealized_pnl=100.0, roi=0.2,
        )
        assert p.side == "long"
        assert p.leverage == 10
        assert p.unrealized_pnl == 100.0

    def test_position_create_short(self):
        p = Position(
            symbol="ETH/USDT", side="short", size=1.0, entry_price=3000.0,
            mark_price=2900.0, liquidation_price=4000.0, leverage=5,
            margin=600.0, unrealized_pnl=100.0, roi=0.167,
        )
        assert p.side == "short"

    def test_position_invalid_side(self):
        with pytest.raises(ValidationError):
            Position(
                symbol="BTC/USDT", side="both", size=0.1, entry_price=50000.0,
                mark_price=51000.0, liquidation_price=40000.0, leverage=10,
                margin=500.0, unrealized_pnl=0.0, roi=0.0,
            )
