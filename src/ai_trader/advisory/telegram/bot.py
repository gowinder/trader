"""Telegram Bot 生命周期管理"""

from ...utils.logger import logger
from .notifier import TelegramNotifier

try:
    from telegram import BotCommand
    from telegram.ext import Application
    HAS_TELEGRAM = True
except ImportError:
    HAS_TELEGRAM = False
    Application = None
    BotCommand = None


class TelegramBot:
    """Telegram Bot 主类，统一管理 polling 和推送"""

    def __init__(self, bot_token: str, chat_id: str, redis=None, db=None,
                 persistence=None, strategy_service=None, advisory_persistence=None):
        """初始化 Bot

        Args:
            bot_token: Telegram Bot Token
            chat_id: 授权的 Chat ID
            redis: Redis 异步客户端
            db: DatabaseManager 实例
            persistence: DecisionPersistenceService 实例 (用于 LLM 查询)
            strategy_service: StrategyPresetService 实例
            advisory_persistence: AdvisoryPersistenceService 实例
        """
        self.bot_token = bot_token
        self.chat_id = chat_id
        self._app = None
        self._notifier = None

        if not HAS_TELEGRAM or not bot_token:
            logger.warning("python-telegram-bot not installed or token not configured")
            return

        self._app = Application.builder().token(bot_token).build()

        # 将共享资源存入 bot_data，供 handlers 通过 context.bot_data 访问
        self._app.bot_data["chat_id"] = chat_id
        self._app.bot_data["redis"] = redis
        self._app.bot_data["db"] = db
        self._app.bot_data["persistence"] = persistence
        self._app.bot_data["strategy_service"] = strategy_service
        self._app.bot_data["advisory_persistence"] = advisory_persistence

        # 注册命令和回调 handlers
        from .commands import register_commands
        register_commands(self._app)

        # 创建 notifier，共享 bot 实例
        self._notifier = TelegramNotifier(bot_token=bot_token, chat_id=chat_id, bot=self._app.bot)

    @property
    def notifier(self) -> TelegramNotifier:
        """获取通知器实例（供外部推送使用）"""
        if self._notifier:
            return self._notifier
        # 降级：没有 Application 时创建独立 notifier
        return TelegramNotifier(bot_token=self.bot_token, chat_id=self.chat_id)

    @property
    def enabled(self) -> bool:
        return bool(self._app and self.chat_id)

    async def start(self):
        """启动 Bot（初始化 + polling + 设置命令菜单）"""
        if not self._app:
            logger.debug("Telegram Bot not configured, skipping start")
            return

        try:
            await self._app.initialize()
            await self._app.start()
            await self._app.updater.start_polling(drop_pending_updates=True)

            # 设置 Bot 命令菜单
            commands = [
                BotCommand("overview", "📊 账户概览"),
                BotCommand("positions", "📈 当前持仓"),
                BotCommand("decisions", "🧠 最近决策"),
                BotCommand("llm", "🤖 LLM 调用统计"),
                BotCommand("strategy", "📋 策略管理"),
                BotCommand("advisory", "💡 Advisory 建议"),
                BotCommand("trading", "⚙️ 交易控制"),
                BotCommand("menu", "显示主菜单"),
                BotCommand("help", "帮助"),
            ]
            await self._app.bot.set_my_commands(commands)

            logger.info("Telegram Bot started (polling + commands)")
        except Exception as e:
            logger.error(f"Failed to start Telegram Bot: {e}")

    async def stop(self):
        """停止 Bot"""
        if not self._app:
            return
        try:
            if self._app.updater and self._app.updater.running:
                await self._app.updater.stop()
            if self._app.running:
                await self._app.stop()
            await self._app.shutdown()
            logger.info("Telegram Bot stopped")
        except Exception as e:
            logger.error(f"Failed to stop Telegram Bot: {e}")
        finally:
            self._app = None
