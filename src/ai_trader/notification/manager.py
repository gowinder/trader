"""通知管理器"""

import json
from typing import Optional

from ..advisory.telegram import TelegramNotifier
from ..utils.logger import logger
from .formatter import (
    format_trade_message,
    format_stop_loss_take_profit_message,
    format_decision_message,
    format_backtest_message,
)

DEFAULT_CONFIG = {
    "telegram_enabled": True,
    "trade": {
        "enabled": True,
        "open_long": True,
        "open_short": True,
        "close_long": True,
        "close_short": True,
        "add_reduce": True,
        "stop_loss_take_profit": True,
    },
    "decision": {
        "enabled": True,
        "action": True,
        "hold": False,
    },
    "backtest": {
        "enabled": True,
        "completed": True,
    },
    "advisory": {
        "enabled": True,
        "suggestion": True,
    },
}

ACTION_EVENT_MAP = {
    "open_long": ("trade", "open_long"),
    "open_short": ("trade", "open_short"),
    "close_long": ("trade", "close_long"),
    "close_short": ("trade", "close_short"),
    "add_long": ("trade", "add_reduce"),
    "add_short": ("trade", "add_reduce"),
    "reduce_long": ("trade", "add_reduce"),
    "reduce_short": ("trade", "add_reduce"),
}

REDIS_CONFIG_KEY = "notification:config"


class NotificationManager:
    def __init__(self, notifier: TelegramNotifier, redis_client=None):
        self.notifier = notifier
        self.redis = redis_client
        self.config = json.loads(json.dumps(DEFAULT_CONFIG))

    async def load_config(self):
        """从 Redis 加载通知配置"""
        if not self.redis:
            return
        try:
            raw = await self.redis.get(REDIS_CONFIG_KEY)
            if raw:
                saved = json.loads(raw)
                self._merge_config(saved)
                logger.info("Notification config loaded from Redis")
        except Exception as e:
            logger.error(f"Failed to load notification config: {e}")

    def _merge_config(self, saved: dict):
        """将保存的配置合并到当前配置，保留默认值中未覆盖的字段"""
        for key, value in saved.items():
            if key in self.config:
                if isinstance(value, dict) and isinstance(self.config[key], dict):
                    self.config[key].update(value)
                else:
                    self.config[key] = value

    def update_config(self, config: dict):
        """热更新通知配置（仅更新内存，不写回 Redis）"""
        self._merge_config(config)

    def is_enabled(self, category: str, event: str) -> bool:
        """检查指定类别和事件的通知是否启用"""
        if not self.config.get("telegram_enabled", True):
            return False
        cat_config = self.config.get(category, {})
        if not isinstance(cat_config, dict):
            return False
        if not cat_config.get("enabled", True):
            return False
        return cat_config.get(event, False)

    async def notify_trade(
        self,
        symbol: str,
        action: str,
        price: float,
        size: float,
        leverage: int = 1,
        position_size_percent: float = 0.0,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ):
        """发送交易通知"""
        mapping = ACTION_EVENT_MAP.get(action)
        if not mapping:
            logger.warning(f"Unknown trade action: {action}")
            return
        category, event = mapping
        if not self.is_enabled(category, event):
            return
        text = format_trade_message(
            symbol=symbol,
            action=action,
            price=price,
            size=size,
            leverage=leverage,
            position_size_percent=position_size_percent,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        await self._send(text)

    async def notify_stop_loss_take_profit(
        self,
        symbol: str,
        side: str,
        trigger_type: str,
        entry_price: float,
        trigger_price: float,
        pnl_percent: float,
    ):
        """发送止损/止盈通知"""
        if not self.is_enabled("trade", "stop_loss_take_profit"):
            return
        text = format_stop_loss_take_profit_message(
            symbol=symbol,
            side=side,
            trigger_type=trigger_type,
            entry_price=entry_price,
            trigger_price=trigger_price,
            pnl_percent=pnl_percent,
        )
        await self._send(text)

    async def notify_decision(
        self,
        symbol: str,
        action: str,
        confidence: float = 0.0,
        reasoning: str = "",
        risk_note: str = "",
    ):
        """发送决策通知"""
        event = "hold" if action == "hold" else "action"
        if not self.is_enabled("decision", event):
            return
        text = format_decision_message(
            symbol=symbol,
            action=action,
            confidence=confidence,
            reasoning=reasoning,
            risk_note=risk_note,
        )
        await self._send(text)

    async def notify_backtest(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        return_pct: float,
        win_rate: float,
        max_drawdown_pct: float,
        sharpe_ratio: float,
        total_trades: int,
    ):
        """发送回测完成通知"""
        if not self.is_enabled("backtest", "completed"):
            return
        text = format_backtest_message(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            return_pct=return_pct,
            win_rate=win_rate,
            max_drawdown_pct=max_drawdown_pct,
            sharpe_ratio=sharpe_ratio,
            total_trades=total_trades,
        )
        await self._send(text)

    def is_advisory_enabled(self) -> bool:
        """检查 advisory 通知是否启用"""
        return self.is_enabled("advisory", "suggestion")

    async def send_test_message(self):
        """发送测试通知"""
        await self._send("🔔 通知测试 | Notification module is working!")

    async def _send(self, text: str):
        """内部发送方法"""
        if not self.notifier:
            logger.debug("Notifier not available, skipping notification")
            return
        await self.notifier.send_text(text, parse_mode=None)
