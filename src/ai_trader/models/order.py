"""订单与持仓模型"""

from pydantic import BaseModel
from typing import Literal, Optional


class Order(BaseModel):
    """订单"""

    symbol: str
    order_id: str
    side: Literal["open_long", "open_short", "close_long", "close_short"]
    price: Optional[float] = None
    size: float
    status: str
    order_type: Literal["market", "limit"]
    created_at: int


class Position(BaseModel):
    """持仓"""

    symbol: str
    side: Literal["long", "short"]
    size: float
    entry_price: float
    mark_price: float
    liquidation_price: float
    leverage: int
    margin: float
    unrealized_pnl: float
    roi: float
