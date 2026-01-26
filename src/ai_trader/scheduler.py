"""调度器模块"""

import asyncio
from typing import Optional
from .config import config
from .utils.logger import logger
from .exchange import create_exchange_client
from .exchange.order import OrderManager
from .exchange.position import PositionManager
from .data.market_data import MarketDataManager
from .ai.client import LLMClient
from .ai.decision import DecisionEngine
from .reporter import Reporter


class Scheduler:
    """任务调度器"""

    def __init__(self):
        # Use factory function to create exchange client based on config
        self.exchange = create_exchange_client()
        self.llm = LLMClient()

        self.market_mgr = MarketDataManager(self.exchange)
        self.order_mgr = OrderManager(self.exchange)
        self.position_mgr = PositionManager(self.exchange)
        self.decision_engine = DecisionEngine(self.llm)
        self.reporter = Reporter()

        self.running = False

    async def start(self):
        """启动调度器"""
        self.running = True
        logger.info(f"Scheduler started for {config.trading_symbol}")

        while self.running:
            try:
                await self.run_cycle()
            except Exception as e:
                logger.error(f"Error in cycle: {e}")

            logger.info(f"Waiting {config.decision_interval}s...")
            await asyncio.sleep(config.decision_interval)

    async def stop(self):
        """停止调度器"""
        self.running = False
        if hasattr(self, "exchange") and self.exchange:
            await self.exchange.close()
        if hasattr(self, "llm") and self.llm:
            await self.llm.close()
        logger.info("Scheduler stopped")

    async def run_cycle(self):
        """执行单次交易循环"""
        symbol = config.trading_symbol
        logger.info(f"Starting cycle for {symbol}")

        # 1. 获取数据
        market_data = await self.market_mgr.get_market_data(
            symbol, interval=f"{config.analysis_interval}m"
        )
        if not market_data:
            return

        position = await self.position_mgr.get_position(symbol)
        account = await self.exchange.get_account()  # Now returns AccountInfo model

        # Extract account balance from AccountInfo
        balance = account.available_balance
        equity = account.total_equity

        # Debug: Log account data
        logger.debug(
            f"Account data: equity={equity}, balance={balance}, "
            f"margin_used={account.margin_used}, unrealized_pnl={account.unrealized_pnl}"
        )

        if balance <= 0 or equity <= 0:
            logger.warning(
                f"Insufficient balance or failed to parse account: balance={balance}, equity={equity}"
            )
            return

        # 2. 决策
        try:
            decision, tech, risk = await self.decision_engine.analyze_and_decide(
                market_data, position, balance, equity
            )
        except Exception as e:
            logger.error(f"Decision engine failed: {e}")
            return

        # 3. 执行
        order_id = None
        quantity = 0.0
        if decision.action != "hold":
            # Determine quantity based on action type
            if decision.action in ["close_long", "close_short"]:
                # Full close: use entire position size
                if position and position.size > 0:
                    quantity = position.size
                else:
                    logger.warning(
                        f"Decision is {decision.action} but no position found."
                    )
            elif decision.action in ["reduce_long", "reduce_short"]:
                # Partial close: reduce by 50% (default strategy for now)
                if position and position.size > 0:
                    quantity = position.size * 0.5
                else:
                    logger.warning(
                        f"Decision is {decision.action} but no position found."
                    )
            else:
                # Open/Add: calculate based on balance percent
                # amount_usdt = balance * (decision.position_size_percent / 100) * decision.leverage
                # Simplification:
                amount_usdt = (
                    balance * (decision.position_size_percent / 100) * decision.leverage
                )
                if amount_usdt > 0:
                    quantity = amount_usdt / market_data.current_price

            # Final check and execution
            if quantity > 0:
                # WeEx requires stepSize of 0.1 for cmt_bnbusdt
                # Round to 1 decimal place to match exchange requirement
                quantity = round(quantity, 1)

                order_id = await self.order_mgr.execute_order(
                    decision, symbol, quantity
                )

        # 4. 报告
        # Get position after trade (wait a bit? or just report 'submitted')
        # We pass None for position_after for now as it takes time to fill
        self.reporter.generate(market_data, tech, decision, position, None, 0.0)
