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
