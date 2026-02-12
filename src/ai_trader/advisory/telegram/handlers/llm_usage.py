"""LLM 调用统计 handler"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from ..auth import authorized
from ..formatters import format_number


@authorized
async def llm_command(update, context):
    """处理 /llm 命令"""
    text, keyboard = await _build_llm_stats(context)
    await update.message.reply_text(text, reply_markup=keyboard)


async def llm_callback(update, context):
    """处理菜单回调"""
    query = update.callback_query
    text, keyboard = await _build_llm_stats(context)
    await query.edit_message_text(text, reply_markup=keyboard)


@authorized
async def llm_records_callback(update, context):
    """处理最近调用记录回调"""
    query = update.callback_query
    await query.answer()

    persistence = context.bot_data.get("persistence")
    if not persistence:
        await query.edit_message_text("❌ 数据不可用")
        return

    result = await persistence.get_llm_usage_records(limit=5)
    records = result.get("records", [])

    if not records:
        await query.edit_message_text(
            "🤖 最近 LLM 调用\n━━━━━━━━━━━━\n暂无调用记录",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀️ 返回 LLM 统计", callback_data="menu:llm")],
            ]),
        )
        return

    lines = ["🤖 最近 LLM 调用", "━━━━━━━━━━━━"]
    buttons = []

    for i, r in enumerate(records, 1):
        ts = r["timestamp"][:16].replace("T", " ")
        status = "✅" if r["success"] else "❌"
        lines.append(
            f"{i}. {status} {ts} {r['provider']}/{r['model'][:15]}"
            f" {r['total_tokens']}tok ${r['cost_usd']:.4f}"
        )
        buttons.append([
            InlineKeyboardButton(
                f"🔍 #{i} {r['provider']}/{r['model'][:10]}",
                callback_data=f"llm:detail:{r['id'][:8]}",
            ),
        ])

    buttons.append([InlineKeyboardButton("◀️ 返回 LLM 统计", callback_data="menu:llm")])
    buttons.append([InlineKeyboardButton("◀️ 返回主菜单", callback_data="menu:main")])

    await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons))


@authorized
async def llm_detail_callback(update, context):
    """处理 LLM 调用详情回调"""
    query = update.callback_query
    await query.answer()

    data = query.data  # llm:detail:{short_id}
    parts = data.split(":", 2)
    if len(parts) != 3:
        return

    short_id = parts[2]
    db = context.bot_data.get("db")

    if not db:
        await query.edit_message_text("❌ 数据不可用")
        return

    row = await db.fetchrow(
        """SELECT id, created_at, provider, model, input_tokens, output_tokens,
                  total_tokens, cost_usd, latency_ms, success, error_message
           FROM llm_usage WHERE CAST(id AS TEXT) LIKE $1
           ORDER BY created_at DESC LIMIT 1""",
        f"{short_id}%",
    )

    if not row:
        await query.edit_message_text("❌ 未找到该记录")
        return

    status = "✅ 成功" if row["success"] else "❌ 失败"
    time_str = row["created_at"].strftime("%m-%d %H:%M:%S")

    lines = [
        "🤖 LLM 调用详情",
        "━━━━━━━━━━━━",
        f"时间: {time_str}",
        f"状态: {status}",
        f"Provider: {row['provider']}",
        f"模型: {row['model']}",
        f"Input Tokens: {format_number(row['input_tokens'], 0)}",
        f"Output Tokens: {format_number(row['output_tokens'], 0)}",
        f"Total Tokens: {format_number(row['total_tokens'], 0)}",
        f"费用: ${float(row['cost_usd']):.6f}",
        f"延迟: {row['latency_ms']}ms",
    ]

    if row["error_message"]:
        lines.append(f"错误: {row['error_message'][:200]}")

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ 返回调用记录", callback_data="llm:records")],
        [InlineKeyboardButton("◀️ 返回主菜单", callback_data="menu:main")],
    ])

    await query.edit_message_text("\n".join(lines), reply_markup=keyboard)


async def _build_llm_stats(context) -> tuple:
    """构建 LLM 统计消息"""
    persistence = context.bot_data.get("persistence")

    if not persistence:
        return "❌ 数据不可用", None

    stats = await persistence.get_llm_usage_stats()

    lines = [
        "🤖 LLM 调用统计",
        "━━━━━━━━━━━━",
        f"📊 总调用: {format_number(stats['total_calls'], 0)} 次",
        f"📝 总 Token: {format_number(stats['total_tokens'], 0)}",
        f"💰 总费用: ${stats['total_cost_usd']:.4f}",
        f"💵 今日费用: ${stats['today_cost_usd']:.4f}",
        f"✅ 成功率: {stats['success_rate']:.1f}%",
        f"⏱ 平均延迟: {stats['avg_latency_ms']:.0f}ms",
    ]

    if stats.get("by_provider"):
        lines.append("")
        lines.append("📊 按 Provider:")
        for provider, data in stats["by_provider"].items():
            lines.append(f"  {provider}: {data['calls']}次 ${data['cost_usd']:.4f}")

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 最近调用记录", callback_data="llm:records")],
        [InlineKeyboardButton("◀️ 返回主菜单", callback_data="menu:main")],
    ])

    return "\n".join(lines), keyboard
