# 回测任务 Docker 容器化与 Dashboard 集成实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将回测任务作为独立服务加入 Docker Compose，并在 Dashboard 中提供配置界面和触发功能。

**Architecture:**
1. 创建 `backtest-runner` 容器，复用现有 Python 镜像，以定时任务或 API 触发方式运行回测
2. Dashboard 新增回测配置页面，支持设置回测参数（交易对、时间范围、频率等）
3. 通过 PostgreSQL 数据库实现配置持久化和任务状态同步

**Tech Stack:** Python 3.12, Docker Compose, React Router 7, PostgreSQL, Drizzle ORM

---

## Phase 1: 数据库 Schema 扩展

### Task 1.1: 添加回测配置表

**Files:**
- Modify: `dashboard/db/schema.ts`

**Step 1: 添加回测配置表定义**

在 `dashboard/db/schema.ts` 的回测相关表之后添加：

```typescript
// ==================== 回测调度配置 ====================

export const backtestScheduleConfig = pgTable("backtest_schedule_config", {
  id: uuid("id").primaryKey().defaultRandom(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),

  // 启用状态
  enabled: boolean("enabled").notNull().default(false),

  // 调度配置
  scheduleType: varchar("schedule_type", { length: 20 }).notNull().default("manual"),  // manual, daily, weekly
  scheduleCron: varchar("schedule_cron", { length: 50 }),  // cron 表达式 (可选)
  scheduleHour: smallint("schedule_hour").default(0),  // 每日执行小时 (0-23)
  scheduleDayOfWeek: smallint("schedule_day_of_week"),  // 每周执行日 (0-6, 0=周日)

  // 回测参数
  symbols: jsonb("symbols").notNull().default(["BTCUSDT"]),  // 交易对列表
  timeframe: varchar("timeframe", { length: 10 }).notNull().default("1h"),
  lookbackDays: smallint("lookback_days").notNull().default(30),  // 回测天数
  initialCapital: decimal("initial_capital", { precision: 20, scale: 2 }).notNull().default("10000"),

  // 策略配置
  enableFilters: boolean("enable_filters").notNull().default(true),
  strategies: jsonb("strategies").notNull().default(["trend_following"]),
});
```

**Step 2: 运行数据库迁移生成**

Run: `cd dashboard && npm run db:generate`
Expected: 生成新的迁移文件

**Step 3: 执行数据库迁移**

Run: `cd dashboard && npm run db:push`
Expected: 表创建成功

**Step 4: Commit**

```bash
git add dashboard/db/schema.ts dashboard/drizzle/
git commit -m "feat(db): add backtest_schedule_config table"
```

---

## Phase 2: 回测运行器服务

### Task 2.1: 创建回测运行器入口

**Files:**
- Create: `src/ai_trader/backtest/runner.py`

**Step 1: 创建回测运行器模块**

```python
"""回测调度运行器

独立进程，从数据库读取配置并执行定时回测任务。
"""

import asyncio
import os
from datetime import datetime, timedelta
from typing import Optional
import asyncpg

from ..backtest.engine import BacktestEngine, BacktestConfig
from ..strategies.market_classifier import MarketClassifier
from ..strategies.strategy_selector import StrategySelector
from ..strategies.signal_filter import SignalFilter
from ..persistence.database import DatabaseManager
from ..persistence.service import DecisionPersistenceService
from ..data.fetcher import CachedDataFetcher
from ..config import config
from ..utils.logger import logger


class BacktestRunner:
    """回测调度运行器"""

    def __init__(self):
        self.db_url = os.environ.get("DASHBOARD_DATABASE_URL", "")
        self.db: Optional[DatabaseManager] = None
        self.persistence: Optional[DecisionPersistenceService] = None
        self.running = False
        self.last_run_time: Optional[datetime] = None

    async def connect(self):
        """连接数据库"""
        if not self.db_url:
            raise ValueError("DASHBOARD_DATABASE_URL 未配置")
        self.db = DatabaseManager(self.db_url)
        await self.db.connect()
        self.persistence = DecisionPersistenceService(self.db)
        logger.info("回测运行器已连接数据库")

    async def close(self):
        """关闭连接"""
        if self.db:
            await self.db.close()
            logger.info("回测运行器已断开数据库")

    async def get_config(self) -> Optional[dict]:
        """从数据库获取回测配置"""
        row = await self.db.fetchrow(
            "SELECT * FROM backtest_schedule_config ORDER BY updated_at DESC LIMIT 1"
        )
        if not row:
            return None
        return dict(row)

    async def should_run(self, cfg: dict) -> bool:
        """判断是否应该运行回测"""
        if not cfg.get("enabled"):
            return False

        schedule_type = cfg.get("schedule_type", "manual")

        if schedule_type == "manual":
            # 手动模式：检查是否有待执行标记
            return cfg.get("pending_run", False)

        now = datetime.now()
        schedule_hour = cfg.get("schedule_hour", 0)

        if schedule_type == "daily":
            # 每日模式：检查是否到达执行时间且今天未执行
            if now.hour == schedule_hour:
                if self.last_run_time is None or self.last_run_time.date() < now.date():
                    return True

        elif schedule_type == "weekly":
            # 每周模式：检查是否到达执行日和时间
            schedule_day = cfg.get("schedule_day_of_week", 0)
            if now.weekday() == schedule_day and now.hour == schedule_hour:
                if self.last_run_time is None or (now - self.last_run_time).days >= 7:
                    return True

        return False

    async def run_backtest(self, cfg: dict) -> None:
        """执行单次回测"""
        symbols = cfg.get("symbols", ["BTCUSDT"])
        timeframe = cfg.get("timeframe", "1h")
        lookback_days = cfg.get("lookback_days", 30)
        initial_capital = float(cfg.get("initial_capital", 10000))
        enable_filters = cfg.get("enable_filters", True)

        end_date = datetime.now()
        start_date = end_date - timedelta(days=lookback_days)

        logger.info(f"开始回测: symbols={symbols}, range={start_date.date()} ~ {end_date.date()}")

        for symbol in symbols:
            try:
                await self._run_single_backtest(
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date,
                    timeframe=timeframe,
                    initial_capital=initial_capital,
                    enable_filters=enable_filters,
                )
            except Exception as e:
                logger.error(f"回测 {symbol} 失败: {e}")

        self.last_run_time = datetime.now()
        logger.info("回测完成")

    async def _run_single_backtest(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        timeframe: str,
        initial_capital: float,
        enable_filters: bool,
    ) -> None:
        """执行单个交易对的回测"""
        import pandas as pd

        # 获取历史数据
        fetcher = CachedDataFetcher(cache_dir="data/cache")
        symbol_formatted = f"{symbol[:-4]}/{symbol[-4:]}" if "/" not in symbol else symbol

        df = fetcher.get_data(
            symbol=symbol_formatted,
            start_date=start_date,
            end_date=end_date,
            timeframe=timeframe,
        )

        if len(df) < 50:
            logger.warning(f"{symbol} 数据不足，跳过")
            return

        # 生成信号
        signals = self._generate_signals(df, enable_filters)

        # 配置回测
        bt_config = BacktestConfig(
            initial_capital=initial_capital,
            commission_rate=0.0002,
            slippage_rate=0.001,
            max_position_size=0.5,
            enable_stop_loss=True,
            enable_take_profit=True,
        )

        # 执行回测
        engine = BacktestEngine(bt_config)
        result = engine.run(df, signals)

        # 保存到数据库
        backtest_id = await self.persistence.create_backtest(
            mode="single",
            symbol=symbol,
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d"),
            initial_capital=initial_capital,
        )

        # 保存交易记录
        for trade in engine.trades:
            await self.persistence.save_backtest_trade(
                backtest_id=backtest_id,
                symbol=symbol,
                side=trade.side,
                entry_time=trade.timestamp,
                entry_price=trade.entry_price,
                exit_time=trade.timestamp,
                exit_price=trade.exit_price,
                pnl=trade.pnl,
                pnl_percent=(trade.pnl / (trade.entry_price * trade.size) * 100)
                if trade.pnl and trade.entry_price and trade.size
                else None,
            )

        # 保存权益曲线
        step = max(1, len(engine.equity_curve) // 100)
        for i in range(0, len(engine.equity_curve), step):
            if i < len(df):
                ts = df.iloc[i]["timestamp"]
                if isinstance(ts, str):
                    ts = datetime.fromisoformat(ts)
                await self.persistence.save_backtest_equity(
                    backtest_id=backtest_id,
                    timestamp=ts,
                    total_equity=engine.equity_curve[i],
                )

        # 完成回测
        await self.persistence.complete_backtest(
            backtest_id=backtest_id,
            final_capital=result.final_capital,
            total_pnl=result.total_pnl,
            total_trades=result.total_trades,
            winning_trades=result.winning_trades,
            max_drawdown=result.max_drawdown,
            sharpe_ratio=result.sharpe_ratio,
        )

        logger.info(f"{symbol} 回测完成: PnL={result.total_pnl:.2f}, WinRate={result.win_rate:.1%}")

    def _generate_signals(self, df: pd.DataFrame, enable_filters: bool) -> pd.DataFrame:
        """生成交易信号"""
        import pandas as pd

        market_classifier = MarketClassifier()
        strategy_selector = StrategySelector(config.enabled_strategies)
        signal_filter = SignalFilter(min_interval_hours=6) if enable_filters else None

        signals = []

        for i in range(len(df)):
            window_df = df.iloc[max(0, i - 100) : i + 1]

            if len(window_df) < 50:
                signals.append({
                    "action": "hold",
                    "confidence": 0.0,
                    "entry_price": None,
                    "stop_loss": None,
                    "take_profit": None,
                })
                continue

            market_class = market_classifier.classify(window_df)
            signal = strategy_selector.aggregate_signals(window_df, market_class)

            action_map = {
                "long": "open_long",
                "short": "open_short",
                "close_long": "close_long",
                "close_short": "close_short",
                "hold": "hold",
            }
            action = action_map.get(signal.action.value, "hold")

            if enable_filters and action != "hold":
                current_time = df.iloc[i]["timestamp"]
                if signal.confidence < 0.55:
                    action = "hold"
                elif signal_filter:
                    allowed, _ = signal_filter.should_allow_signal(signal.action, current_time)
                    if not allowed:
                        action = "hold"
                    else:
                        signal_filter.record_trade(signal.action, current_time)

            signals.append({
                "action": action,
                "confidence": signal.confidence,
                "entry_price": signal.entry_price,
                "stop_loss": signal.stop_loss,
                "take_profit": signal.take_profit,
            })

        return pd.DataFrame(signals)

    async def run_loop(self, check_interval: int = 60):
        """主循环"""
        self.running = True
        logger.info(f"回测运行器启动，检查间隔: {check_interval}秒")

        while self.running:
            try:
                cfg = await self.get_config()
                if cfg and await self.should_run(cfg):
                    await self.run_backtest(cfg)
            except Exception as e:
                logger.error(f"回测运行器错误: {e}")

            await asyncio.sleep(check_interval)

    def stop(self):
        """停止运行"""
        self.running = False
        logger.info("回测运行器停止")


async def main():
    """入口函数"""
    runner = BacktestRunner()
    await runner.connect()

    try:
        await runner.run_loop(check_interval=60)
    finally:
        await runner.close()


if __name__ == "__main__":
    asyncio.run(main())
```

**Step 2: 验证模块导入**

Run: `cd /Users/gowinder/code/gowinder/trader && python -c "from ai_trader.backtest.runner import BacktestRunner; print('OK')"`
Expected: OK

**Step 3: Commit**

```bash
git add src/ai_trader/backtest/runner.py
git commit -m "feat(backtest): add scheduled backtest runner"
```

---

### Task 2.2: 创建 Docker 服务配置

**Files:**
- Modify: `docker-compose.example.yaml`

**Step 1: 添加 backtest-runner 服务**

在 `docker-compose.example.yaml` 中添加新服务：

```yaml
services:
  trader:
    build:
      context: .
      dockerfile: Dockerfile.trader
    container_name: ai-trader
    restart: unless-stopped
    env_file:
      - .env
    volumes:
      - ./src:/app/src:ro
      - ./trades:/app/trades
      - ./run_output:/app/run_output
      - ./logs:/app/logs
      - ./data:/app/data
    networks:
      - trader-network

  backtest-runner:
    build:
      context: .
      dockerfile: Dockerfile.trader
    container_name: ai-backtest-runner
    restart: unless-stopped
    env_file:
      - .env
    environment:
      - PYTHONPATH=/app/src
    command: ["python", "-m", "ai_trader.backtest.runner"]
    volumes:
      - ./src:/app/src:ro
      - ./data:/app/data
    depends_on:
      - dashboard
    networks:
      - trader-network

  dashboard:
    build:
      context: ./dashboard
      dockerfile: Dockerfile
    container_name: trader-dashboard
    restart: unless-stopped
    ports:
      - "3000:3000"
    env_file:
      - .env
    environment:
      - LLM_USAGE_DB=/app/data/llm_usage.db
      - TRADER_LOG_FILE=/app/logs/trading.log
    volumes:
      - ./data:/app/data:ro
      - ./logs:/app/logs:ro
    networks:
      - trader-network

networks:
  trader-network:
    driver: bridge
```

**Step 2: Commit**

```bash
git add docker-compose.example.yaml
git commit -m "feat(docker): add backtest-runner service"
```

---

## Phase 3: Dashboard 回测配置 API

### Task 3.1: 创建回测配置 API

**Files:**
- Create: `dashboard/app/routes/api.backtest-config.ts`

**Step 1: 创建 API 路由**

```typescript
import type { ActionFunctionArgs, LoaderFunctionArgs } from "react-router";
import { db } from "db";
import { backtestScheduleConfig } from "db/schema";
import { desc, eq } from "drizzle-orm";

// GET: 获取当前配置
export async function loader({ request }: LoaderFunctionArgs) {
  const config = await db
    .select()
    .from(backtestScheduleConfig)
    .orderBy(desc(backtestScheduleConfig.updatedAt))
    .limit(1);

  if (config.length === 0) {
    // 返回默认配置
    return Response.json({
      enabled: false,
      scheduleType: "manual",
      scheduleHour: 0,
      scheduleDayOfWeek: null,
      symbols: ["BTCUSDT"],
      timeframe: "1h",
      lookbackDays: 30,
      initialCapital: 10000,
      enableFilters: true,
      strategies: ["trend_following"],
    });
  }

  const cfg = config[0];
  return Response.json({
    id: cfg.id,
    enabled: cfg.enabled,
    scheduleType: cfg.scheduleType,
    scheduleHour: cfg.scheduleHour,
    scheduleDayOfWeek: cfg.scheduleDayOfWeek,
    symbols: cfg.symbols,
    timeframe: cfg.timeframe,
    lookbackDays: cfg.lookbackDays,
    initialCapital: cfg.initialCapital ? parseFloat(cfg.initialCapital) : 10000,
    enableFilters: cfg.enableFilters,
    strategies: cfg.strategies,
    updatedAt: cfg.updatedAt.toISOString(),
  });
}

// POST: 更新配置
export async function action({ request }: ActionFunctionArgs) {
  if (request.method !== "POST") {
    return Response.json({ error: "Method not allowed" }, { status: 405 });
  }

  const body = await request.json();

  // 验证必要字段
  const {
    enabled,
    scheduleType,
    scheduleHour,
    scheduleDayOfWeek,
    symbols,
    timeframe,
    lookbackDays,
    initialCapital,
    enableFilters,
    strategies,
  } = body;

  // 查找现有配置
  const existing = await db
    .select()
    .from(backtestScheduleConfig)
    .orderBy(desc(backtestScheduleConfig.updatedAt))
    .limit(1);

  if (existing.length > 0) {
    // 更新现有配置
    await db
      .update(backtestScheduleConfig)
      .set({
        enabled: enabled ?? false,
        scheduleType: scheduleType ?? "manual",
        scheduleHour: scheduleHour ?? 0,
        scheduleDayOfWeek: scheduleDayOfWeek,
        symbols: symbols ?? ["BTCUSDT"],
        timeframe: timeframe ?? "1h",
        lookbackDays: lookbackDays ?? 30,
        initialCapital: String(initialCapital ?? 10000),
        enableFilters: enableFilters ?? true,
        strategies: strategies ?? ["trend_following"],
        updatedAt: new Date(),
      })
      .where(eq(backtestScheduleConfig.id, existing[0].id));
  } else {
    // 创建新配置
    await db.insert(backtestScheduleConfig).values({
      enabled: enabled ?? false,
      scheduleType: scheduleType ?? "manual",
      scheduleHour: scheduleHour ?? 0,
      scheduleDayOfWeek: scheduleDayOfWeek,
      symbols: symbols ?? ["BTCUSDT"],
      timeframe: timeframe ?? "1h",
      lookbackDays: lookbackDays ?? 30,
      initialCapital: String(initialCapital ?? 10000),
      enableFilters: enableFilters ?? true,
      strategies: strategies ?? ["trend_following"],
    });
  }

  return Response.json({ success: true });
}
```

**Step 2: Commit**

```bash
git add dashboard/app/routes/api.backtest-config.ts
git commit -m "feat(api): add backtest config endpoint"
```

---

### Task 3.2: 创建触发回测 API

**Files:**
- Create: `dashboard/app/routes/api.backtest-trigger.ts`

**Step 1: 创建触发 API**

```typescript
import type { ActionFunctionArgs } from "react-router";
import { spawn } from "child_process";
import path from "path";

export async function action({ request }: ActionFunctionArgs) {
  if (request.method !== "POST") {
    return Response.json({ error: "Method not allowed" }, { status: 405 });
  }

  const body = await request.json();
  const {
    symbol = "BTCUSDT",
    startDate,
    endDate,
    interval = "1h",
    capital = 10000,
  } = body;

  // 验证日期
  if (!startDate || !endDate) {
    return Response.json({ error: "startDate and endDate are required" }, { status: 400 });
  }

  // 构建命令参数
  const args = [
    "-m", "ai_trader.backtest.runner",
    "--symbol", symbol,
    "--start", startDate,
    "--end", endDate,
    "--interval", interval,
    "--capital", String(capital),
    "--save-to-db",
  ];

  // 获取 Python 路径 (容器内或本地)
  const pythonPath = process.env.PYTHON_PATH || "python";

  try {
    // 异步启动回测进程
    const proc = spawn(pythonPath, args, {
      cwd: path.resolve(process.cwd(), ".."),
      detached: true,
      stdio: "ignore",
    });

    proc.unref();

    return Response.json({
      success: true,
      message: "Backtest started",
      pid: proc.pid,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return Response.json({ error: message }, { status: 500 });
  }
}
```

**Step 2: Commit**

```bash
git add dashboard/app/routes/api.backtest-trigger.ts
git commit -m "feat(api): add backtest trigger endpoint"
```

---

## Phase 4: Dashboard 回测配置页面

### Task 4.1: 创建回测设置页面

**Files:**
- Create: `dashboard/app/routes/dashboard.backtest-settings.tsx`

**Step 1: 创建设置页面组件**

```typescript
import { useEffect, useState } from "react";
import { useFetcher } from "react-router";
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card";
import { Button } from "~/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select";
import { Label } from "~/components/ui/label";
import { Settings, Play, Clock, Calendar } from "lucide-react";

interface BacktestConfig {
  id?: string;
  enabled: boolean;
  scheduleType: "manual" | "daily" | "weekly";
  scheduleHour: number;
  scheduleDayOfWeek: number | null;
  symbols: string[];
  timeframe: string;
  lookbackDays: number;
  initialCapital: number;
  enableFilters: boolean;
  strategies: string[];
  updatedAt?: string;
}

const SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"];
const TIMEFRAMES = ["15m", "1h", "4h", "1d"];
const STRATEGIES = ["trend_following", "mean_reversion", "breakout"];

export default function BacktestSettingsPage() {
  const fetcher = useFetcher();
  const [config, setConfig] = useState<BacktestConfig>({
    enabled: false,
    scheduleType: "manual",
    scheduleHour: 0,
    scheduleDayOfWeek: null,
    symbols: ["BTCUSDT"],
    timeframe: "1h",
    lookbackDays: 30,
    initialCapital: 10000,
    enableFilters: true,
    strategies: ["trend_following"],
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // 加载配置
  useEffect(() => {
    fetch("/api/backtest-config")
      .then((res) => res.json())
      .then((data) => {
        setConfig(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  // 保存配置
  const saveConfig = async () => {
    setSaving(true);
    try {
      await fetch("/api/backtest-config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      });
    } finally {
      setSaving(false);
    }
  };

  // 立即运行回测
  const runNow = async () => {
    const endDate = new Date().toISOString().split("T")[0];
    const startDate = new Date(Date.now() - config.lookbackDays * 24 * 60 * 60 * 1000)
      .toISOString()
      .split("T")[0];

    for (const symbol of config.symbols) {
      await fetch("/api/backtest-trigger", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol,
          startDate,
          endDate,
          interval: config.timeframe,
          capital: config.initialCapital,
        }),
      });
    }
  };

  if (loading) {
    return <div className="p-8 text-center text-muted-foreground">加载中...</div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Settings className="h-6 w-6" />
          回测设置
        </h1>
        <div className="flex gap-2">
          <Button variant="outline" onClick={runNow}>
            <Play className="mr-2 h-4 w-4" />
            立即运行
          </Button>
          <Button onClick={saveConfig} disabled={saving}>
            {saving ? "保存中..." : "保存配置"}
          </Button>
        </div>
      </div>

      {/* 调度配置 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Clock className="h-4 w-4" />
            调度配置
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-4">
            <Label>启用自动回测</Label>
            <input
              type="checkbox"
              checked={config.enabled}
              onChange={(e) => setConfig({ ...config, enabled: e.target.checked })}
              className="h-4 w-4"
            />
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            <div>
              <Label>调度类型</Label>
              <Select
                value={config.scheduleType}
                onValueChange={(v) =>
                  setConfig({ ...config, scheduleType: v as BacktestConfig["scheduleType"] })
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="manual">手动</SelectItem>
                  <SelectItem value="daily">每日</SelectItem>
                  <SelectItem value="weekly">每周</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {config.scheduleType !== "manual" && (
              <div>
                <Label>执行时间 (小时)</Label>
                <Select
                  value={String(config.scheduleHour)}
                  onValueChange={(v) => setConfig({ ...config, scheduleHour: parseInt(v) })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {Array.from({ length: 24 }, (_, i) => (
                      <SelectItem key={i} value={String(i)}>
                        {String(i).padStart(2, "0")}:00
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            {config.scheduleType === "weekly" && (
              <div>
                <Label>执行日</Label>
                <Select
                  value={String(config.scheduleDayOfWeek ?? 0)}
                  onValueChange={(v) => setConfig({ ...config, scheduleDayOfWeek: parseInt(v) })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="0">周日</SelectItem>
                    <SelectItem value="1">周一</SelectItem>
                    <SelectItem value="2">周二</SelectItem>
                    <SelectItem value="3">周三</SelectItem>
                    <SelectItem value="4">周四</SelectItem>
                    <SelectItem value="5">周五</SelectItem>
                    <SelectItem value="6">周六</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* 回测参数 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Calendar className="h-4 w-4" />
            回测参数
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <div>
              <Label>交易对</Label>
              <Select
                value={config.symbols[0]}
                onValueChange={(v) => setConfig({ ...config, symbols: [v] })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {SYMBOLS.map((s) => (
                    <SelectItem key={s} value={s}>
                      {s}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div>
              <Label>时间周期</Label>
              <Select
                value={config.timeframe}
                onValueChange={(v) => setConfig({ ...config, timeframe: v })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TIMEFRAMES.map((tf) => (
                    <SelectItem key={tf} value={tf}>
                      {tf}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div>
              <Label>回测天数</Label>
              <Select
                value={String(config.lookbackDays)}
                onValueChange={(v) => setConfig({ ...config, lookbackDays: parseInt(v) })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="7">7 天</SelectItem>
                  <SelectItem value="14">14 天</SelectItem>
                  <SelectItem value="30">30 天</SelectItem>
                  <SelectItem value="60">60 天</SelectItem>
                  <SelectItem value="90">90 天</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div>
              <Label>初始资金 (USDT)</Label>
              <Select
                value={String(config.initialCapital)}
                onValueChange={(v) => setConfig({ ...config, initialCapital: parseInt(v) })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="1000">1,000</SelectItem>
                  <SelectItem value="5000">5,000</SelectItem>
                  <SelectItem value="10000">10,000</SelectItem>
                  <SelectItem value="50000">50,000</SelectItem>
                  <SelectItem value="100000">100,000</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <Label>启用信号过滤</Label>
            <input
              type="checkbox"
              checked={config.enableFilters}
              onChange={(e) => setConfig({ ...config, enableFilters: e.target.checked })}
              className="h-4 w-4"
            />
          </div>
        </CardContent>
      </Card>

      {/* 配置信息 */}
      {config.updatedAt && (
        <div className="text-sm text-muted-foreground">
          最后更新: {new Date(config.updatedAt).toLocaleString("zh-CN")}
        </div>
      )}
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add dashboard/app/routes/dashboard.backtest-settings.tsx
git commit -m "feat(dashboard): add backtest settings page"
```

---

### Task 4.2: 添加导航链接

**Files:**
- Modify: `dashboard/app/components/layout/Sidebar.tsx` (或类似侧边栏组件)

**Step 1: 查找并更新导航**

需要在侧边栏添加 "回测设置" 链接，指向 `/dashboard/backtest-settings`

**Step 2: Commit**

```bash
git add dashboard/app/components/
git commit -m "feat(dashboard): add backtest settings to navigation"
```

---

## Phase 5: 集成测试

### Task 5.1: 测试数据库配置

**Step 1: 启动 Dashboard 开发服务器**

Run: `cd dashboard && npm run dev`

**Step 2: 访问回测设置页面**

访问 `http://localhost:3000/dashboard/backtest-settings`
Expected: 页面正常加载，显示默认配置

**Step 3: 测试保存配置**

修改配置并点击保存，刷新页面确认配置已保存

---

### Task 5.2: 测试 Docker 部署

**Step 1: 构建镜像**

Run: `docker compose -f docker-compose.example.yaml build`
Expected: 所有镜像构建成功

**Step 2: 启动服务**

Run: `docker compose -f docker-compose.example.yaml up -d`
Expected: 三个容器启动成功 (trader, backtest-runner, dashboard)

**Step 3: 验证回测运行器**

Run: `docker logs ai-backtest-runner`
Expected: 显示 "回测运行器启动" 日志

**Step 4: Commit**

```bash
git add .
git commit -m "feat: complete backtest docker integration"
```

---

## 总结

### 新增文件
- `dashboard/db/schema.ts` - 添加 `backtest_schedule_config` 表
- `src/ai_trader/backtest/runner.py` - 回测调度运行器
- `dashboard/app/routes/api.backtest-config.ts` - 配置 API
- `dashboard/app/routes/api.backtest-trigger.ts` - 触发 API
- `dashboard/app/routes/dashboard.backtest-settings.tsx` - 设置页面

### 修改文件
- `docker-compose.example.yaml` - 添加 backtest-runner 服务

### 环境变量
确保 `.env` 中配置：
```
DASHBOARD_DATABASE_URL=postgresql://...
```
