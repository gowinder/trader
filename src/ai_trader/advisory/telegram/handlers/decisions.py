"""决策历史 handler"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from ..auth import authorized
from ..formatters import format_action, format_number, truncate


@authorized
async def decisions_command(update, context):
    """处理 /decisions 命令"""
    text, keyboard = await _build_decisions_list(context)
    await update.message.reply_text(text, reply_markup=keyboard)


async def decisions_callback(update, context):
    """处理菜单回调"""
    query = update.callback_query
    text, keyboard = await _build_decisions_list(context)
    await query.edit_message_text(text, reply_markup=keyboard)


@authorized
async def decision_detail_callback(update, context):
    """处理决策详情回调"""
    query = update.callback_query
    await query.answer()

    data = query.data  # dec:detail:{uuid}
    parts = data.split(":", 2)
    if len(parts) != 3:
        return

    decision_id = parts[2]
    db = context.bot_data.get("db")

    if not db:
        await query.edit_message_text("❌ 数据不可用")
        return

    row = await db.fetchrow(
        """SELECT id, created_at, symbol, action, confidence, leverage,
                  entry_price, stop_loss, take_profit, reasoning_zh, reasoning,
                  strategy_preset, llm_provider, llm_model
           FROM decisions WHERE id = $1""",
        decision_id,
    )

    if not row:
        await query.edit_message_text("❌ 未找到该决策")
        return

    time_str = row["created_at"].strftime("%m-%d %H:%M")
    symbol_short = row["symbol"].replace("/USDT:USDT", "").replace("/USDT", "")
    reasoning = row["reasoning_zh"] or row["reasoning"] or "无"

    lines = [
        "🧠 决策详情",
        "━━━━━━━━━━━━",
        f"时间: {time_str}",
        f"交易对: {symbol_short}",
        f"动作: {format_action(row['action'])}",
        f"置信度: {row['confidence']}",
    ]

    if row["entry_price"]:
        lines.append(f"入场价: {format_number(float(row['entry_price']), 4)}")
    if row["stop_loss"]:
        lines.append(f"止损: {format_number(float(row['stop_loss']), 4)}")
    if row["take_profit"]:
        lines.append(f"止盈: {format_number(float(row['take_profit']), 4)}")
    if row["leverage"]:
        lines.append(f"杠杆: {float(row['leverage']):.0f}x")
    if row["strategy_preset"]:
        lines.append(f"策略: {row['strategy_preset']}")
    if row["llm_provider"]:
        lines.append(f"LLM: {row['llm_provider']}/{row['llm_model']}")

    lines.append("")
    lines.append(f"📝 理由: {truncate(reasoning, 500)}")

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ 返回决策列表", callback_data="menu:decisions")],
        [InlineKeyboardButton("◀️ 返回主菜单", callback_data="menu:main")],
    ])

    await query.edit_message_text("\n".join(lines), reply_markup=keyboard)


async def _build_decisions_list(context) -> tuple:
    """构建最近决策摘要列表"""
    db = context.bot_data.get("db")

    if not db:
        return "❌ 数据不可用", None

    rows = await db.fetch(
        """SELECT id, created_at, symbol, action, confidence
           FROM decisions
           ORDER BY created_at DESC LIMIT 10"""
    )

    if not rows:
        return "🧠 最近决策\n━━━━━━━━━━━━\n暂无决策记录", InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ 返回主菜单", callback_data="menu:main")],
        ])

    lines = ["🧠 最近决策", "━━━━━━━━━━━━"]
    buttons = []

    for i, row in enumerate(rows, 1):
        time_str = row["created_at"].strftime("%m-%d %H:%M")
        symbol_short = row["symbol"].replace("/USDT:USDT", "").replace("/USDT", "")
        action_label = format_action(row["action"])
        lines.append(f"{i}. {time_str} {symbol_short} {action_label} 置信度:{row['confidence']}")

        buttons.append([
            InlineKeyboardButton(
                f"🔍 #{i} {symbol_short} {action_label}",
                callback_data=f"dec:detail:{row['id']}",
            ),
        ])

    buttons.append([InlineKeyboardButton("◀️ 返回主菜单", callback_data="menu:main")])

    return "\n".join(lines), InlineKeyboardMarkup(buttons)
