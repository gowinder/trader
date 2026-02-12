# TG 推送扩展实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 Telegram 推送从仅支持 Advisory 扩展为支持交易、决策、回测四大类通知，每个事件可独立开关，通过 Dashboard 配置。

**Architecture:** 新建 `notification` 模块（manager + formatter），在 scheduler 的关键调用点植入通知。配置存 Redis，Dashboard 新增通知设置页面。现有 TelegramNotifier 保持不变，NotificationManager 在上层封装。

**Tech Stack:** Python (asyncio, pydantic), Redis (config + pubsub), React + TypeScript (Dashboard)

---

## Task 1: 创建 NotificationManager 和 formatter 模块

**Files:**
- Create: `src/ai_trader/notification/__init__.py`
- Create: `src/ai_trader/notification/formatter.py`
- Create: `src/ai_trader/notification/manager.py`

**Step 1: 创建 `__init__.py`**

```python
from .manager import NotificationManager

__all__ = ["NotificationManager"]
```

**Step 2: 创建 `formatter.py` — 消息格式化**

```python
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


def format_trade_message(
    symbol: str,
    action: str,
    price: float,
    size: float,
    leverage: float,
    position_size_percent: float = 0,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None,
) -> str:
    emoji_action = ACTION_EMOJI.get(action, action)
    lines = [
        f"{emoji_action} | {symbol}",
        "━━━━━━━━━━━━━━━",
        f"💰 价格: {price:,.2f} USDT",
        f"📊 数量: {size}",
        f"🔧 杠杆: {int(leverage)}x",
    ]
    if position_size_percent > 0:
        lines.append(f"📐 仓位: {position_size_percent:.0f}%")
    if take_profit:
        lines.append(f"🎯 止盈: {take_profit:,.2f}")
    if stop_loss:
        lines.append(f"🛑 止损: {stop_loss:,.2f}")
    lines.append(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    return "\n".join(lines)


def format_stop_loss_take_profit_message(
    symbol: str,
    side: str,
    trigger_type: str,  # "stop_loss" or "take_profit"
    entry_price: float,
    trigger_price: float,
    pnl_percent: float,
) -> str:
    emoji = "🛑 止损触发" if trigger_type == "stop_loss" else "🎯 止盈触发"
    direction = "多头" if side == "long" else "空头"
    lines = [
        f"{emoji} | {symbol}",
        "━━━━━━━━━━━━━━━",
        f"📉 方向: {direction}",
        f"💰 入场: {entry_price:,.2f}",
        f"{'❌' if trigger_type == 'stop_loss' else '✅'} 触发: {trigger_price:,.2f}",
        f"📊 盈亏: {pnl_percent:+.2f}%",
        f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
    ]
    return "\n".join(lines)


def format_decision_message(
    symbol: str,
    action: str,
    confidence: float,
    reasoning: str,
    risk_note: str = "",
) -> str:
    if action == "hold":
        return f"🧠 AI决策 | {symbol} — ⏸️ 持仓不动 (信心度: {confidence:.0f})"

    emoji_action = ACTION_EMOJI.get(action, action)
    lines = [
        f"🧠 AI决策 | {symbol}",
        "━━━━━━━━━━━━━━━",
        f"📋 动作: {emoji_action}",
        f"🎯 信心度: {confidence:.0f}/100",
        f"💡 理由: {reasoning[:200]}",
    ]
    if risk_note:
        lines.append(f"⚠️ 风险: {risk_note[:100]}")
    lines.append(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
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
    lines = [
        f"📊 回测完成 | {symbol}",
        "━━━━━━━━━━━━━━━",
        f"📅 周期: {start_date} ~ {end_date}",
        f"💰 总盈亏: {return_pct:+.2f}%",
        f"🏆 胜率: {win_rate:.1f}%",
        f"📉 最大回撤: {max_drawdown_pct:.1f}%",
        f"📈 夏普比率: {sharpe_ratio:.2f}",
        f"🔄 交易次数: {total_trades}",
        f"⏰ 完成于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
    ]
    return "\n".join(lines)
```

**Step 3: 创建 `manager.py` — NotificationManager**

```python
"""通知管理器"""

import json
from typing import Optional

from ..advisory.telegram import TelegramNotifier
from ..utils.logger import logger
from . import formatter


DEFAULT_CONFIG = {
    "telegram_enabled": True,
    "trade": {
        "enabled": True,
        "open_long": True,
        "open_short": True,
        "close_long": True,
        "close_short": True,
        "add_reduce": True,
        "stop_loss_take_profit": True,
    },
    "decision": {
        "enabled": True,
        "action": True,
        "hold": False,
    },
    "backtest": {
        "enabled": True,
        "completed": True,
    },
    "advisory": {
        "enabled": True,
        "suggestion": True,
    },
}

# action -> event_type 映射
ACTION_EVENT_MAP = {
    "open_long": ("trade", "open_long"),
    "open_short": ("trade", "open_short"),
    "close_long": ("trade", "close_long"),
    "close_short": ("trade", "close_short"),
    "add_long": ("trade", "add_reduce"),
    "add_short": ("trade", "add_reduce"),
    "reduce_long": ("trade", "add_reduce"),
    "reduce_short": ("trade", "add_reduce"),
}


class NotificationManager:
    def __init__(self, notifier: TelegramNotifier, redis_client=None):
        self.notifier = notifier
        self._redis = redis_client
        self._config = dict(DEFAULT_CONFIG)

    async def load_config(self):
        """从 Redis 加载通知配置"""
        if not self._redis:
            return
        try:
            data = await self._redis.get("notification:config")
            if data:
                self._config = json.loads(data)
        except Exception as e:
            logger.warning(f"Failed to load notification config: {e}")

    def update_config(self, config: dict):
        """热更新配置"""
        self._config = config

    def is_enabled(self, category: str, event: str) -> bool:
        """检查某事件是否开启"""
        if not self._config.get("telegram_enabled", True):
            return False
        cat_config = self._config.get(category, {})
        if not cat_config.get("enabled", True):
            return False
        return cat_config.get(event, True)

    async def _send(self, text: str):
        """发送消息（内部方法）"""
        if not self.notifier.enabled:
            return
        try:
            await self.notifier._bot.send_message(
                chat_id=self.notifier.chat_id, text=text, parse_mode=None,
            )
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")

    async def notify_trade(
        self,
        symbol: str,
        action: str,
        price: float,
        size: float,
        leverage: float,
        position_size_percent: float = 0,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ):
        """发送交易通知"""
        mapping = ACTION_EVENT_MAP.get(action)
        if not mapping:
            return
        category, event = mapping
        if not self.is_enabled(category, event):
            return
        text = formatter.format_trade_message(
            symbol, action, price, size, leverage,
            position_size_percent, stop_loss, take_profit,
        )
        await self._send(text)

    async def notify_stop_loss_take_profit(
        self,
        symbol: str,
        side: str,
        trigger_type: str,
        entry_price: float,
        trigger_price: float,
        pnl_percent: float,
    ):
        """发送止损/止盈通知"""
        if not self.is_enabled("trade", "stop_loss_take_profit"):
            return
        text = formatter.format_stop_loss_take_profit_message(
            symbol, side, trigger_type, entry_price, trigger_price, pnl_percent,
        )
        await self._send(text)

    async def notify_decision(
        self,
        symbol: str,
        action: str,
        confidence: float,
        reasoning: str,
        risk_note: str = "",
    ):
        """发送决策通知"""
        event = "hold" if action == "hold" else "action"
        if not self.is_enabled("decision", event):
            return
        text = formatter.format_decision_message(
            symbol, action, confidence, reasoning, risk_note,
        )
        await self._send(text)

    async def notify_backtest(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        return_pct: float,
        win_rate: float,
        max_drawdown_pct: float,
        sharpe_ratio: float,
        total_trades: int,
    ):
        """发送回测完成通知"""
        if not self.is_enabled("backtest", "completed"):
            return
        text = formatter.format_backtest_message(
            symbol, start_date, end_date, return_pct,
            win_rate, max_drawdown_pct, sharpe_ratio, total_trades,
        )
        await self._send(text)

    def is_advisory_enabled(self) -> bool:
        """检查 advisory 通知是否开启"""
        return self.is_enabled("advisory", "suggestion")

    async def send_test_message(self):
        """发送测试消息"""
        await self._send("🔔 测试通知\n━━━━━━━━━━━━━━━\n✅ Telegram 通知连接正常！")
```

**Step 4: 提交**

```bash
git add src/ai_trader/notification/
git commit -m "feat: add NotificationManager and message formatter for TG notifications"
```

---

## Task 2: 在 Scheduler 中集成 NotificationManager

**Files:**
- Modify: `src/ai_trader/scheduler.py`

**Step 1: 添加 import 和初始化**

在 `scheduler.py` 顶部 import 区域（第 40 行之后）添加：
```python
from .notification import NotificationManager
```

在 `__init__` 方法中（第 85 行 `self._redis` 之后）添加：
```python
self._notification_manager: Optional[NotificationManager] = None
```

**Step 2: 在 `_init_advisory` 中初始化 NotificationManager**

在 `scheduler.py` 第 186 行（`notifier` 创建之后）添加 NotificationManager 初始化：
```python
# 初始化通知管理器
self._notification_manager = NotificationManager(
    notifier=notifier, redis_client=self._redis,
)
await self._notification_manager.load_config()
```

**Step 3: 在 `_persist_position_change` 中植入交易通知**

在 `scheduler.py` 第 827 行（开仓持久化成功后 `logger.info(...)` 之后）添加：
```python
# 发送开仓通知
if self._notification_manager:
    await self._notification_manager.notify_trade(
        symbol=symbol, action=action, price=price,
        size=size, leverage=leverage,
        stop_loss=decision.stop_loss_price if decision else None,
        take_profit=decision.take_profit_price if decision else None,
    )
```

在第 870 行（平仓持久化成功后 `logger.info(...)` 之后）添加：
```python
# 发送平仓通知
if self._notification_manager:
    await self._notification_manager.notify_trade(
        symbol=symbol, action=action, price=price, size=size, leverage=leverage,
    )
```

在第 919 行（reduce 持久化后 `logger.info(...)` 之后）添加：
```python
# 发送减仓通知
if self._notification_manager:
    await self._notification_manager.notify_trade(
        symbol=symbol, action=action, price=price, size=size, leverage=leverage,
    )
```

**Step 4: 在 `_run_cycle_for_symbol_impl` 中植入止损止盈通知**

在第 1360 行（`if sl_tp_action:` 块内，执行订单之前）添加止损止盈通知：
```python
# 发送止损/止盈通知
if self._notification_manager and position:
    is_sl = (side == "long" and market_data.current_price <= stop_loss_price) or \
            (side == "short" and market_data.current_price >= stop_loss_price)
    trigger_type = "stop_loss" if is_sl else "take_profit"
    entry_price = position.entry_price
    pnl_pct = ((market_data.current_price - entry_price) / entry_price) * 100
    if position.side.lower() == "short":
        pnl_pct = -pnl_pct
    await self._notification_manager.notify_stop_loss_take_profit(
        symbol=symbol,
        side=position.side.lower(),
        trigger_type=trigger_type,
        entry_price=entry_price,
        trigger_price=market_data.current_price,
        pnl_percent=pnl_pct,
    )
```

注意：需要在 `_check_stop_loss_take_profit` 返回前获取信息不太方便，更好的做法是在调用该方法之后、执行订单之前发送通知。具体位置在第 1360 行 `if sl_tp_action:` 块内。

**Step 5: 在 `_run_cycle_for_symbol_impl` 中植入决策通知**

在第 1403 行（决策完成后，执行之前）添加：
```python
# 发送决策通知
if self._notification_manager:
    await self._notification_manager.notify_decision(
        symbol=symbol,
        action=decision.action,
        confidence=decision.confidence,
        reasoning=decision.reasoning_zh or decision.reasoning,
    )
```

**Step 6: 在 `_run_backtest_task` 中植入回测通知**

在第 569 行（`logger.info(f"Backtest {task_id} completed...")` 之后）添加：
```python
# 发送回测完成通知
if self._notification_manager:
    await self._notification_manager.notify_backtest(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        return_pct=result.return_pct,
        win_rate=result.win_rate,
        max_drawdown_pct=result.max_drawdown_pct,
        sharpe_ratio=result.sharpe_ratio,
        total_trades=result.total_trades,
    )
```

**Step 7: 在 `_config_listener` 中添加通知配置监听**

在第 318 行 `pubsub.subscribe(...)` 调用中追加 `"notification:config:updated"` channel。

在第 376 行 `else:` 分支之前添加新的 elif：
```python
elif channel == "notification:config:updated":
    cfg = json.loads(message["data"])
    if self._notification_manager:
        self._notification_manager.update_config(cfg)
        logger.info("Notification config updated")
```

**Step 8: 提交**

```bash
git add src/ai_trader/scheduler.py
git commit -m "feat: integrate NotificationManager into scheduler for trade/decision/backtest notifications"
```

---

## Task 3: 创建 Dashboard 后端 API

**Files:**
- Create: `dashboard/app/routes/api.notification-settings.ts`

**Step 1: 创建 API 路由**

```typescript
import type { ActionFunctionArgs, LoaderFunctionArgs } from "react-router";
import { createClient } from "redis";

const NOTIFICATION_CONFIG_KEY = "notification:config";

const DEFAULT_CONFIG = {
  telegram_enabled: true,
  trade: {
    enabled: true,
    open_long: true,
    open_short: true,
    close_long: true,
    close_short: true,
    add_reduce: true,
    stop_loss_take_profit: true,
  },
  decision: {
    enabled: true,
    action: true,
    hold: false,
  },
  backtest: {
    enabled: true,
    completed: true,
  },
  advisory: {
    enabled: true,
    suggestion: true,
  },
};

async function getRedisClient() {
  const redisUrl = process.env.REDIS_URL || "redis://localhost:6379";
  const client = createClient({ url: redisUrl });
  await client.connect();
  return client;
}

export async function loader({ request }: LoaderFunctionArgs) {
  let client: Awaited<ReturnType<typeof getRedisClient>> | null = null;
  try {
    client = await getRedisClient();
    const data = await client.get(NOTIFICATION_CONFIG_KEY);
    return Response.json(data ? JSON.parse(data) : DEFAULT_CONFIG);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return Response.json({ error: message }, { status: 500 });
  } finally {
    if (client) { try { await client.disconnect(); } catch { /* ignore */ } }
  }
}

export async function action({ request }: ActionFunctionArgs) {
  if (request.method !== "POST" && request.method !== "PUT") {
    return Response.json({ error: "Method not allowed" }, { status: 405 });
  }

  let client: Awaited<ReturnType<typeof getRedisClient>> | null = null;
  try {
    const body = await request.json();
    client = await getRedisClient();

    // test 请求：发送测试消息
    if (body._action === "test") {
      await client.publish("notification:test", "test");
      return Response.json({ success: true, message: "Test message sent" });
    }

    // 保存配置
    await client.set(NOTIFICATION_CONFIG_KEY, JSON.stringify(body));
    await client.publish("notification:config:updated", JSON.stringify(body));
    return Response.json({ success: true });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return Response.json({ error: message }, { status: 500 });
  } finally {
    if (client) { try { await client.disconnect(); } catch { /* ignore */ } }
  }
}
```

**Step 2: 提交**

```bash
git add dashboard/app/routes/api.notification-settings.ts
git commit -m "feat: add notification settings API endpoint"
```

---

## Task 4: 创建 Dashboard 通知设置页面

**Files:**
- Create: `dashboard/app/routes/dashboard.notification-settings.tsx`
- Modify: `dashboard/app/components/layout/Sidebar.tsx`

**Step 1: 创建通知设置页面**

```tsx
import { useState, useEffect, useCallback } from "react";
import { Save, SendHorizonal } from "lucide-react";

interface NotificationConfig {
  telegram_enabled: boolean;
  trade: {
    enabled: boolean;
    open_long: boolean;
    open_short: boolean;
    close_long: boolean;
    close_short: boolean;
    add_reduce: boolean;
    stop_loss_take_profit: boolean;
  };
  decision: {
    enabled: boolean;
    action: boolean;
    hold: boolean;
  };
  backtest: {
    enabled: boolean;
    completed: boolean;
  };
  advisory: {
    enabled: boolean;
    suggestion: boolean;
  };
}

const DEFAULT_CONFIG: NotificationConfig = {
  telegram_enabled: true,
  trade: {
    enabled: true,
    open_long: true,
    open_short: true,
    close_long: true,
    close_short: true,
    add_reduce: true,
    stop_loss_take_profit: true,
  },
  decision: {
    enabled: true,
    action: true,
    hold: false,
  },
  backtest: {
    enabled: true,
    completed: true,
  },
  advisory: {
    enabled: true,
    suggestion: true,
  },
};

function Toggle({
  checked,
  onChange,
  disabled,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 ${
        checked ? "bg-primary" : "bg-input"
      }`}
    >
      <span
        className={`pointer-events-none block h-5 w-5 rounded-full bg-background shadow-lg ring-0 transition-transform ${
          checked ? "translate-x-5" : "translate-x-0"
        }`}
      />
    </button>
  );
}

function SwitchRow({
  label,
  checked,
  onChange,
  disabled,
  indent,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
  indent?: boolean;
}) {
  return (
    <div className={`flex items-center justify-between py-2 ${indent ? "pl-6" : ""}`}>
      <span className={`text-sm ${disabled ? "text-muted-foreground" : ""}`}>{label}</span>
      <Toggle checked={checked} onChange={onChange} disabled={disabled} />
    </div>
  );
}

export default function NotificationSettingsPage() {
  const [config, setConfig] = useState<NotificationConfig>(DEFAULT_CONFIG);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [toast, setToast] = useState<{ type: "success" | "error"; message: string } | null>(null);

  const showToast = useCallback((type: "success" | "error", message: string) => {
    setToast({ type, message });
  }, []);

  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(null), 3000);
      return () => clearTimeout(timer);
    }
  }, [toast]);

  useEffect(() => {
    fetch("/api/notification-settings")
      .then((r) => r.json())
      .then((data) => {
        if (!data.error) setConfig(data);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await fetch("/api/notification-settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      });
      const data = await res.json();
      if (data.success) {
        showToast("success", "保存成功");
      } else {
        showToast("error", data.error || "保存失败");
      }
    } catch {
      showToast("error", "保存失败");
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    try {
      const res = await fetch("/api/notification-settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ _action: "test" }),
      });
      const data = await res.json();
      if (data.success) {
        showToast("success", "测试消息已发送");
      } else {
        showToast("error", data.error || "发送失败");
      }
    } catch {
      showToast("error", "发送失败");
    } finally {
      setTesting(false);
    }
  };

  const updateCategory = <K extends keyof NotificationConfig>(
    category: K,
    field: string,
    value: boolean
  ) => {
    setConfig((prev) => ({
      ...prev,
      [category]:
        typeof prev[category] === "object"
          ? { ...(prev[category] as Record<string, unknown>), [field]: value }
          : value,
    }));
  };

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
      </div>
    );
  }

  const globalDisabled = !config.telegram_enabled;

  return (
    <div className="mx-auto max-w-2xl space-y-6 p-6">
      <h1 className="text-2xl font-bold">通知设置</h1>

      {toast && (
        <div
          className={`rounded-md p-3 text-sm ${
            toast.type === "success"
              ? "bg-green-500/10 text-green-500"
              : "bg-red-500/10 text-red-500"
          }`}
        >
          {toast.message}
        </div>
      )}

      {/* 全局开关 */}
      <div className="rounded-lg border bg-card p-4">
        <SwitchRow
          label="🔔 Telegram 推送"
          checked={config.telegram_enabled}
          onChange={(v) => setConfig((prev) => ({ ...prev, telegram_enabled: v }))}
        />
      </div>

      {/* 交易通知 */}
      <div className="rounded-lg border bg-card p-4 space-y-1">
        <SwitchRow
          label="📈 交易通知"
          checked={config.trade.enabled}
          onChange={(v) => updateCategory("trade", "enabled", v)}
          disabled={globalDisabled}
        />
        <SwitchRow label="开多" checked={config.trade.open_long} onChange={(v) => updateCategory("trade", "open_long", v)} disabled={globalDisabled || !config.trade.enabled} indent />
        <SwitchRow label="开空" checked={config.trade.open_short} onChange={(v) => updateCategory("trade", "open_short", v)} disabled={globalDisabled || !config.trade.enabled} indent />
        <SwitchRow label="平多" checked={config.trade.close_long} onChange={(v) => updateCategory("trade", "close_long", v)} disabled={globalDisabled || !config.trade.enabled} indent />
        <SwitchRow label="平空" checked={config.trade.close_short} onChange={(v) => updateCategory("trade", "close_short", v)} disabled={globalDisabled || !config.trade.enabled} indent />
        <SwitchRow label="加仓/减仓" checked={config.trade.add_reduce} onChange={(v) => updateCategory("trade", "add_reduce", v)} disabled={globalDisabled || !config.trade.enabled} indent />
        <SwitchRow label="止损/止盈触发" checked={config.trade.stop_loss_take_profit} onChange={(v) => updateCategory("trade", "stop_loss_take_profit", v)} disabled={globalDisabled || !config.trade.enabled} indent />
      </div>

      {/* 决策通知 */}
      <div className="rounded-lg border bg-card p-4 space-y-1">
        <SwitchRow
          label="🧠 决策通知"
          checked={config.decision.enabled}
          onChange={(v) => updateCategory("decision", "enabled", v)}
          disabled={globalDisabled}
        />
        <SwitchRow label="有动作的决策" checked={config.decision.action} onChange={(v) => updateCategory("decision", "action", v)} disabled={globalDisabled || !config.decision.enabled} indent />
        <SwitchRow label="持仓不动" checked={config.decision.hold} onChange={(v) => updateCategory("decision", "hold", v)} disabled={globalDisabled || !config.decision.enabled} indent />
      </div>

      {/* 回测通知 */}
      <div className="rounded-lg border bg-card p-4 space-y-1">
        <SwitchRow
          label="📊 回测通知"
          checked={config.backtest.enabled}
          onChange={(v) => updateCategory("backtest", "enabled", v)}
          disabled={globalDisabled}
        />
        <SwitchRow label="回测完成" checked={config.backtest.completed} onChange={(v) => updateCategory("backtest", "completed", v)} disabled={globalDisabled || !config.backtest.enabled} indent />
      </div>

      {/* Advisory 通知 */}
      <div className="rounded-lg border bg-card p-4 space-y-1">
        <SwitchRow
          label="🤖 Advisory 通知"
          checked={config.advisory.enabled}
          onChange={(v) => updateCategory("advisory", "enabled", v)}
          disabled={globalDisabled}
        />
        <SwitchRow label="AI 建议" checked={config.advisory.suggestion} onChange={(v) => updateCategory("advisory", "suggestion", v)} disabled={globalDisabled || !config.advisory.enabled} indent />
      </div>

      {/* 操作按钮 */}
      <div className="flex gap-3">
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          <Save className="h-4 w-4" />
          {saving ? "保存中..." : "保存设置"}
        </button>
        <button
          onClick={handleTest}
          disabled={testing}
          className="flex items-center gap-2 rounded-md border px-4 py-2 text-sm font-medium hover:bg-accent disabled:opacity-50"
        >
          <SendHorizonal className="h-4 w-4" />
          {testing ? "发送中..." : "发送测试消息"}
        </button>
      </div>
    </div>
  );
}
```

**Step 2: 在 Sidebar 添加菜单项**

在 `Sidebar.tsx` 的 import 中添加 `MessageSquare`：
```typescript
import { ..., MessageSquare } from "lucide-react";
```

在 `advisoryItems` 数组（第 36 行之后）添加：
```typescript
{ to: "/dashboard/notification-settings", icon: MessageSquare, label: "通知设置", hasBadge: false },
```

**Step 3: 提交**

```bash
git add dashboard/app/routes/dashboard.notification-settings.tsx dashboard/app/routes/api.notification-settings.ts dashboard/app/components/layout/Sidebar.tsx
git commit -m "feat: add notification settings page in dashboard"
```

---

## Task 5: 添加测试消息监听和 Advisory 开关集成

**Files:**
- Modify: `src/ai_trader/scheduler.py`
- Modify: `src/ai_trader/advisory/service.py`

**Step 1: 在 scheduler 中添加测试消息监听**

在 `_config_listener` 中的 `notification:config:updated` channel 旁边，也订阅 `notification:test`。

在处理 `notification:test` channel 时：
```python
elif channel == "notification:test":
    if self._notification_manager:
        await self._notification_manager.send_test_message()
        logger.info("Notification test message sent")
```

**Step 2: 在 Advisory service 中集成开关检查**

在 `advisory/service.py` 中，发送 advisory 通知之前检查 NotificationManager 的 advisory 开关。这需要 AdvisoryService 能访问 NotificationManager。

在 `scheduler.py` 的 `_init_advisory` 中，将 NotificationManager 传给 advisory service（可选），或者直接在 scheduler 层面拦截。

推荐做法：在 scheduler 中 advisory 触发后、调用 `notifier.send_advisory()` 之前检查。查看 `advisory/service.py` 中调用 `self.notifier.send_advisory()` 的位置，在 scheduler 层面通过 NotificationManager 包装。

具体做法：在 `AdvisoryService` 中增加一个 `notification_manager` 引用，在 `send_advisory` 前检查 `is_advisory_enabled()`。

**Step 3: 提交**

```bash
git add src/ai_trader/scheduler.py src/ai_trader/advisory/service.py
git commit -m "feat: add test message listener and advisory notification toggle"
```

---

## Task 6: 验证与测试

**Step 1: 验证 Python 代码无语法错误**

```bash
cd /Users/gowinder/code/gowinder/trader
python -c "from src.ai_trader.notification import NotificationManager; print('OK')"
```

**Step 2: 验证 Dashboard 构建**

```bash
cd /Users/gowinder/code/gowinder/trader/dashboard
npm run build
```

**Step 3: 最终提交**

```bash
git add -A
git commit -m "feat: complete TG notification expansion with trade/decision/backtest support"
```
