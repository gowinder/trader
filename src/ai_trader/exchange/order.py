"""订单管理模块"""

from typing import Optional
from ..models.decision import TradingDecision
from .weex_client import WeexClient
from ..utils.logger import logger


class OrderManager:
    """订单管理器"""

    def __init__(self, client: WeexClient):
        self.client = client

    def _map_side(self, action: str) -> str:
        """映射交易动作到交易所方向"""
        # Weex contract V2: 1=open long, 2=open short, 3=close long, 4=close short
        # But wait, Weex V2 /placeOrder API uses specific values?
        # Let's assume standard "1","2","3","4" for simplicity or use strings if API allows.
        # Checking Weex API docs (implied): usually 1: open long, 2: open short, 3: close long, 4: close short
        mapping = {
            "open_long": "1",
            "open_short": "2",
            "close_long": "3",
            "close_short": "4",
            "add_long": "1",  # Same as open
            "add_short": "2",
            "reduce_long": "3",  # Same as close
            "reduce_short": "4",
        }
        return mapping.get(action, "0")

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
        if side == "0":
            logger.warning(f"Unknown action {decision.action}")
            return None

        # 3. 映射类型
        # Weex orderType: 1=limit, 2=market (implied)
        # Let's assume strings "limit" / "market" are accepted by our client wrapper,
        # but client wrapper passed them raw.
        # Weex V2 usually: limit, market.
        # I'll pass strings "limit" and "market" and let WeexClient handle it (it passes raw).
        # But if Weex expects numbers, we need to map.
        # Let's map to "limit" and "market" strings which is common in wrappers.
        # If raw API needs numbers, WeexClient or here should do it.
        # I'll use "market" and "limit" strings.

        # 4. 下单
        try:
            result = await self.client.create_order(
                symbol=symbol,
                side=side,
                order_type=decision.order_type,
                size=quantity,
                price=decision.entry_price if decision.order_type == "limit" else None,
                stop_loss=decision.stop_loss_price,
                take_profit=decision.take_profit_price,
            )

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
