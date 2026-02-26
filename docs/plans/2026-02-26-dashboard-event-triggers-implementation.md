# Dashboard 事件触发管理页面实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为事件驱动 LLM 触发机制添加 Dashboard 管理界面（触发记录查看 + 事件配置编辑 + 策略映射展示）

**Architecture:** Drizzle schema 新增 `event_trigger_logs` 表，Python 端写入事件记录，Dashboard 通过 3 个 API 路由读写数据，单页 + 3 Tabs 展示

**Tech Stack:** React Router, Drizzle ORM (PostgreSQL), Redis, Tailwind CSS, Lucide Icons, psycopg2 (Python 端)

---

### Task 1: Drizzle Schema — 新增 event_trigger_logs 表

**Files:**
- Modify: `dashboard/db/schema.ts`

**步骤:**

在 schema.ts 的 `// ==================== 系统管理 ====================` 之前，添加事件触发记录表：

```typescript
// ==================== 事件触发记录 ====================

export const eventTriggerLogs = pgTable(
  "event_trigger_logs",
  {
    id: serial("id").primaryKey(),
    symbol: varchar("symbol", { length: 20 }).notNull(),
    eventType: varchar("event_type", { length: 50 }).notNull(),
    severity: varchar("severity", { length: 10 }).notNull(),
    description: text("description").notNull(),
    keyData: jsonb("key_data"),
    triggeredAt: timestamp("triggered_at", { withTimezone: true }).notNull(),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => ({
    symbolTimeIdx: index("idx_event_trigger_symbol_time").on(table.symbol, table.triggeredAt),
    eventTypeIdx: index("idx_event_trigger_type").on(table.eventType),
  })
);
```

**验证:** `cd dashboard && npm run db:push` 成功创建表

---

### Task 2: Python 端 — 事件触发后写入数据库

**Files:**
- Modify: `src/ai_trader/events/detector.py`

**步骤:**

在 `EventDetector.scan()` 方法中，检测到事件后批量写入 PostgreSQL。使用 `DATABASE_URL` 环境变量连接。

在 `detector.py` 中添加 `_persist_events` 方法：

```python
def _persist_events(self, events: list[TriggerEvent]) -> None:
    """将触发事件写入 PostgreSQL event_trigger_logs 表。"""
    import os
    try:
        import psycopg2
    except ImportError:
        logger.warning("psycopg2 未安装，跳过事件持久化")
        return

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return

    try:
        conn = psycopg2.connect(database_url)
        cur = conn.cursor()
        import json
        for event in events:
            cur.execute(
                """INSERT INTO event_trigger_logs
                   (symbol, event_type, severity, description, key_data, triggered_at)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (
                    getattr(event, '_symbol', 'UNKNOWN'),
                    event.event_type,
                    event.severity,
                    event.description,
                    json.dumps(event.key_data),
                    event.timestamp,
                ),
            )
        conn.commit()
        cur.close()
        conn.close()
    except Exception:
        logger.exception("事件持久化写入失败")
```

需要在 `scan()` 方法签名中增加 `symbol` 参数，用于标识交易对。在 `scan()` 末尾调用 `self._persist_events(triggered)`，并把 symbol 信息挂在 event 上。

**注意:** 检查 `scheduler.py` 中 `scan()` 的调用处，确保传入 `symbol`。如果 `scan()` 当前没有 `symbol` 参数，需要加上并更新调用方。

**验证:** 在 Docker 中运行，触发事件后查询 `SELECT * FROM event_trigger_logs` 有记录

---

### Task 3: API 路由 — 触发记录查询

**Files:**
- Create: `dashboard/app/routes/api.event-triggers.logs.ts`

**步骤:**

参考 `dashboard.decisions.tsx` 的 loader 分页模式：

```typescript
import type { LoaderFunctionArgs } from "react-router";
import { db } from "~/db/client";
import { eventTriggerLogs } from "~/db/schema";
import { desc, eq, and, gte, lte, count, sql } from "drizzle-orm";

export async function loader({ request }: LoaderFunctionArgs) {
  const url = new URL(request.url);
  const symbol = url.searchParams.get("symbol");
  const eventType = url.searchParams.get("type");
  const severity = url.searchParams.get("severity");
  const from = url.searchParams.get("from");
  const to = url.searchParams.get("to");
  const page = parseInt(url.searchParams.get("page") || "1");
  const limit = parseInt(url.searchParams.get("limit") || "20");
  const offset = (page - 1) * limit;

  const conditions = [];
  if (symbol) conditions.push(eq(eventTriggerLogs.symbol, symbol));
  if (eventType) conditions.push(eq(eventTriggerLogs.eventType, eventType));
  if (severity) conditions.push(eq(eventTriggerLogs.severity, severity));
  if (from) conditions.push(gte(eventTriggerLogs.triggeredAt, new Date(from)));
  if (to) conditions.push(lte(eventTriggerLogs.triggeredAt, new Date(to)));

  const whereClause = conditions.length > 0 ? and(...conditions) : undefined;

  const [logs, totalResult] = await Promise.all([
    db.select().from(eventTriggerLogs)
      .where(whereClause)
      .orderBy(desc(eventTriggerLogs.triggeredAt))
      .limit(limit).offset(offset),
    db.select({ count: count() }).from(eventTriggerLogs).where(whereClause),
  ]);

  return Response.json({
    logs,
    total: totalResult[0]?.count ?? 0,
    page,
    limit,
  });
}
```

**验证:** `curl http://localhost:3500/api/event-triggers/logs` 返回 JSON

---

### Task 4: API 路由 — 事件配置读写 + 策略映射

**Files:**
- Create: `dashboard/app/routes/api.event-triggers.config.ts`
- Create: `dashboard/app/routes/api.event-triggers.mapping.ts`

**步骤:**

**api.event-triggers.config.ts** — 参考 `api.advisory-settings.ts` 的 Redis 模式：

```typescript
// loader: GET — 读取 Redis trading:event_trigger_config
// action: POST — 写入 Redis + publish trading:event_trigger_config:updated
```

**api.event-triggers.mapping.ts** — 返回硬编码的 STRATEGY_EVENT_DEFAULTS：

```typescript
// loader: GET — 返回策略-事件映射 JSON
const STRATEGY_EVENT_DEFAULTS = {
  trend_following: ["price_surge", "macd_cross", "market_state_change", "position_pnl"],
  mean_reversion: ["price_surge", "rsi_extreme", "bollinger_break", "market_state_change", "position_pnl"],
  breakout: ["price_surge", "volume_spike", "bollinger_break", "market_state_change", "position_pnl"],
};
```

**验证:** API 端点可正常读写

---

### Task 5: Dashboard 页面 — 主页面 + 触发记录 Tab

**Files:**
- Create: `dashboard/app/routes/dashboard.event-triggers.tsx`

**步骤:**

创建主页面框架，包含 Tabs 组件和触发记录 Tab：

- 页面标题 "事件触发管理"
- 3 个 Tab: "触发记录" / "事件配置" / "策略映射"
- 触发记录 Tab:
  - 筛选栏：币种 Select + 事件类型 Select + 严重程度 Select + 时间范围 Select
  - 分页表格：时间 | 币种 | 事件类型 | 严重程度(彩色标签) | 描述 | 关键数据
  - 底部分页控件

参考 `dashboard.decisions.tsx` 的 useSearchParams + fetch 模式。

**验证:** 浏览器访问 `/dashboard/event-triggers`，触发记录 Tab 正常展示

---

### Task 6: Dashboard 页面 — 事件配置 Tab

**Files:**
- Modify: `dashboard/app/routes/dashboard.event-triggers.tsx`

**步骤:**

在同一页面文件中添加事件配置 Tab：

- 全局配置区：总开关 (Switch) + 扫描间隔/全局冷却/单事件冷却 (Input) + 重置定时器 (Switch)
- 7 个事件卡片（2~3 列网格）：每个卡片包含开关 + 特定参数输入
- 即时生效：Switch 切换和 Input 修改（debounce 500ms）后立即 POST /api/event-triggers/config
- 成功/失败 Toast 提示

参考 `dashboard.advisory-settings.tsx` 的即时保存模式。

**验证:** 修改配置后 Redis 中 `trading:event_trigger_config` 值更新

---

### Task 7: Dashboard 页面 — 策略映射 Tab + 侧边栏入口

**Files:**
- Modify: `dashboard/app/routes/dashboard.event-triggers.tsx`
- Modify: `dashboard/app/components/layout/Sidebar.tsx`

**步骤:**

**策略映射 Tab:**
- 只读矩阵表格：行=策略，列=7 个事件类型
- 勾选标记用绿色 ✓，空白留空
- 表格上方说明文字

**侧边栏:**
- 在 `Sidebar.tsx` 的 `navItems` 数组中，`decisions` 之后添加：
  ```typescript
  { to: "/dashboard/event-triggers", icon: Zap, label: "事件触发" },
  ```
- import `Zap` from lucide-react

**验证:** 侧边栏显示"事件触发"入口，点击进入页面，策略映射 Tab 正常展示
