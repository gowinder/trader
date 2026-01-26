"""持仓管理模块"""

from typing import Optional, List
from ..models.order import Position
from .base import BaseExchange
from ..utils.logger import logger


class PositionManager:
    """持仓管理器"""

    def __init__(self, client: BaseExchange):
        self.client = client

    async def get_position(self, symbol: str) -> Optional[Position]:
        """获取指定交易对的持仓

        Now returns Position model directly from WeexClient.get_positions()
        """
        positions = await self.client.get_positions(symbol)

        # get_positions() now returns List[Position] models
        # Return the first non-zero position or None
        for pos in positions:
            if pos.size > 0:
                return pos

        return None
