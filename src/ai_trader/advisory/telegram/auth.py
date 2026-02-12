"""Telegram 鉴权装饰器"""

import functools
from ...utils.logger import logger


def authorized(func):
    """验证 chat_id 的装饰器，从 context.bot_data['chat_id'] 获取配置"""
    @functools.wraps(func)
    async def wrapper(update, context):
        expected = context.bot_data.get("chat_id")
        if not expected:
            return
        if str(update.effective_chat.id) != str(expected):
            logger.debug(f"Unauthorized chat_id: {update.effective_chat.id}")
            return
        return await func(update, context)
    return wrapper
