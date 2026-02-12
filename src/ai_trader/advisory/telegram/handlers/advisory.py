"""Advisory 建议管理 handler"""

import json
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from ..auth import authorized
from ..formatters import truncate


URGENCY_EMOJI = {"high": "🔴", "medium": "🟡", "low": "🟢"}


@authorized
async def advisory_command(update, context):
    """处理 /advisory 命令"""
    text, keyboard = await _build_advisory_list(context)
    await update.message.reply_text(text, reply_markup=keyboard)


async def advisory_callback(update, context):
    """处理菜单回调"""
    query = update.callback_query
    text, keyboard = await _build_advisory_list(context)
    await query.edit_message_text(text, reply_markup=keyboard)


@authorized
async def advisory_detail_callback(update, context):
    """处理 Advisory 详情回调"""
    query = update.callback_query
    await query.answer()

    data = query.data  # adv:detail:{advisory_id_short}
    parts = data.split(":", 2)
    if len(parts) != 3:
        return

    advisory_short_id = parts[2]
    advisory_persistence = context.bot_data.get("advisory_persistence")

    if not advisory_persistence:
        await query.edit_message_text("❌ 数据不可用")
        return

    # 从待处理列表中查找匹配的 advisory
    advisories = await advisory_persistence.get_pending_advisories(limit=20)
    target = None
    for adv in advisories:
        if str(adv["id"]).startswith(advisory_short_id):
            target = adv
            break

    if not target:
        await query.edit_message_text("❌ 未找到该 Advisory")
        return

    urgency_emoji = URGENCY_EMOJI.get(target.get("urgency", ""), "⚪")
    lines = [
        f"💡 Advisory 详情 [{urgency_emoji} {target.get('urgency', 'N/A').upper()}]",
        "━━━━━━━━━━━━",
        f"触发类型: {target.get('trigger_type', 'N/A')}",
        f"市场概况: {truncate(target.get('market_summary', ''), 300)}",
        "",
    ]

    suggestions = target.get("suggestions", [])
    if isinstance(suggestions, str):
        suggestions = json.loads(suggestions)

    # 过滤掉聚合产生的 null 项
    suggestions = [s for s in suggestions if s and s.get("id")]

    buttons = []
    for i, s in enumerate(suggestions):
        status_emoji = {"pending": "⏳", "accepted": "✅", "rejected": "❌", "executed": "🎯"}.get(s.get("status", ""), "❓")
        lines.append(f"建议 {i+1}: {status_emoji} {s.get('action', 'N/A')}")
        lines.append(f"  目标: {s.get('target', 'N/A')}")
        lines.append(f"  理由: {truncate(s.get('reasoning', ''), 150)}")
        lines.append(f"  风险: {truncate(s.get('risk_note', ''), 100)}")
        lines.append("")

        if s.get("status") == "pending":
            advisory_id = str(target["id"])
            buttons.append([
                InlineKeyboardButton(f"✅ 采纳 #{i+1}", callback_data=f"adv:accept:{advisory_id}:{i}"),
                InlineKeyboardButton(f"❌ 拒绝 #{i+1}", callback_data=f"adv:reject:{advisory_id}:{i}"),
            ])

    buttons.append([InlineKeyboardButton("◀️ 返回 Advisory 列表", callback_data="menu:advisory")])
    buttons.append([InlineKeyboardButton("◀️ 返回主菜单", callback_data="menu:main")])

    await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons))


@authorized
async def advisory_action_callback(update, context):
    """处理 Advisory 建议操作（采纳/拒绝/确认/取消）"""
    query = update.callback_query
    await query.answer()

    data = query.data  # adv:{action}:{advisory_id}:{index}
    parts = data.split(":")
    if len(parts) != 4:
        return

    action_type = parts[1]  # accept/reject/confirm/cancel
    advisory_id = parts[2]
    try:
        idx = int(parts[3])
    except ValueError:
        return

    redis = context.bot_data.get("redis")
    if not redis:
        return

    # 将操作推入 Redis 队列，由 advisory 执行监听器处理
    await redis.lpush(
        "advisory:telegram_actions",
        json.dumps({"advisory_id": advisory_id, "index": idx, "action": action_type}),
    )

    # 更新消息中的按钮
    original_markup = query.message.reply_markup

    if action_type == "accept":
        new_markup = _rebuild_keyboard(original_markup, advisory_id, idx, [
            InlineKeyboardButton(f"⚠️ 确认#{idx+1}?", callback_data=f"adv:confirm:{advisory_id}:{idx}"),
            InlineKeyboardButton(f"↩️ 取消#{idx+1}", callback_data=f"adv:cancel:{advisory_id}:{idx}"),
        ])
        await query.edit_message_reply_markup(reply_markup=new_markup)
    elif action_type == "reject":
        new_markup = _rebuild_keyboard(original_markup, advisory_id, idx, None)
        await query.edit_message_reply_markup(reply_markup=new_markup)
    elif action_type == "confirm":
        new_markup = _rebuild_keyboard(original_markup, advisory_id, idx, None)
        text = query.message.text + f"\n\n⏳ 建议 #{idx+1} 执行中..."
        await query.edit_message_text(text=text, reply_markup=new_markup)
    elif action_type == "cancel":
        new_markup = _rebuild_keyboard(original_markup, advisory_id, idx, [
            InlineKeyboardButton(f"✅ 采纳 #{idx+1}", callback_data=f"adv:accept:{advisory_id}:{idx}"),
            InlineKeyboardButton(f"❌ 拒绝 #{idx+1}", callback_data=f"adv:reject:{advisory_id}:{idx}"),
        ])
        await query.edit_message_reply_markup(reply_markup=new_markup)


@authorized
async def advisory_trigger_callback(update, context):
    """处理立即分析触发"""
    query = update.callback_query
    await query.answer()

    redis = context.bot_data.get("redis")
    if not redis:
        await query.edit_message_text("❌ 服务不可用")
        return

    await redis.publish("advisory:manual_trigger", "telegram")
    await query.edit_message_text(
        "🔄 Advisory 分析已触发，请等待结果推送...",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💡 刷新列表", callback_data="menu:advisory")],
            [InlineKeyboardButton("◀️ 返回主菜单", callback_data="menu:main")],
        ]),
    )


def _rebuild_keyboard(original_markup, advisory_id, idx, replacement_row):
    """替换指定 idx 的按钮行，保留其余行"""
    new_rows = []
    if original_markup and original_markup.inline_keyboard:
        for row in original_markup.inline_keyboard:
            row_matches = any(
                btn.callback_data and f":{advisory_id}:{idx}" in btn.callback_data
                for btn in row
            )
            if row_matches:
                if replacement_row is not None:
                    new_rows.append(replacement_row)
            else:
                new_rows.append(row)
    return InlineKeyboardMarkup(new_rows) if new_rows else None


async def _build_advisory_list(context) -> tuple:
    """构建待处理 Advisory 列表"""
    advisory_persistence = context.bot_data.get("advisory_persistence")

    if not advisory_persistence:
        return "❌ 数据不可用", None

    advisories = await advisory_persistence.get_pending_advisories(limit=10)

    lines = ["💡 Advisory 建议", "━━━━━━━━━━━━"]
    buttons = [[InlineKeyboardButton("🔄 立即分析", callback_data="adv:trigger")]]

    if not advisories:
        lines.append("暂无待处理建议")
    else:
        lines.append(f"待处理: {len(advisories)} 条")
        lines.append("")

        for i, adv in enumerate(advisories, 1):
            urgency_emoji = URGENCY_EMOJI.get(adv.get("urgency", ""), "⚪")
            trigger = adv.get("trigger_type", "N/A")
            suggestions = adv.get("suggestions", [])
            if isinstance(suggestions, str):
                suggestions = json.loads(suggestions)
            suggestions = [s for s in suggestions if s and s.get("id")]
            suggestion_count = len(suggestions)
            time_str = adv["created_at"].strftime("%m-%d %H:%M") if adv.get("created_at") else ""

            lines.append(f"{i}. {urgency_emoji} {time_str} {trigger} ({suggestion_count}条建议)")

            short_id = str(adv["id"])[:8]
            buttons.append([
                InlineKeyboardButton(
                    f"🔍 #{i} 查看详情",
                    callback_data=f"adv:detail:{short_id}",
                ),
            ])

    buttons.append([InlineKeyboardButton("◀️ 返回主菜单", callback_data="menu:main")])

    return "\n".join(lines), InlineKeyboardMarkup(buttons)
