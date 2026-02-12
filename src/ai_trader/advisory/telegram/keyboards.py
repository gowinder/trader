"""Telegram Inline Keyboard 构建工具"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """主菜单键盘"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 概览", callback_data="menu:overview"),
            InlineKeyboardButton("📈 持仓", callback_data="menu:positions"),
        ],
        [
            InlineKeyboardButton("🧠 决策", callback_data="menu:decisions"),
            InlineKeyboardButton("🤖 LLM", callback_data="menu:llm"),
        ],
        [
            InlineKeyboardButton("📋 策略", callback_data="menu:strategy"),
            InlineKeyboardButton("💡 Advisory", callback_data="menu:advisory"),
        ],
        [
            InlineKeyboardButton("⚙️ 交易控制", callback_data="menu:trading"),
        ],
    ])


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    """返回主菜单按钮"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ 返回主菜单", callback_data="menu:main")],
    ])


def confirm_keyboard(module: str, action: str) -> InlineKeyboardMarkup:
    """确认/取消键盘"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ 确认", callback_data=f"{module}:confirm:{action}"),
            InlineKeyboardButton("❌ 取消", callback_data=f"{module}:cancel:{action}"),
        ],
    ])


def build_detail_buttons(module: str, items: list, label_func=None) -> InlineKeyboardMarkup:
    """为列表项生成详情按钮，每行一个

    Args:
        module: 模块前缀 (pos/dec/llm)
        items: 列表项，每项需有 id 或 key
        label_func: 生成按钮文字的函数，接收 (index, item)，返回 str
    """
    buttons = []
    for i, item in enumerate(items):
        item_id = item.get("id") or item.get("key") or str(i)
        label = label_func(i, item) if label_func else f"详情 #{i+1}"
        buttons.append([
            InlineKeyboardButton(label, callback_data=f"{module}:detail:{item_id}"),
        ])
    buttons.append([InlineKeyboardButton("◀️ 返回主菜单", callback_data="menu:main")])
    return InlineKeyboardMarkup(buttons)
