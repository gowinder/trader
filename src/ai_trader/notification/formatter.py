"""通知消息格式化模块"""

from datetime import datetime
from typing import Optional

ACTION_EMOJI = {
    "open_long": "📈 开多",
    "open_short": "📉 开空",
    "close_long": "💰 平多",
    "close_short": "💰 平空",
    "add_long": "➕ 加仓(多)",
    "add_short": "➕ 加仓(空)",
    "reduce_long": "➖ 减仓(多)",
    "reduce_short": "➖ 减仓(空)",
    "hold": "⏸️ 持仓不动",
}

SEPARATOR = "━━━━━━━━━━━━━━━"


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def format_trade_message(
    symbol: str,
    action: str,
    price: float,
    size: float,
    leverage: int = 1,
    position_size_percent: float = 0.0,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None,
) -> str:
    emoji_label = ACTION_EMOJI.get(action, action)
    lines = [
        f"🔔 交易通知 | {emoji_label}",
        SEPARATOR,
        f"📌 交易对: {symbol}",
        f"💲 价格: {price}",
        f"📏 数量: {size}",
        f"⚡ 杠杆: {leverage}x",
        f"📊 仓位比例: {position_size_percent:.1f}%",
    ]
    if stop_loss is not None:
        lines.append(f"🛡️ 止损: {stop_loss}")
    if take_profit is not None:
        lines.append(f"🎯 止盈: {take_profit}")
    lines.append(SEPARATOR)
    lines.append(f"🕐 {_timestamp()}")
    return "\n".join(lines)


def format_stop_loss_take_profit_message(
    symbol: str,
    side: str,
    trigger_type: str,
    entry_price: float,
    trigger_price: float,
    pnl_percent: float,
) -> str:
    emoji = "🛡️ 止损" if trigger_type == "stop_loss" else "🎯 止盈"
    pnl_emoji = "🟢" if pnl_percent >= 0 else "🔴"
    lines = [
        f"⚠️ {emoji}触发",
        SEPARATOR,
        f"📌 交易对: {symbol}",
        f"📍 方向: {side}",
        f"💲 入场价: {entry_price}",
        f"💲 触发价: {trigger_price}",
        f"{pnl_emoji} 盈亏: {pnl_percent:+.2f}%",
        SEPARATOR,
        f"🕐 {_timestamp()}",
    ]
    return "\n".join(lines)


def format_decision_message(
    symbol: str,
    action: str,
    confidence: float = 0.0,
    reasoning: str = "",
    risk_note: str = "",
) -> str:
    emoji_label = ACTION_EMOJI.get(action, action)

    if action == "hold":
        return f"⏸️ {symbol} | 持仓不动 | 置信度 {confidence:.0f}% | {_timestamp()}"

    lines = [
        f"🧠 决策通知 | {emoji_label}",
        SEPARATOR,
        f"📌 交易对: {symbol}",
        f"📊 置信度: {confidence:.0f}%",
    ]
    if reasoning:
        lines.append(f"💡 理由: {reasoning}")
    if risk_note:
        lines.append(f"⚠️ 风险: {risk_note}")
    lines.append(SEPARATOR)
    lines.append(f"🕐 {_timestamp()}")
    return "\n".join(lines)


def format_backtest_message(
    symbol: str,
    start_date: str,
    end_date: str,
    return_pct: float,
    win_rate: float,
    max_drawdown_pct: float,
    sharpe_ratio: float,
    total_trades: int,
) -> str:
    return_emoji = "🟢" if return_pct >= 0 else "🔴"
    lines = [
        "📊 回测完成",
        SEPARATOR,
        f"📌 交易对: {symbol}",
        f"📅 区间: {start_date} ~ {end_date}",
        f"{return_emoji} 收益率: {return_pct:+.2f}%",
        f"🎯 胜率: {win_rate:.1f}%",
        f"📉 最大回撤: {max_drawdown_pct:.2f}%",
        f"📐 夏普比率: {sharpe_ratio:.2f}",
        f"🔢 总交易数: {total_trades}",
        SEPARATOR,
        f"🕐 {_timestamp()}",
    ]
    return "\n".join(lines)
