"""持仓查看 handler"""

import json
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from ..auth import authorized
from ..formatters import format_number, format_pnl, format_percent


@authorized
async def positions_command(update, context):
    """处理 /positions 命令"""
    text, keyboard = await _build_positions_list(context)
    await update.message.reply_text(text, reply_markup=keyboard)


async def positions_callback(update, context):
    """处理菜单回调"""
    query = update.callback_query
    text, keyboard = await _build_positions_list(context)
    await query.edit_message_text(text, reply_markup=keyboard)


@authorized
async def position_detail_callback(update, context):
    """处理持仓详情回调"""
    query = update.callback_query
    await query.answer()

    data = query.data  # pos:detail:BTCUSDT
    parts = data.split(":", 2)
    if len(parts) != 3:
        return

    symbol = parts[2]
    redis = context.bot_data.get("redis")

    if not redis:
        await query.edit_message_text("❌ 数据不可用")
        return

    raw = await redis.get("trading:account_state")
    if not raw:
        await query.edit_message_text("❌ 无账户状态数据")
        return

    state = json.loads(raw)
    positions = state.get("positions", {})
    pos = positions.get(symbol)

    if not pos:
        await query.edit_message_text(f"❌ 未找到 {symbol} 的持仓")
        return

    side_emoji = "🟢" if pos.get("side") == "long" else "🔴"
    side_label = "多" if pos.get("side") == "long" else "空"
    roi = pos.get("roi", 0.0)

    lines = [
        f"📈 持仓详情 - {symbol}",
        "━━━━━━━━━━━━",
        f"方向: {side_emoji}{side_label}",
        f"数量: {format_number(pos.get('size', 0), 4)}",
        f"入场价: {format_number(pos.get('entry_price', 0), 4)}",
        f"标记价: {format_number(pos.get('mark_price', 0), 4)}",
        f"杠杆: {pos.get('leverage', 1)}x",
        f"保证金: {format_number(pos.get('margin', 0))} USDT",
        f"未实现盈亏: {format_pnl(pos.get('unrealized_pnl', 0))} USDT",
        f"ROI: {format_percent(roi)}",
    ]

    if pos.get("liquidation_price"):
        lines.append(f"强平价: {format_number(pos['liquidation_price'], 4)}")

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ 返回持仓列表", callback_data="menu:positions")],
        [InlineKeyboardButton("◀️ 返回主菜单", callback_data="menu:main")],
    ])

    await query.edit_message_text("\n".join(lines), reply_markup=keyboard)


async def _build_positions_list(context) -> tuple:
    """构建持仓摘要列表"""
    redis = context.bot_data.get("redis")

    if not redis:
        return "❌ 数据不可用", None

    raw = await redis.get("trading:account_state")
    if not raw:
        return "📈 当前持仓 (0)\n━━━━━━━━━━━━\n无持仓", InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ 返回主菜单", callback_data="menu:main")],
        ])

    state = json.loads(raw)
    positions = state.get("positions", {})

    if not positions:
        return "📈 当前持仓 (0)\n━━━━━━━━━━━━\n无持仓", InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ 返回主菜单", callback_data="menu:main")],
        ])

    lines = [f"📈 当前持仓 ({len(positions)})", "━━━━━━━━━━━━"]
    buttons = []

    for i, (key, pos) in enumerate(positions.items(), 1):
        side_emoji = "🟢" if pos.get("side") == "long" else "🔴"
        side_label = "多" if pos.get("side") == "long" else "空"
        roi = pos.get("roi", 0.0)
        symbol_short = pos.get("symbol", key).replace("/USDT:USDT", "").replace("/USDT", "")
        lines.append(f"{i}. {symbol_short} {side_emoji}{side_label} {format_percent(roi)}")
        buttons.append([
            InlineKeyboardButton(f"🔍 {symbol_short} 详情", callback_data=f"pos:detail:{key}"),
        ])

    buttons.append([InlineKeyboardButton("◀️ 返回主菜单", callback_data="menu:main")])

    return "\n".join(lines), InlineKeyboardMarkup(buttons)
