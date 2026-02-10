"""Advisory 服务 - 协调触发器、引擎和通知"""

from typing import Optional, List, Dict, Any

from .engine import AdvisoryEngine
from .triggers import TriggerManager
from .telegram import TelegramNotifier
from .persistence import AdvisoryPersistenceService
from ..models.advisory import TriggerType
from ..utils.logger import logger


class AdvisoryService:
    def __init__(
        self,
        engine: AdvisoryEngine,
        trigger_manager: TriggerManager,
        notifier: Optional[TelegramNotifier] = None,
        persistence: Optional[AdvisoryPersistenceService] = None,
    ):
        self.engine = engine
        self.trigger_mgr = trigger_manager
        self.notifier = notifier
        self.persistence = persistence

    async def check_and_run(
        self,
        symbols: List[str],
        positions: List[Dict],
        market_data: Dict[str, Dict],
        sentiment: Optional[Dict],
        current_config: Dict[str, Any],
        consecutive_losses: int = 0,
        price_context: Optional[Dict[str, Dict]] = None,
        account_summary: Optional[Dict] = None,
    ):
        triggered = []

        # 1. Scheduled
        if self.trigger_mgr.should_run_scheduled():
            triggered.append((TriggerType.SCHEDULED, {}))
            self.trigger_mgr.mark_scheduled_run()

        # 2. Price volatility
        if self.trigger_mgr.config.price_volatility_enabled and price_context:
            for symbol, ctx in price_context.items():
                result = self.trigger_mgr.price_volatility.check(
                    current_price=ctx.get("current", 0),
                    previous_price=ctx.get("previous", 0),
                )
                if result:
                    triggered.append((TriggerType.PRICE_VOLATILITY, {**result, "symbol": symbol}))

        # 3. Consecutive loss
        if self.trigger_mgr.config.consecutive_loss_enabled:
            result = self.trigger_mgr.consecutive_loss.check(consecutive_losses)
            if result:
                triggered.append((TriggerType.CONSECUTIVE_LOSS, result))

        # 4. Unrealized PnL
        if self.trigger_mgr.config.unrealized_pnl_enabled:
            for p in positions:
                pnl_pct = p.get("roi", 0) or 0
                result = self.trigger_mgr.unrealized_pnl.check(float(pnl_pct))
                if result:
                    triggered.append((TriggerType.UNREALIZED_PNL, {**result, "symbol": p.get("symbol", "")}))

        # 5. Sentiment shift
        if self.trigger_mgr.config.sentiment_shift_enabled and sentiment:
            result = self.trigger_mgr.sentiment_shift.check(
                extreme_fear=sentiment.get("extreme_fear", False),
                extreme_greed=sentiment.get("extreme_greed", False),
            )
            if result:
                triggered.append((TriggerType.SENTIMENT_SHIFT, result))

        if not triggered:
            return

        trigger_type = triggered[0][0]
        trigger_detail = triggered[0][1]
        if len(triggered) > 1:
            trigger_detail["additional_triggers"] = [
                {"type": t.value, "detail": d} for t, d in triggered[1:]
            ]

        advisory_id = await self.engine.generate_advisory(
            trigger_type=trigger_type, trigger_detail=trigger_detail,
            symbols=symbols, positions=positions,
            market_data=market_data, sentiment=sentiment,
            current_config=current_config, account_summary=account_summary,
        )

        if advisory_id is None:
            return

        # Send notification
        if self.notifier and self.notifier.enabled and self.engine.last_result:
            try:
                await self.notifier.send_advisory(self.engine.last_result, str(advisory_id))
            except Exception as e:
                logger.error(f"Failed to send notification: {e}")

        logger.info(f"Advisory check complete: {len(triggered)} trigger(s), advisory_id={advisory_id}")
