"""Telegram 消息格式化工具"""


def escape_md(text: str) -> str:
    """转义 Telegram MarkdownV2 特殊字符"""
    special = r"_*[]()~`>#+-=|{}.!"
    result = ""
    for c in text:
        if c in special:
            result += "\\" + c
        else:
            result += c
    return result


def format_number(value: float, decimals: int = 2) -> str:
    """格式化数字，带千分位"""
    if abs(value) >= 1_000_000:
        return f"{value/1_000_000:,.{decimals}f}M"
    if abs(value) >= 1_000:
        return f"{value:,.{decimals}f}"
    return f"{value:.{decimals}f}"


def format_pnl(value: float, decimals: int = 2) -> str:
    """格式化盈亏，带正负号"""
    sign = "+" if value >= 0 else ""
    return f"{sign}{format_number(value, decimals)}"


def format_percent(value: float, decimals: int = 1) -> str:
    """格式化百分比"""
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.{decimals}f}%"


def truncate(text: str, max_len: int = 200) -> str:
    """截断文本"""
    if not text or len(text) <= max_len:
        return text or ""
    return text[:max_len - 3] + "..."


ACTION_LABELS = {
    "open_long": "开多",
    "open_short": "开空",
    "close_long": "平多",
    "close_short": "平空",
    "add_long": "加多",
    "add_short": "加空",
    "reduce_long": "减多",
    "reduce_short": "减空",
    "hold": "持有",
}


def format_action(action: str) -> str:
    """将 action 转为中文标签"""
    return ACTION_LABELS.get(action, action)
