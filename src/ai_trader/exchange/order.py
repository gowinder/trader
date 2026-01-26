"""订单管理模块"""

from typing import Optional
from ..models.decision import TradingDecision
from .base import BaseExchange, OrderSide, OrderType
from ..utils.logger import logger


class OrderManager:
    """订单管理器"""

    def __init__(self, client: BaseExchange):
        self.client = client

    def _map_side(self, action: str) -> Optional[OrderSide]:
        """映射交易动作到 OrderSide 枚举"""
        mapping = {
            "open_long": OrderSide.OPEN_LONG,
            "open_short": OrderSide.OPEN_SHORT,
            "close_long": OrderSide.CLOSE_LONG,
            "close_short": OrderSide.CLOSE_SHORT,
            "add_long": OrderSide.OPEN_LONG,  # Same as open
            "add_short": OrderSide.OPEN_SHORT,
            "reduce_long": OrderSide.CLOSE_LONG,  # Same as close
            "reduce_short": OrderSide.CLOSE_SHORT,
        }
        return mapping.get(action)

    async def execute_order(
        self, decision: TradingDecision, symbol: str, quantity: float
    ) -> Optional[str]:
        """执行交易决策"""
        if decision.action == "hold":
            return None

        logger.info(f"Executing order: {decision.action} {symbol} x {quantity}")

        # 1. 设置杠杆
        if not await self.client.set_leverage(symbol, decision.leverage):
            logger.error("Failed to set leverage, aborting order")
            return None

        # 2. 映射方向
        side = self._map_side(decision.action)
        if side is None:
            logger.warning(f"Unknown action {decision.action}")
            return None

        # 3. 映射订单类型字符串到 OrderType 枚举
        order_type_map = {
            "market": OrderType.MARKET,
            "limit": OrderType.LIMIT,
        }
        order_type = order_type_map.get(decision.order_type, OrderType.MARKET)

        # 4. 下单
        try:
            result = await self.client.create_order(
                symbol=symbol,
                side=side,
                order_type=order_type,
                size=quantity,
                price=decision.entry_price if order_type == OrderType.LIMIT else None,
                stop_loss=decision.stop_loss_price,
                take_profit=decision.take_profit_price,
            )

            # create_order now returns dict from WEEX API
            if result.get("code") == "00000":
                order_id = result["data"]["orderId"]
                logger.info(f"Order placed successfully: {order_id}")
                return order_id
            else:
                logger.error(f"Order placement failed: {result}")
                return None
        except Exception as e:
            logger.error(f"Error executing order: {e}")
            return None
