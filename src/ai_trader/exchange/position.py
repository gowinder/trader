"""持仓管理模块"""

from typing import Optional, List
from ..models.order import Position
from .weex_client import WeexClient
from ..utils.logger import logger


class PositionManager:
    """持仓管理器"""

    def __init__(self, client: WeexClient):
        self.client = client

    async def get_position(self, symbol: str) -> Optional[Position]:
        """获取指定交易对的持仓"""
        positions_data = await self.client.get_positions(symbol)

        # Weex V2 returns list of positions (long/short separate)
        # We assume we care about the aggregate or specific logic.
        # Simplification: return the first non-zero position or None

        for pos in positions_data:
            size = float(pos.get("holdAmount", 0))
            if size > 0:
                # Map raw data to Position model
                # Weex "side": 1=long, 2=short
                side_map = {"1": "long", "2": "short"}

                return Position(
                    symbol=pos.get("symbol", symbol),
                    side=side_map.get(
                        str(pos.get("side")), "long"
                    ),  # Default to long if unknown?
                    size=size,
                    entry_price=float(pos.get("averageOpenPrice", 0)),
                    mark_price=float(
                        pos.get("marketPrice", 0)
                    ),  # Assuming API returns mark price
                    liquidation_price=float(pos.get("liquidationPrice", 0)),
                    leverage=int(pos.get("leverage", 1)),
                    margin=float(pos.get("margin", 0)),
                    unrealized_pnl=float(pos.get("unrealizedPL", 0)),
                    roi=float(pos.get("rate", 0)),  # return rate
                )
        return None
