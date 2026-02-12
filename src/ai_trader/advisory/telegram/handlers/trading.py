"""交易控制 handler"""

import json
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from ..auth import authorized


@authorized
async def trading_command(update, context):
    """处理 /trading 命令"""
    text, keyboard = await _build_trading_view(context)
    await update.message.reply_text(text, reply_markup=keyboard)


async def trading_callback(update, context):
    """处理菜单回调"""
    query = update.callback_query
    text, keyboard = await _build_trading_view(context)
    await query.edit_message_text(text, reply_markup=keyboard)


@authorized
async def trading_toggle_callback(update, context):
    """处理交易开关切换请求（显示确认）"""
    query = update.callback_query
    await query.answer()

    data = query.data  # trd:toggle:{on|off}
    parts = data.split(":")
    if len(parts) != 3:
        return

    target_state = parts[2]  # on or off
    label = "开启" if target_state == "on" else "关闭"

    text = f"⚠️ 确认{label}交易？\n\n{'开启后系统将根据策略自动进行交易决策' if target_state == 'on' else '关闭后系统将停止所有交易决策'}"

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"✅ 确认{label}", callback_data=f"trd:confirm:{target_state}"),
            InlineKeyboardButton("❌ 取消", callback_data="menu:trading"),
        ],
    ])

    await query.edit_message_text(text, reply_markup=keyboard)


@authorized
async def trading_confirm_callback(update, context):
    """处理交易开关确认"""
    query = update.callback_query
    await query.answer()

    data = query.data  # trd:confirm:{on|off}
    parts = data.split(":")
    if len(parts) != 3:
        return

    target_state = parts[2] == "on"
    redis = context.bot_data.get("redis")

    if not redis:
        await query.edit_message_text("❌ 服务不可用")
        return

    # 读取当前配置
    raw = await redis.get("trading:config")
    config = json.loads(raw) if raw else {}

    # 更新开关
    config["enabled"] = target_state
    await redis.set("trading:config", json.dumps(config))

    # 通知其他组件
    await redis.publish("trading:config:updated", json.dumps(config))

    label = "已开启" if target_state else "已关闭"
    emoji = "🟢" if target_state else "🔴"

    await query.edit_message_text(
        f"{emoji} 交易{label}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⚙️ 查看交易控制", callback_data="menu:trading")],
            [InlineKeyboardButton("◀️ 返回主菜单", callback_data="menu:main")],
        ]),
    )


async def _build_trading_view(context) -> tuple:
    """构建交易控制视图"""
    redis = context.bot_data.get("redis")

    if not redis:
        return "❌ 服务不可用", None

    raw = await redis.get("trading:config")
    config = json.loads(raw) if raw else {}

    enabled = config.get("enabled", False)
    interval = config.get("decisionInterval", "N/A")
    status_emoji = "🟢" if enabled else "🔴"
    status_label = "运行中" if enabled else "已停止"

    lines = [
        "⚙️ 交易控制",
        "━━━━━━━━━━━━",
        f"状态: {status_emoji} {status_label}",
        f"决策间隔: {interval} 分钟",
    ]

    # 显示其他配置信息
    if config.get("trading_symbols"):
        lines.append(f"交易对: {config['trading_symbols']}")
    if config.get("leverage_max"):
        lines.append(f"最大杠杆: {config['leverage_max']}x")
    if config.get("stop_loss_percent"):
        lines.append(f"止损: {config['stop_loss_percent']}%")
    if config.get("take_profit_percent"):
        lines.append(f"止盈: {config['take_profit_percent']}%")

    # 开关按钮
    if enabled:
        toggle_btn = InlineKeyboardButton("🔴 关闭交易", callback_data="trd:toggle:off")
    else:
        toggle_btn = InlineKeyboardButton("🟢 开启交易", callback_data="trd:toggle:on")

    keyboard = InlineKeyboardMarkup([
        [toggle_btn],
        [InlineKeyboardButton("◀️ 返回主菜单", callback_data="menu:main")],
    ])

    return "\n".join(lines), keyboard
