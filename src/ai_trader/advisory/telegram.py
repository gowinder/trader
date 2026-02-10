"""Telegram 通知模块"""

from typing import Optional, List
from ..models.advisory import AdvisoryResult, Suggestion, Urgency
from ..utils.logger import logger

try:
    from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
    HAS_TELEGRAM = True
except ImportError:
    HAS_TELEGRAM = False
    Bot = None
    InlineKeyboardButton = None
    InlineKeyboardMarkup = None


URGENCY_EMOJI = {
    Urgency.HIGH: "\U0001f534",
    Urgency.MEDIUM: "\U0001f7e1",
    Urgency.LOW: "\U0001f7e2",
}


def format_advisory_message(result: AdvisoryResult, advisory_id: str) -> str:
    emoji = URGENCY_EMOJI.get(result.urgency, "\u26aa")
    lines = [
        f"\U0001f514 AI \u4ea4\u6613\u5efa\u8bae [{emoji} {result.urgency.value.upper()}]",
        "",
        f"\U0001f4ca \u5e02\u573a\u6982\u51b5: {result.market_summary}",
    ]
    if result.suggestions:
        lines.append("")
        for i, s in enumerate(result.suggestions, 1):
            lines.append(f"\u5efa\u8bae {i}/{len(result.suggestions)}: {s.action}")
            lines.append(f"  \u76ee\u6807: {s.target}")
            lines.append(f"  \u7406\u7531: {s.reasoning}")
            lines.append(f"  \u98ce\u9669: {s.risk_note}")
            lines.append("")
    else:
        lines.append("")
        lines.append("\u2705 \u5f53\u524d\u65e0\u9700\u8c03\u6574")
    lines.append(f"\U0001f4cb ID: {advisory_id}")
    return "\n".join(lines)


def build_suggestion_keyboard(advisory_id: str, suggestions: List[Suggestion]):
    if not HAS_TELEGRAM or not suggestions:
        return None
    buttons = []
    for i, s in enumerate(suggestions):
        buttons.append([
            InlineKeyboardButton(f"\u2705 \u91c7\u7eb3 #{i+1}", callback_data=f"accept:{advisory_id}:{i}"),
            InlineKeyboardButton(f"\u274c \u62d2\u7edd #{i+1}", callback_data=f"reject:{advisory_id}:{i}"),
        ])
    return InlineKeyboardMarkup(buttons)


class TelegramNotifier:
    def __init__(self, bot_token: str = "", chat_id: str = ""):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self._bot = None
        self._app = None  # Telegram Application (for callback handler)
        if HAS_TELEGRAM and bot_token:
            self._bot = Bot(token=bot_token)

    @property
    def enabled(self) -> bool:
        return bool(self._bot and self.chat_id)

    async def send_advisory(self, result: AdvisoryResult, advisory_id: str) -> Optional[int]:
        if not self.enabled:
            logger.debug("Telegram not configured, skipping notification")
            return None
        try:
            text = format_advisory_message(result, advisory_id)
            keyboard = build_suggestion_keyboard(advisory_id, result.suggestions)
            msg = await self._bot.send_message(
                chat_id=self.chat_id, text=text,
                reply_markup=keyboard, parse_mode=None,
            )
            logger.info(f"Telegram advisory sent: msg_id={msg.message_id}")
            return msg.message_id
        except Exception as e:
            logger.error(f"Failed to send Telegram notification: {e}")
            return None

    async def send_execution_result(self, suggestion_index: int, action: str, success: bool, message: str):
        if not self.enabled:
            return
        try:
            emoji = "\u2705" if success else "\u274c"
            text = f"{emoji} \u5efa\u8bae #{suggestion_index + 1} ({action}) \u6267\u884c\u7ed3\u679c: {message}"
            await self._bot.send_message(chat_id=self.chat_id, text=text)
        except Exception as e:
            logger.error(f"Failed to send execution result: {e}")

    async def start_callback_handler(self, redis_client, persistence):
        """启动 Telegram callback 处理"""
        if not HAS_TELEGRAM or not self.enabled:
            logger.debug("Telegram callback handler not started (not configured)")
            return

        try:
            from telegram.ext import Application, CallbackQueryHandler

            app = Application.builder().token(self.bot_token).build()

            async def handle_callback(update, context):
                query = update.callback_query
                await query.answer()

                data = query.data
                parts = data.split(":")
                if len(parts) != 3:
                    return

                action_type, advisory_id, idx = parts[0], parts[1], int(parts[2])

                if str(query.message.chat_id) != self.chat_id:
                    return

                import json

                def _rebuild_keyboard(original_markup, advisory_id, idx, replacement_row):
                    """替换指定 idx 的按钮行，保留其余行"""
                    new_rows = []
                    if original_markup and original_markup.inline_keyboard:
                        for row in original_markup.inline_keyboard:
                            # 检查该行是否属于当前 idx
                            row_matches = any(
                                btn.callback_data and btn.callback_data.endswith(f":{advisory_id}:{idx}")
                                for btn in row
                            )
                            if row_matches:
                                if replacement_row is not None:
                                    new_rows.append(replacement_row)
                            else:
                                new_rows.append(row)
                    return InlineKeyboardMarkup(new_rows) if new_rows else None

                if action_type == "accept":
                    await redis_client.lpush(
                        "advisory:telegram_actions",
                        json.dumps({"advisory_id": advisory_id, "index": idx, "action": "accept"})
                    )
                    confirm_row = [
                        InlineKeyboardButton(f"\u26a0\ufe0f \u786e\u8ba4#{idx+1}?", callback_data=f"confirm:{advisory_id}:{idx}"),
                        InlineKeyboardButton(f"\u21a9\ufe0f \u53d6\u6d88#{idx+1}", callback_data=f"cancel:{advisory_id}:{idx}"),
                    ]
                    new_markup = _rebuild_keyboard(query.message.reply_markup, advisory_id, idx, confirm_row)
                    await query.edit_message_reply_markup(reply_markup=new_markup)
                elif action_type == "reject":
                    await redis_client.lpush(
                        "advisory:telegram_actions",
                        json.dumps({"advisory_id": advisory_id, "index": idx, "action": "reject"})
                    )
                    # 移除该建议的按钮行，保留其余
                    new_markup = _rebuild_keyboard(query.message.reply_markup, advisory_id, idx, None)
                    await query.edit_message_reply_markup(reply_markup=new_markup)
                elif action_type == "confirm":
                    await redis_client.lpush(
                        "advisory:telegram_actions",
                        json.dumps({"advisory_id": advisory_id, "index": idx, "action": "confirm"})
                    )
                    # 移除该建议的按钮行，保留其余
                    new_markup = _rebuild_keyboard(query.message.reply_markup, advisory_id, idx, None)
                    text = query.message.text + f"\n\n\u23f3 \u5efa\u8bae #{idx+1} \u6267\u884c\u4e2d..."
                    await query.edit_message_text(text=text, reply_markup=new_markup)
                elif action_type == "cancel":
                    await redis_client.lpush(
                        "advisory:telegram_actions",
                        json.dumps({"advisory_id": advisory_id, "index": idx, "action": "cancel"})
                    )
                    # 恢复为 accept/reject 按钮
                    restore_row = [
                        InlineKeyboardButton(f"\u2705 \u91c7\u7eb3 #{idx+1}", callback_data=f"accept:{advisory_id}:{idx}"),
                        InlineKeyboardButton(f"\u274c \u62d2\u7edd #{idx+1}", callback_data=f"reject:{advisory_id}:{idx}"),
                    ]
                    new_markup = _rebuild_keyboard(query.message.reply_markup, advisory_id, idx, restore_row)
                    await query.edit_message_reply_markup(reply_markup=new_markup)

                logger.info(f"Telegram callback: {action_type} advisory={advisory_id} idx={idx}")

            app.add_handler(CallbackQueryHandler(handle_callback))
            await app.initialize()
            await app.start()
            await app.updater.start_polling(drop_pending_updates=True)
            self._app = app
            logger.info("Telegram callback handler started")
        except Exception as e:
            logger.error(f"Failed to start Telegram callback handler: {e}")

    async def stop(self):
        """停止 Telegram Application 并释放资源"""
        if self._app:
            try:
                if self._app.updater and self._app.updater.running:
                    await self._app.updater.stop()
                if self._app.running:
                    await self._app.stop()
                await self._app.shutdown()
                logger.info("Telegram callback handler stopped")
            except Exception as e:
                logger.error(f"Failed to stop Telegram callback handler: {e}")
            finally:
                self._app = None
