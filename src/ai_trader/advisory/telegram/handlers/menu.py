"""主菜单和帮助命令 handler"""

from ..auth import authorized
from ..keyboards import main_menu_keyboard


HELP_TEXT = """📖 可用命令

/overview - 📊 账户概览
/positions - 📈 当前持仓
/decisions - 🧠 最近决策
/llm - 🤖 LLM 调用统计
/strategy - 📋 策略管理
/advisory - 💡 Advisory 建议
/trading - ⚙️ 交易控制
/menu - 显示主菜单
/help - 显示此帮助"""


@authorized
async def start_command(update, context):
    """处理 /start 和 /menu 命令"""
    await update.message.reply_text(
        "🤖 AI Trader Bot\n\n请选择功能：",
        reply_markup=main_menu_keyboard(),
    )


@authorized
async def help_command(update, context):
    """处理 /help 命令"""
    await update.message.reply_text(HELP_TEXT)


@authorized
async def menu_callback(update, context):
    """处理菜单 inline button 回调"""
    query = update.callback_query
    await query.answer()
    data = query.data  # menu:xxx

    parts = data.split(":")
    if len(parts) != 2:
        return

    target = parts[1]

    if target == "main":
        await query.edit_message_text(
            "🤖 AI Trader Bot\n\n请选择功能：",
            reply_markup=main_menu_keyboard(),
        )
        return

    # 将菜单按钮点击分发到对应 handler
    handler_map = {
        "overview": "overview_callback",
        "positions": "positions_callback",
        "decisions": "decisions_callback",
        "llm": "llm_callback",
        "strategy": "strategy_callback",
        "advisory": "advisory_callback",
        "trading": "trading_callback",
    }

    handler_name = handler_map.get(target)
    if handler_name and handler_name in context.bot_data:
        await context.bot_data[handler_name](update, context)
