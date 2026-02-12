"""账户概览 handler"""

import json
from datetime import datetime, timezone
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from ..auth import authorized
from ..formatters import format_number, format_pnl


@authorized
async def overview_command(update, context):
    """处理 /overview 命令"""
    text, keyboard = await _build_overview(context)
    await update.message.reply_text(text, reply_markup=keyboard)


async def overview_callback(update, context):
    """处理菜单回调"""
    query = update.callback_query
    text, keyboard = await _build_overview(context)
    await query.edit_message_text(text, reply_markup=keyboard)


async def _build_overview(context) -> tuple:
    """构建概览消息"""
    redis = context.bot_data.get("redis")
    db = context.bot_data.get("db")

    lines = ["📊 账户概览", "━━━━━━━━━━━━"]

    # 从 Redis 获取账户状态
    equity = 0.0
    unrealized_pnl = 0.0
    position_count = 0

    if redis:
        raw = await redis.get("trading:account_state")
        if raw:
            state = json.loads(raw)
            account = state.get("account", {})
            equity = account.get("total_equity", 0.0)
            unrealized_pnl = account.get("unrealized_pnl", 0.0)
            positions = state.get("positions", {})
            position_count = len(positions)

    lines.append(f"💰 账户权益: {format_number(equity)} USDT")
    lines.append(f"📉 未实现盈亏: {format_pnl(unrealized_pnl)} USDT")
    lines.append(f"📌 当前持仓: {position_count} 个")

    # 从 PostgreSQL 获取统计
    if db:
        # 已实现盈亏
        pnl_row = await db.fetchrow(
            "SELECT COALESCE(SUM(realized_pnl), 0) as total_pnl FROM position_history WHERE status = 'closed'"
        )
        realized_pnl = float(pnl_row["total_pnl"]) if pnl_row else 0.0
        total_pnl = realized_pnl + unrealized_pnl
        lines.insert(4, f"📈 已实现盈亏: {format_pnl(realized_pnl)} USDT")
        lines.insert(5, f"📊 总盈亏: {format_pnl(total_pnl)} USDT")

        # 今日决策数
        today = datetime.now(timezone.utc).date()
        today_count = await db.fetchval(
            "SELECT COUNT(*) FROM decisions WHERE DATE(created_at) = $1", today
        )
        lines.append(f"🧠 今日决策: {today_count} 次")

        # 历史胜率
        win_row = await db.fetchrow(
            """SELECT COUNT(*) as total,
                      COUNT(*) FILTER (WHERE realized_pnl > 0) as wins
               FROM position_history WHERE status = 'closed'"""
        )
        if win_row and win_row["total"] > 0:
            win_rate = win_row["wins"] / win_row["total"] * 100
            lines.append(f"🎯 历史胜率: {win_rate:.1f}%")

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📈 查看持仓", callback_data="menu:positions"),
            InlineKeyboardButton("🧠 查看决策", callback_data="menu:decisions"),
        ],
        [InlineKeyboardButton("◀️ 返回主菜单", callback_data="menu:main")],
    ])

    return "\n".join(lines), keyboard
