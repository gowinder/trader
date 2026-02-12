# Telegram Bot 交互功能实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将现有 Telegram 推送 bot 重构为 `telegram/` 包，增加命令交互功能（概览、持仓、决策、LLM、策略、Advisory、交易控制）。

**Architecture:** 重构 `src/ai_trader/advisory/telegram.py` 为 `telegram/` 包。Bot 使用 `python-telegram-bot` 的 `Application` 统一管理 polling 和消息发送。所有 handler 直接通过 `context.bot_data` 访问 Redis/PostgreSQL 连接。现有推送逻辑迁移到 `notifier.py`，调用方导入路径更新。

**Tech Stack:** python-telegram-bot (已安装)、asyncpg (PostgreSQL)、redis.asyncio (Redis)

**Design Doc:** `docs/plans/2026-02-12-telegram-bot-commands-design.md`

---

## Task 1: 创建 telegram/ 包骨架 + auth 模块

**Files:**
- Create: `src/ai_trader/advisory/telegram/__init__.py`
- Create: `src/ai_trader/advisory/telegram/auth.py`
- Create: `src/ai_trader/advisory/telegram/handlers/__init__.py`

**Step 1: 创建包目录和 __init__.py**

```python
# src/ai_trader/advisory/telegram/__init__.py
"""Telegram Bot 交互模块"""

from .bot import TelegramBot
from .notifier import TelegramNotifier

__all__ = ["TelegramBot", "TelegramNotifier"]
```

**Step 2: 实现 auth.py**

```python
# src/ai_trader/advisory/telegram/auth.py
"""Telegram 鉴权装饰器"""

import functools
from ...utils.logger import logger


def authorized(func):
    """验证 chat_id 的装饰器，从 context.bot_data['chat_id'] 获取配置"""
    @functools.wraps(func)
    async def wrapper(update, context):
        expected = context.bot_data.get("chat_id")
        if not expected:
            return
        if str(update.effective_chat.id) != str(expected):
            logger.debug(f"Unauthorized chat_id: {update.effective_chat.id}")
            return
        return await func(update, context)
    return wrapper
```

**Step 3: 创建 handlers/__init__.py**

```python
# src/ai_trader/advisory/telegram/handlers/__init__.py
```

**Step 4: 验证**

Run: `python -c "import ast; ast.parse(open('src/ai_trader/advisory/telegram/__init__.py').read()); ast.parse(open('src/ai_trader/advisory/telegram/auth.py').read()); print('OK')"`
Expected: OK

**Step 5: Commit**

```bash
git add src/ai_trader/advisory/telegram/__init__.py src/ai_trader/advisory/telegram/auth.py src/ai_trader/advisory/telegram/handlers/__init__.py
git commit -m "feat(telegram): create telegram/ package skeleton with auth decorator"
```

---

## Task 2: 实现 formatters.py 和 keyboards.py 工具模块

**Files:**
- Create: `src/ai_trader/advisory/telegram/formatters.py`
- Create: `src/ai_trader/advisory/telegram/keyboards.py`

**Step 1: 实现 formatters.py**

```python
# src/ai_trader/advisory/telegram/formatters.py
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
```

**Step 2: 实现 keyboards.py**

```python
# src/ai_trader/advisory/telegram/keyboards.py
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
```

**Step 3: 验证语法**

Run: `python -c "import ast; ast.parse(open('src/ai_trader/advisory/telegram/formatters.py').read()); ast.parse(open('src/ai_trader/advisory/telegram/keyboards.py').read()); print('OK')"`
Expected: OK

**Step 4: Commit**

```bash
git add src/ai_trader/advisory/telegram/formatters.py src/ai_trader/advisory/telegram/keyboards.py
git commit -m "feat(telegram): add formatters and keyboards utility modules"
```

---

## Task 3: 迁移 notifier.py（从现有 telegram.py）

**Files:**
- Create: `src/ai_trader/advisory/telegram/notifier.py`
- Keep (暂不删): `src/ai_trader/advisory/telegram.py`

**Step 1: 创建 notifier.py**

将现有 `telegram.py` 的内容迁移到 `notifier.py`，保持所有功能不变，但移除 `start_callback_handler` 方法（回调处理将在 bot.py 中统一管理）。

```python
# src/ai_trader/advisory/telegram/notifier.py
"""Telegram 通知推送模块（从 telegram.py 迁移）"""

from typing import Optional, List
from ...models.advisory import AdvisoryResult, Suggestion, Urgency
from ...utils.logger import logger

try:
    from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
    HAS_TELEGRAM = True
except ImportError:
    HAS_TELEGRAM = False
    Bot = None
    InlineKeyboardButton = None
    InlineKeyboardMarkup = None


URGENCY_EMOJI = {
    Urgency.HIGH: "\U0001f534",
    Urgency.MEDIUM: "\U0001f7e1",
    Urgency.LOW: "\U0001f7e2",
}


def format_advisory_message(result: AdvisoryResult, advisory_id: str) -> str:
    emoji = URGENCY_EMOJI.get(result.urgency, "\u26aa")
    lines = [
        f"\U0001f514 AI 交易建议 [{emoji} {result.urgency.value.upper()}]",
        "",
        f"\U0001f4ca 市场概况: {result.market_summary}",
    ]
    if result.suggestions:
        lines.append("")
        for i, s in enumerate(result.suggestions, 1):
            lines.append(f"建议 {i}/{len(result.suggestions)}: {s.action}")
            lines.append(f"  目标: {s.target}")
            lines.append(f"  理由: {s.reasoning}")
            lines.append(f"  风险: {s.risk_note}")
            lines.append("")
    else:
        lines.append("")
        lines.append("\u2705 当前无需调整")
    lines.append(f"\U0001f4cb ID: {advisory_id}")
    return "\n".join(lines)


def build_suggestion_keyboard(advisory_id: str, suggestions: List[Suggestion]):
    if not HAS_TELEGRAM or not suggestions:
        return None
    buttons = []
    for i, s in enumerate(suggestions):
        buttons.append([
            InlineKeyboardButton(f"\u2705 采纳 #{i+1}", callback_data=f"adv:accept:{advisory_id}:{i}"),
            InlineKeyboardButton(f"\u274c 拒绝 #{i+1}", callback_data=f"adv:reject:{advisory_id}:{i}"),
        ])
    return InlineKeyboardMarkup(buttons)


class TelegramNotifier:
    def __init__(self, bot_token: str = "", chat_id: str = "", bot=None):
        """初始化通知器

        Args:
            bot_token: Telegram bot token
            chat_id: 目标 chat id
            bot: 可选，传入已有的 Bot 实例（用于共享 Application 的 bot）
        """
        self.bot_token = bot_token
        self.chat_id = chat_id
        self._bot = bot
        if not self._bot and HAS_TELEGRAM and bot_token:
            self._bot = Bot(token=bot_token)

    @property
    def enabled(self) -> bool:
        return bool(self._bot and self.chat_id)

    async def send_advisory(self, result: AdvisoryResult, advisory_id: str) -> Optional[int]:
        if not self.enabled:
            logger.debug("Telegram not configured, skipping notification")
            return None
        try:
            text = format_advisory_message(result, advisory_id)
            keyboard = build_suggestion_keyboard(advisory_id, result.suggestions)
            msg = await self._bot.send_message(
                chat_id=self.chat_id, text=text,
                reply_markup=keyboard, parse_mode=None,
            )
            logger.info(f"Telegram advisory sent: msg_id={msg.message_id}")
            return msg.message_id
        except Exception as e:
            logger.error(f"Failed to send Telegram notification: {e}")
            return None

    async def send_text(self, text: str, parse_mode: Optional[str] = None) -> bool:
        """发送纯文本消息"""
        if not self.enabled:
            return False
        try:
            await self._bot.send_message(chat_id=self.chat_id, text=text, parse_mode=parse_mode)
            return True
        except Exception as e:
            logger.error(f"Failed to send text message: {e}")
            return False

    async def send_execution_result(self, suggestion_index: int, action: str, success: bool, message: str):
        if not self.enabled:
            return
        try:
            emoji = "\u2705" if success else "\u274c"
            text = f"{emoji} 建议 #{suggestion_index + 1} ({action}) 执行结果: {message}"
            await self._bot.send_message(chat_id=self.chat_id, text=text)
        except Exception as e:
            logger.error(f"Failed to send execution result: {e}")
```

注意变化：
- `build_suggestion_keyboard` 的 callback_data 格式改为 `adv:accept:{id}:{idx}` 以匹配新的统一回调格式
- `__init__` 增加可选 `bot` 参数，支持传入 Application 共享的 bot 实例
- 移除了 `start_callback_handler` 和 `stop` 方法（回调处理转移到 bot.py）

**Step 2: 验证语法**

Run: `python -c "import ast; ast.parse(open('src/ai_trader/advisory/telegram/notifier.py').read()); print('OK')"`
Expected: OK

**Step 3: Commit**

```bash
git add src/ai_trader/advisory/telegram/notifier.py
git commit -m "feat(telegram): migrate notifier from telegram.py to telegram/notifier.py"
```

---

## Task 4: 实现 menu handler

**Files:**
- Create: `src/ai_trader/advisory/telegram/handlers/menu.py`

**Step 1: 实现 menu.py**

```python
# src/ai_trader/advisory/telegram/handlers/menu.py
"""主菜单和帮助命令 handler"""

from ..auth import authorized
from ..keyboards import main_menu_keyboard


HELP_TEXT = """📖 可用命令

/overview - 📊 账户概览
/positions - 📈 当前持仓
/decisions - 🧠 最近决策
/llm - 🤖 LLM 调用统计
/strategy - 📋 策略管理
/advisory - 💡 Advisory 建议
/trading - ⚙️ 交易控制
/menu - 显示主菜单
/help - 显示此帮助"""


@authorized
async def start_command(update, context):
    """处理 /start 和 /menu 命令"""
    await update.message.reply_text(
        "🤖 AI Trader Bot\n\n请选择功能：",
        reply_markup=main_menu_keyboard(),
    )


@authorized
async def help_command(update, context):
    """处理 /help 命令"""
    await update.message.reply_text(HELP_TEXT)


@authorized
async def menu_callback(update, context):
    """处理菜单 inline button 回调"""
    query = update.callback_query
    await query.answer()
    data = query.data  # menu:xxx

    parts = data.split(":")
    if len(parts) != 2:
        return

    target = parts[1]

    if target == "main":
        await query.edit_message_text(
            "🤖 AI Trader Bot\n\n请选择功能：",
            reply_markup=main_menu_keyboard(),
        )
        return

    # 将菜单按钮点击分发到对应 handler
    handler_map = {
        "overview": "overview_callback",
        "positions": "positions_callback",
        "decisions": "decisions_callback",
        "llm": "llm_callback",
        "strategy": "strategy_callback",
        "advisory": "advisory_callback",
        "trading": "trading_callback",
    }

    handler_name = handler_map.get(target)
    if handler_name and handler_name in context.bot_data:
        await context.bot_data[handler_name](update, context)
```

**Step 2: 验证语法**

Run: `python -c "import ast; ast.parse(open('src/ai_trader/advisory/telegram/handlers/menu.py').read()); print('OK')"`
Expected: OK

**Step 3: Commit**

```bash
git add src/ai_trader/advisory/telegram/handlers/menu.py
git commit -m "feat(telegram): implement menu handler with /start /menu /help commands"
```

---

## Task 5: 实现 overview handler

**Files:**
- Create: `src/ai_trader/advisory/telegram/handlers/overview.py`

**Step 1: 实现 overview.py**

```python
# src/ai_trader/advisory/telegram/handlers/overview.py
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
```

**Step 2: 验证语法**

Run: `python -c "import ast; ast.parse(open('src/ai_trader/advisory/telegram/handlers/overview.py').read()); print('OK')"`
Expected: OK

**Step 3: Commit**

```bash
git add src/ai_trader/advisory/telegram/handlers/overview.py
git commit -m "feat(telegram): implement /overview handler with account stats"
```

---

## Task 6: 实现 positions handler

**Files:**
- Create: `src/ai_trader/advisory/telegram/handlers/positions.py`

**Step 1: 实现 positions.py**

```python
# src/ai_trader/advisory/telegram/handlers/positions.py
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
    parts = data.split(":")
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
```

**Step 2: 验证语法**

Run: `python -c "import ast; ast.parse(open('src/ai_trader/advisory/telegram/handlers/positions.py').read()); print('OK')"`
Expected: OK

**Step 3: Commit**

```bash
git add src/ai_trader/advisory/telegram/handlers/positions.py
git commit -m "feat(telegram): implement /positions handler with detail view"
```

---

## Task 7: 实现 decisions handler

**Files:**
- Create: `src/ai_trader/advisory/telegram/handlers/decisions.py`

**Step 1: 实现 decisions.py**

```python
# src/ai_trader/advisory/telegram/handlers/decisions.py
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
    parts = data.split(":")
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
        f"🧠 决策详情",
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

        # callback_data 限制 64 字节，用 UUID 前 8 位
        short_id = str(row["id"])[:8]
        buttons.append([
            InlineKeyboardButton(
                f"🔍 #{i} {symbol_short} {action_label}",
                callback_data=f"dec:detail:{row['id']}",
            ),
        ])

    buttons.append([InlineKeyboardButton("◀️ 返回主菜单", callback_data="menu:main")])

    return "\n".join(lines), InlineKeyboardMarkup(buttons)
```

注意：UUID 在 callback_data 中为 36 字节（含连字符），加上前缀 `dec:detail:` = 11 字节，总共 47 字节，不超过 64 字节限制。

**Step 2: 验证语法**

Run: `python -c "import ast; ast.parse(open('src/ai_trader/advisory/telegram/handlers/decisions.py').read()); print('OK')"`
Expected: OK

**Step 3: Commit**

```bash
git add src/ai_trader/advisory/telegram/handlers/decisions.py
git commit -m "feat(telegram): implement /decisions handler with detail view"
```

---

## Task 8: 实现 llm_usage handler

**Files:**
- Create: `src/ai_trader/advisory/telegram/handlers/llm_usage.py`

**Step 1: 实现 llm_usage.py**

```python
# src/ai_trader/advisory/telegram/handlers/llm_usage.py
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
    parts = data.split(":")
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
        f"🤖 LLM 调用详情",
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
```

**Step 2: 验证语法**

Run: `python -c "import ast; ast.parse(open('src/ai_trader/advisory/telegram/handlers/llm_usage.py').read()); print('OK')"`
Expected: OK

**Step 3: Commit**

```bash
git add src/ai_trader/advisory/telegram/handlers/llm_usage.py
git commit -m "feat(telegram): implement /llm handler with usage stats and records"
```

---

## Task 9: 实现 strategy handler

**Files:**
- Create: `src/ai_trader/advisory/telegram/handlers/strategy.py`

**Step 1: 实现 strategy.py**

```python
# src/ai_trader/advisory/telegram/handlers/strategy.py
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
            }))
            await redis.publish("strategy:preset:changed", json.dumps({
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
```

**Step 2: 验证语法**

Run: `python -c "import ast; ast.parse(open('src/ai_trader/advisory/telegram/handlers/strategy.py').read()); print('OK')"`
Expected: OK

**Step 3: Commit**

```bash
git add src/ai_trader/advisory/telegram/handlers/strategy.py
git commit -m "feat(telegram): implement /strategy handler with preset switching"
```

---

## Task 10: 实现 advisory handler

**Files:**
- Create: `src/ai_trader/advisory/telegram/handlers/advisory.py`

**Step 1: 实现 advisory.py**

```python
# src/ai_trader/advisory/telegram/handlers/advisory.py
"""Advisory 建议管理 handler"""

import json
from uuid import UUID
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
    parts = data.split(":")
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
```

**Step 2: 验证语法**

Run: `python -c "import ast; ast.parse(open('src/ai_trader/advisory/telegram/handlers/advisory.py').read()); print('OK')"`
Expected: OK

**Step 3: Commit**

```bash
git add src/ai_trader/advisory/telegram/handlers/advisory.py
git commit -m "feat(telegram): implement /advisory handler with suggestion management"
```

---

## Task 11: 实现 trading handler

**Files:**
- Create: `src/ai_trader/advisory/telegram/handlers/trading.py`

**Step 1: 实现 trading.py**

```python
# src/ai_trader/advisory/telegram/handlers/trading.py
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
```

**Step 2: 验证语法**

Run: `python -c "import ast; ast.parse(open('src/ai_trader/advisory/telegram/handlers/trading.py').read()); print('OK')"`
Expected: OK

**Step 3: Commit**

```bash
git add src/ai_trader/advisory/telegram/handlers/trading.py
git commit -m "feat(telegram): implement /trading handler with enable/disable toggle"
```

---

## Task 12: 实现 commands.py 和 bot.py

**Files:**
- Create: `src/ai_trader/advisory/telegram/commands.py`
- Create: `src/ai_trader/advisory/telegram/bot.py`

**Step 1: 实现 commands.py**

```python
# src/ai_trader/advisory/telegram/commands.py
"""命令注册模块"""

from telegram.ext import CommandHandler, CallbackQueryHandler

from .handlers.menu import start_command, help_command, menu_callback
from .handlers.overview import overview_command, overview_callback
from .handlers.positions import positions_command, positions_callback, position_detail_callback
from .handlers.decisions import decisions_command, decisions_callback, decision_detail_callback
from .handlers.llm_usage import llm_command, llm_callback, llm_records_callback, llm_detail_callback
from .handlers.strategy import (
    strategy_command, strategy_callback,
    strategy_switch_callback, strategy_confirm_callback,
)
from .handlers.advisory import (
    advisory_command, advisory_callback,
    advisory_detail_callback, advisory_action_callback,
    advisory_trigger_callback,
)
from .handlers.trading import (
    trading_command, trading_callback,
    trading_toggle_callback, trading_confirm_callback,
)


def register_commands(app):
    """注册所有命令和回调 handler"""

    # 命令 handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("menu", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("overview", overview_command))
    app.add_handler(CommandHandler("positions", positions_command))
    app.add_handler(CommandHandler("decisions", decisions_command))
    app.add_handler(CommandHandler("llm", llm_command))
    app.add_handler(CommandHandler("strategy", strategy_command))
    app.add_handler(CommandHandler("advisory", advisory_command))
    app.add_handler(CommandHandler("trading", trading_command))

    # 回调 handlers — 用 pattern 正则匹配分发
    app.add_handler(CallbackQueryHandler(menu_callback, pattern=r"^menu:"))
    app.add_handler(CallbackQueryHandler(position_detail_callback, pattern=r"^pos:detail:"))
    app.add_handler(CallbackQueryHandler(decision_detail_callback, pattern=r"^dec:detail:"))
    app.add_handler(CallbackQueryHandler(llm_records_callback, pattern=r"^llm:records$"))
    app.add_handler(CallbackQueryHandler(llm_detail_callback, pattern=r"^llm:detail:"))
    app.add_handler(CallbackQueryHandler(strategy_switch_callback, pattern=r"^str:switch:"))
    app.add_handler(CallbackQueryHandler(strategy_confirm_callback, pattern=r"^str:confirm:"))
    app.add_handler(CallbackQueryHandler(advisory_detail_callback, pattern=r"^adv:detail:"))
    app.add_handler(CallbackQueryHandler(advisory_trigger_callback, pattern=r"^adv:trigger$"))
    app.add_handler(CallbackQueryHandler(advisory_action_callback, pattern=r"^adv:(accept|reject|confirm|cancel):"))
    app.add_handler(CallbackQueryHandler(trading_toggle_callback, pattern=r"^trd:toggle:"))
    app.add_handler(CallbackQueryHandler(trading_confirm_callback, pattern=r"^trd:confirm:"))

    # 在 bot_data 中注册回调函数，供菜单 handler 分发
    app.bot_data["overview_callback"] = overview_callback
    app.bot_data["positions_callback"] = positions_callback
    app.bot_data["decisions_callback"] = decisions_callback
    app.bot_data["llm_callback"] = llm_callback
    app.bot_data["strategy_callback"] = strategy_callback
    app.bot_data["advisory_callback"] = advisory_callback
    app.bot_data["trading_callback"] = trading_callback
```

**Step 2: 实现 bot.py**

```python
# src/ai_trader/advisory/telegram/bot.py
"""Telegram Bot 生命周期管理"""

from ...utils.logger import logger
from .notifier import TelegramNotifier

try:
    from telegram.ext import Application
    HAS_TELEGRAM = True
except ImportError:
    HAS_TELEGRAM = False
    Application = None


class TelegramBot:
    """Telegram Bot 主类，统一管理 polling 和推送"""

    def __init__(self, bot_token: str, chat_id: str, redis=None, db=None,
                 persistence=None, strategy_service=None, advisory_persistence=None):
        """初始化 Bot

        Args:
            bot_token: Telegram Bot Token
            chat_id: 授权的 Chat ID
            redis: Redis 异步客户端
            db: DatabaseManager 实例
            persistence: DecisionPersistenceService 实例 (用于 LLM 查询)
            strategy_service: StrategyPresetService 实例
            advisory_persistence: AdvisoryPersistenceService 实例
        """
        self.bot_token = bot_token
        self.chat_id = chat_id
        self._app = None
        self._notifier = None

        if not HAS_TELEGRAM or not bot_token:
            logger.warning("python-telegram-bot not installed or token not configured")
            return

        self._app = Application.builder().token(bot_token).build()

        # 将共享资源存入 bot_data，供 handlers 通过 context.bot_data 访问
        self._app.bot_data["chat_id"] = chat_id
        self._app.bot_data["redis"] = redis
        self._app.bot_data["db"] = db
        self._app.bot_data["persistence"] = persistence
        self._app.bot_data["strategy_service"] = strategy_service
        self._app.bot_data["advisory_persistence"] = advisory_persistence

        # 注册命令和回调 handlers
        from .commands import register_commands
        register_commands(self._app)

        # 创建 notifier，共享 bot 实例
        self._notifier = TelegramNotifier(bot_token=bot_token, chat_id=chat_id, bot=self._app.bot)

    @property
    def notifier(self) -> TelegramNotifier:
        """获取通知器实例（供外部推送使用）"""
        if self._notifier:
            return self._notifier
        # 降级：没有 Application 时创建独立 notifier
        return TelegramNotifier(bot_token=self.bot_token, chat_id=self.chat_id)

    @property
    def enabled(self) -> bool:
        return bool(self._app and self.chat_id)

    async def start(self):
        """启动 Bot（初始化 + polling）"""
        if not self._app:
            logger.debug("Telegram Bot not configured, skipping start")
            return

        try:
            await self._app.initialize()
            await self._app.start()
            await self._app.updater.start_polling(drop_pending_updates=True)
            logger.info("Telegram Bot started (polling + commands)")
        except Exception as e:
            logger.error(f"Failed to start Telegram Bot: {e}")

    async def stop(self):
        """停止 Bot"""
        if not self._app:
            return
        try:
            if self._app.updater and self._app.updater.running:
                await self._app.updater.stop()
            if self._app.running:
                await self._app.stop()
            await self._app.shutdown()
            logger.info("Telegram Bot stopped")
        except Exception as e:
            logger.error(f"Failed to stop Telegram Bot: {e}")
        finally:
            self._app = None
```

**Step 3: 更新 __init__.py**

确保 `__init__.py` 导出正确（已在 Task 1 中创建，此处确认内容）。

**Step 4: 验证语法**

Run: `python -c "import ast; ast.parse(open('src/ai_trader/advisory/telegram/commands.py').read()); ast.parse(open('src/ai_trader/advisory/telegram/bot.py').read()); print('OK')"`
Expected: OK

**Step 5: Commit**

```bash
git add src/ai_trader/advisory/telegram/commands.py src/ai_trader/advisory/telegram/bot.py
git commit -m "feat(telegram): implement bot.py lifecycle and commands.py registration"
```

---

## Task 13: 更新 scheduler.py — 集成新的 TelegramBot

**Files:**
- Modify: `src/ai_trader/scheduler.py` — `_init_advisory()` 和 `stop()` 方法

**Step 1: 更新导入**

在 `scheduler.py` 顶部，将：
```python
from .advisory.telegram import TelegramNotifier
```
替换为：
```python
from .advisory.telegram import TelegramBot
```

如果顶部没有此导入（它在 `_init_advisory` 方法内导入），则修改 `_init_advisory` 方法内的导入。

**Step 2: 修改 `_init_advisory()` 方法**

在 `_init_advisory` 方法中，将 TelegramNotifier 的创建和 callback handler 启动替换为 TelegramBot：

将原来的（约 212-236 行）：
```python
notifier = TelegramNotifier(
    bot_token=config.telegram_bot_token,
    chat_id=config.telegram_chat_id,
)

self._notification_manager = NotificationManager(
    notifier=notifier, redis_client=self._redis,
)
await self._notification_manager.load_config()

self._advisory_service = AdvisoryService(
    engine=engine, trigger_manager=trigger_mgr,
    notifier=notifier, persistence=persistence,
)
...
if notifier.enabled and self._redis:
    self._advisory_tasks.append(asyncio.create_task(notifier.start_callback_handler(
        redis_client=self._redis,
        persistence=persistence,
    )))
```

替换为：
```python
# 初始化 Telegram Bot（统一管理 polling + 推送 + 命令）
self._telegram_bot = TelegramBot(
    bot_token=config.telegram_bot_token,
    chat_id=config.telegram_chat_id,
    redis=self._redis,
    db=self.db_manager,
    persistence=self.persistence_service,
    strategy_service=self._strategy_service if hasattr(self, '_strategy_service') else None,
    advisory_persistence=persistence,
)
notifier = self._telegram_bot.notifier

self._notification_manager = NotificationManager(
    notifier=notifier, redis_client=self._redis,
)
await self._notification_manager.load_config()

self._advisory_service = AdvisoryService(
    engine=engine, trigger_manager=trigger_mgr,
    notifier=notifier, persistence=persistence,
)
...
# 启动 Telegram Bot（替代原来的 start_callback_handler）
if self._telegram_bot.enabled:
    await self._telegram_bot.start()
```

移除原来的 `notifier.start_callback_handler` 相关 task 创建。

**Step 3: 修改 `stop()` 方法**

将原来的：
```python
if self._advisory_service:
    if hasattr(self._advisory_service, 'notifier') and self._advisory_service.notifier:
        await self._advisory_service.notifier.stop()
```

替换为：
```python
if hasattr(self, '_telegram_bot') and self._telegram_bot:
    await self._telegram_bot.stop()
```

**Step 4: 确保 `_strategy_service` 可用**

检查 scheduler 中是否有 `_strategy_service` 属性。如果当前策略服务是通过其他名称存储的，需要确保 `_init_advisory` 中能访问到。

Run: `grep -n "strategy_service\|_strategy_service\|StrategyPresetService" src/ai_trader/scheduler.py`

根据搜索结果调整属性名。

**Step 5: 验证**

Run: `python -c "import ast; ast.parse(open('src/ai_trader/scheduler.py').read()); print('OK')"`
Expected: OK

**Step 6: Commit**

```bash
git add src/ai_trader/scheduler.py
git commit -m "feat(telegram): integrate TelegramBot into scheduler replacing TelegramNotifier"
```

---

## Task 14: 更新其他调用方的导入路径

**Files:**
- Modify: `src/ai_trader/notification/manager.py` — 更新导入路径

**Step 1: 更新 notification/manager.py**

将：
```python
from ..advisory.telegram import TelegramNotifier
```
改为：
```python
from ..advisory.telegram import TelegramNotifier
```

由于 `telegram/__init__.py` 已经重新导出了 `TelegramNotifier`，导入路径 `from ..advisory.telegram import TelegramNotifier` 仍然有效（Python 包的 `__init__.py` 导出）。

但需确认旧的 `telegram.py` 文件删除后不会冲突：

**Step 2: 删除旧的 telegram.py**

确认所有导入都通过新的 `telegram/` 包工作后：

```bash
git rm src/ai_trader/advisory/telegram.py
```

注意：`telegram.py` 和 `telegram/` 不能同时存在（Python 会优先解析包目录）。由于我们在 Task 1 已创建了 `telegram/` 目录，旧的 `telegram.py` 实际上已被覆盖/忽略。需要显式删除。

**Step 3: 检查所有导入路径**

Run: `grep -rn "from.*advisory.*telegram" src/ai_trader/ --include="*.py" | grep -v __pycache__ | grep -v telegram/`

确保所有导入都能通过新包解析。

**Step 4: 验证**

Run: `python -c "from ai_trader.advisory.telegram import TelegramBot, TelegramNotifier; print('OK')"`

（需要在项目根目录或 src 目录下运行）

**Step 5: Commit**

```bash
git add -A
git commit -m "refactor(telegram): remove old telegram.py, update import paths"
```

---

## Task 15: 设置 BotCommand 菜单

**Files:**
- Modify: `src/ai_trader/advisory/telegram/bot.py` — 在 `start()` 中设置命令菜单

**Step 1: 在 bot.py 的 start() 方法中添加 set_my_commands**

在 `await self._app.updater.start_polling(...)` 之后添加：

```python
from telegram import BotCommand

# 设置 Bot 命令菜单（用户在输入框看到的 / 命令列表）
commands = [
    BotCommand("overview", "📊 账户概览"),
    BotCommand("positions", "📈 当前持仓"),
    BotCommand("decisions", "🧠 最近决策"),
    BotCommand("llm", "🤖 LLM 调用统计"),
    BotCommand("strategy", "📋 策略管理"),
    BotCommand("advisory", "💡 Advisory 建议"),
    BotCommand("trading", "⚙️ 交易控制"),
    BotCommand("menu", "显示主菜单"),
    BotCommand("help", "帮助"),
]
await self._app.bot.set_my_commands(commands)
```

**Step 2: 验证语法**

Run: `python -c "import ast; ast.parse(open('src/ai_trader/advisory/telegram/bot.py').read()); print('OK')"`
Expected: OK

**Step 3: Commit**

```bash
git add src/ai_trader/advisory/telegram/bot.py
git commit -m "feat(telegram): set BotCommand menu for command discovery"
```

---

## Task 16: 端到端集成验证

**Step 1: 检查所有文件是否存在**

Run:
```bash
ls -la src/ai_trader/advisory/telegram/
ls -la src/ai_trader/advisory/telegram/handlers/
```

Expected: 看到所有创建的文件。

**Step 2: 语法检查所有文件**

Run:
```bash
python -c "
import ast, pathlib
base = pathlib.Path('src/ai_trader/advisory/telegram')
errors = []
for f in base.rglob('*.py'):
    try:
        ast.parse(f.read_text())
    except SyntaxError as e:
        errors.append(f'{f}: {e}')
if errors:
    print('ERRORS:')
    for e in errors:
        print(e)
else:
    print(f'All {len(list(base.rglob(\"*.py\")))} files OK')
"
```

**Step 3: 导入检查**

Run:
```bash
cd src && python -c "from ai_trader.advisory.telegram import TelegramBot, TelegramNotifier; print('Import OK')" && cd ..
```

如果报错，根据错误修复导入路径。

**Step 4: 确认旧 telegram.py 已删除**

Run: `test -f src/ai_trader/advisory/telegram.py && echo "ERROR: old file exists" || echo "OK: old file removed"`

**Step 5: Commit**

```bash
git add -A
git commit -m "feat(telegram): complete telegram bot command system implementation"
```
