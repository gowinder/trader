"""策略管理 handler"""

import json
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from ..auth import authorized


@authorized
async def strategy_command(update, context):
    """处理 /strategy 命令"""
    text, keyboard = await _build_strategy_view(context)
    await update.message.reply_text(text, reply_markup=keyboard)


async def strategy_callback(update, context):
    """处理菜单回调"""
    query = update.callback_query
    text, keyboard = await _build_strategy_view(context)
    await query.edit_message_text(text, reply_markup=keyboard)


@authorized
async def strategy_switch_callback(update, context):
    """处理策略切换请求（显示确认）"""
    query = update.callback_query
    await query.answer()

    data = query.data  # str:switch:{preset_id}
    parts = data.split(":")
    if len(parts) != 3:
        return

    preset_id = int(parts[2])
    strategy_service = context.bot_data.get("strategy_service")

    if not strategy_service:
        await query.edit_message_text("❌ 策略服务不可用")
        return

    preset = await strategy_service.get_preset_by_id(preset_id)
    if not preset:
        await query.edit_message_text("❌ 未找到该策略预设")
        return

    risk_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(preset.get("risk_level", ""), "⚪")

    text = (
        f"⚠️ 确认切换策略？\n\n"
        f"策略: {preset['display_name']}\n"
        f"风险: {risk_emoji} {preset.get('risk_level', 'N/A')}\n"
        f"说明: {preset.get('description', 'N/A')}"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ 确认切换", callback_data=f"str:confirm:{preset_id}"),
            InlineKeyboardButton("❌ 取消", callback_data="menu:strategy"),
        ],
    ])

    await query.edit_message_text(text, reply_markup=keyboard)


@authorized
async def strategy_confirm_callback(update, context):
    """处理策略切换确认"""
    query = update.callback_query
    await query.answer()

    data = query.data  # str:confirm:{preset_id}
    parts = data.split(":")
    if len(parts) != 3:
        return

    preset_id = int(parts[2])
    strategy_service = context.bot_data.get("strategy_service")
    redis = context.bot_data.get("redis")

    if not strategy_service:
        await query.edit_message_text("❌ 策略服务不可用")
        return

    success = await strategy_service.activate_preset(preset_id)

    if success:
        # 更新 Redis 缓存并通知其他组件
        preset = await strategy_service.get_preset_by_id(preset_id)
        if redis and preset:
            config_json = preset.get("config_json", "{}")
            if isinstance(config_json, str):
                config_data = json.loads(config_json)
            else:
                config_data = config_json
            await redis.set("strategy:active_preset", json.dumps({
                "name": preset["name"],
                "config": config_data,
                "is_locked": False,
            }))
            await redis.publish("strategy:preset:updated", json.dumps({
                "preset_id": preset_id,
                "name": preset["name"],
            }))

        await query.edit_message_text(
            f"✅ 策略已切换到: {preset['display_name'] if preset else preset_id}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 查看策略", callback_data="menu:strategy")],
                [InlineKeyboardButton("◀️ 返回主菜单", callback_data="menu:main")],
            ]),
        )
    else:
        await query.edit_message_text(
            "❌ 策略切换失败",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀️ 返回策略", callback_data="menu:strategy")],
            ]),
        )


async def _build_strategy_view(context) -> tuple:
    """构建策略管理视图"""
    strategy_service = context.bot_data.get("strategy_service")

    if not strategy_service:
        return "❌ 策略服务不可用", None

    active = await strategy_service.get_active_preset()
    all_presets = await strategy_service.get_all_presets()

    lines = ["📋 策略管理", "━━━━━━━━━━━━"]

    if active:
        activated_at = active.get("current_activated_at")
        time_str = activated_at.strftime("%m-%d %H:%M") if activated_at else "N/A"
        risk_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(active.get("risk_level", ""), "⚪")

        lines.append(f"当前策略: {active['display_name']}")
        lines.append(f"风险等级: {risk_emoji} {active.get('risk_level', 'N/A')}")
        lines.append(f"激活时间: {time_str}")
    else:
        lines.append("当前策略: 无")

    lines.append("")
    lines.append("可用预设:")

    buttons = []
    for preset in all_presets:
        risk_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(preset.get("risk_level", ""), "⚪")
        is_active = active and preset["id"] == active["id"]
        marker = " ✓" if is_active else ""
        lines.append(f"  {risk_emoji} {preset['display_name']}{marker}")

        if not is_active:
            buttons.append([
                InlineKeyboardButton(
                    f"🔄 切换到 {preset['display_name']}",
                    callback_data=f"str:switch:{preset['id']}",
                ),
            ])

    buttons.append([InlineKeyboardButton("◀️ 返回主菜单", callback_data="menu:main")])

    return "\n".join(lines), InlineKeyboardMarkup(buttons)
