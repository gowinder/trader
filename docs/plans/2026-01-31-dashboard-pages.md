# Dashboard 四页面开发实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现 Dashboard 的仓位、分析、回测、图表四个页面

**Architecture:** 使用 React Router 7 的 loader 模式从 PostgreSQL 获取数据，Recharts/Lightweight Charts 渲染图表，遵循现有 dashboard._index.tsx 的代码风格

**Tech Stack:** React 19, React Router 7, Drizzle ORM, Recharts, Lightweight Charts, Tailwind CSS, shadcn/ui

---

## Task 1: 仓位页面 (Positions)

**Files:**
- Modify: `dashboard/app/routes/dashboard.positions.tsx`

**Step 1: 实现 loader 函数**

```typescript
import type { Route } from "./+types/dashboard.positions";
import { db } from "db";
import { positionHistory } from "db/schema";
import { desc, eq, sql, isNull, isNotNull } from "drizzle-orm";

export async function loader(_args: Route.LoaderArgs) {
  // 当前持仓（未平仓）
  const openPositions = await db
    .select()
    .from(positionHistory)
    .where(eq(positionHistory.status, "open"))
    .orderBy(desc(positionHistory.entryTime));

  // 历史持仓（已平仓）
  const closedPositions = await db
    .select()
    .from(positionHistory)
    .where(eq(positionHistory.status, "closed"))
    .orderBy(desc(positionHistory.exitTime))
    .limit(50);

  // 统计数据
  const statsResult = await db
    .select({
      totalTrades: sql<number>`count(*)`,
      winningTrades: sql<number>`count(*) FILTER (WHERE ${positionHistory.realizedPnl}::numeric > 0)`,
      totalPnl: sql<number>`COALESCE(SUM(${positionHistory.realizedPnl}::numeric), 0)`,
      avgPnlPercent: sql<number>`COALESCE(AVG(${positionHistory.pnlPercent}::numeric), 0)`,
    })
    .from(positionHistory)
    .where(eq(positionHistory.status, "closed"));

  const stats = statsResult[0] || { totalTrades: 0, winningTrades: 0, totalPnl: 0, avgPnlPercent: 0 };

  return {
    openPositions: openPositions.map(p => ({
      ...p,
      entryTime: p.entryTime.toISOString(),
      exitTime: p.exitTime?.toISOString(),
      entryPrice: Number(p.entryPrice),
      exitPrice: p.exitPrice ? Number(p.exitPrice) : null,
      entrySize: Number(p.entrySize),
      leverage: p.leverage ? Number(p.leverage) : null,
      realizedPnl: p.realizedPnl ? Number(p.realizedPnl) : null,
      pnlPercent: p.pnlPercent ? Number(p.pnlPercent) : null,
    })),
    closedPositions: closedPositions.map(p => ({
      ...p,
      entryTime: p.entryTime.toISOString(),
      exitTime: p.exitTime?.toISOString(),
      entryPrice: Number(p.entryPrice),
      exitPrice: p.exitPrice ? Number(p.exitPrice) : null,
      entrySize: Number(p.entrySize),
      leverage: p.leverage ? Number(p.leverage) : null,
      realizedPnl: p.realizedPnl ? Number(p.realizedPnl) : null,
      pnlPercent: p.pnlPercent ? Number(p.pnlPercent) : null,
    })),
    stats: {
      totalTrades: Number(stats.totalTrades),
      winningTrades: Number(stats.winningTrades),
      winRate: stats.totalTrades > 0 ? Math.round((Number(stats.winningTrades) / Number(stats.totalTrades)) * 100) : 0,
      totalPnl: Number(stats.totalPnl),
      avgPnlPercent: Number(stats.avgPnlPercent),
    },
  };
}
```

**Step 2: 实现组件**

```typescript
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card";
import { StatCard } from "~/components/common/StatCard";
import { formatUSD, cn } from "~/lib/utils";
import { TrendingUp, TrendingDown, Target, Percent, History } from "lucide-react";

export default function PositionsPage({ loaderData }: Route.ComponentProps) {
  const { openPositions, closedPositions, stats } = loaderData;

  return (
    <div className="space-y-6">
      {/* 统计卡片 */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard label="总交易数" value={`${stats.totalTrades}`} icon={History} />
        <StatCard label="胜率" value={`${stats.winRate}%`} icon={Target} />
        <StatCard
          label="总盈亏"
          value={formatUSD(stats.totalPnl)}
          variant={stats.totalPnl >= 0 ? "profit" : "loss"}
          icon={stats.totalPnl >= 0 ? TrendingUp : TrendingDown}
        />
        <StatCard
          label="平均收益率"
          value={`${stats.avgPnlPercent.toFixed(2)}%`}
          variant={stats.avgPnlPercent >= 0 ? "profit" : "loss"}
          icon={Percent}
        />
      </div>

      {/* 当前持仓 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">当前持仓</CardTitle>
        </CardHeader>
        <CardContent>
          {openPositions.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="pb-2">交易对</th>
                    <th className="pb-2">方向</th>
                    <th className="pb-2">入场价</th>
                    <th className="pb-2">数量</th>
                    <th className="pb-2">杠杆</th>
                    <th className="pb-2">入场时间</th>
                  </tr>
                </thead>
                <tbody>
                  {openPositions.map((p) => (
                    <tr key={p.id} className="border-b">
                      <td className="py-2 font-medium">{p.symbol}</td>
                      <td className={cn("py-2", p.side === "long" ? "text-profit" : "text-loss")}>
                        {p.side === "long" ? "多" : "空"}
                      </td>
                      <td className="py-2">{p.entryPrice.toFixed(2)}</td>
                      <td className="py-2">{p.entrySize}</td>
                      <td className="py-2">{p.leverage}x</td>
                      <td className="py-2 text-muted-foreground">{formatTime(p.entryTime)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="flex h-32 items-center justify-center text-muted-foreground">
              暂无持仓
            </div>
          )}
        </CardContent>
      </Card>

      {/* 历史持仓 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">历史持仓</CardTitle>
        </CardHeader>
        <CardContent>
          {closedPositions.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="pb-2">交易对</th>
                    <th className="pb-2">方向</th>
                    <th className="pb-2">入场价</th>
                    <th className="pb-2">出场价</th>
                    <th className="pb-2">盈亏</th>
                    <th className="pb-2">收益率</th>
                    <th className="pb-2">平仓时间</th>
                  </tr>
                </thead>
                <tbody>
                  {closedPositions.map((p) => (
                    <tr key={p.id} className="border-b">
                      <td className="py-2 font-medium">{p.symbol}</td>
                      <td className={cn("py-2", p.side === "long" ? "text-profit" : "text-loss")}>
                        {p.side === "long" ? "多" : "空"}
                      </td>
                      <td className="py-2">{p.entryPrice.toFixed(2)}</td>
                      <td className="py-2">{p.exitPrice?.toFixed(2) ?? "-"}</td>
                      <td className={cn("py-2", (p.realizedPnl ?? 0) >= 0 ? "text-profit" : "text-loss")}>
                        {formatUSD(p.realizedPnl ?? 0)}
                      </td>
                      <td className={cn("py-2", (p.pnlPercent ?? 0) >= 0 ? "text-profit" : "text-loss")}>
                        {p.pnlPercent?.toFixed(2) ?? 0}%
                      </td>
                      <td className="py-2 text-muted-foreground">{formatTime(p.exitTime!)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="flex h-32 items-center justify-center text-muted-foreground">
              暂无历史记录
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}
```

**Step 3: 验证**

Run: `docker compose up -d --build dashboard`

访问 http://localhost:3000/dashboard/positions 确认页面正常加载

**Step 4: Commit**

```bash
git add dashboard/app/routes/dashboard.positions.tsx
git commit -m "feat(dashboard): implement positions page with open/closed positions"
```

---

## Task 2: 分析页面 (Analytics)

**Files:**
- Modify: `dashboard/app/routes/dashboard.analytics.tsx`

**Step 1: 实现 loader 函数**

```typescript
import type { Route } from "./+types/dashboard.analytics";
import { db } from "db";
import { positionHistory, dailyStats, decisions } from "db/schema";
import { desc, sql, gte, eq } from "drizzle-orm";

export async function loader(_args: Route.LoaderArgs) {
  const thirtyDaysAgo = new Date();
  thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);

  // 总体统计
  const overallStats = await db
    .select({
      totalTrades: sql<number>`count(*)`,
      winningTrades: sql<number>`count(*) FILTER (WHERE ${positionHistory.realizedPnl}::numeric > 0)`,
      losingTrades: sql<number>`count(*) FILTER (WHERE ${positionHistory.realizedPnl}::numeric < 0)`,
      totalPnl: sql<number>`COALESCE(SUM(${positionHistory.realizedPnl}::numeric), 0)`,
      avgWin: sql<number>`COALESCE(AVG(${positionHistory.realizedPnl}::numeric) FILTER (WHERE ${positionHistory.realizedPnl}::numeric > 0), 0)`,
      avgLoss: sql<number>`COALESCE(AVG(${positionHistory.realizedPnl}::numeric) FILTER (WHERE ${positionHistory.realizedPnl}::numeric < 0), 0)`,
      maxWin: sql<number>`COALESCE(MAX(${positionHistory.realizedPnl}::numeric), 0)`,
      maxLoss: sql<number>`COALESCE(MIN(${positionHistory.realizedPnl}::numeric), 0)`,
    })
    .from(positionHistory)
    .where(eq(positionHistory.status, "closed"));

  // 每日盈亏曲线
  const dailyPnl = await db
    .select({
      date: dailyStats.date,
      pnl: sql<number>`COALESCE(SUM(${dailyStats.totalPnl}::numeric), 0)`,
      trades: sql<number>`COALESCE(SUM(${dailyStats.totalTrades}), 0)`,
    })
    .from(dailyStats)
    .groupBy(dailyStats.date)
    .orderBy(dailyStats.date)
    .limit(30);

  // 累计盈亏
  let cumulative = 0;
  const cumulativePnl = dailyPnl.map(d => {
    cumulative += Number(d.pnl);
    return { date: d.date, pnl: Number(d.pnl), cumulative };
  });

  // 按交易对统计
  const symbolStats = await db
    .select({
      symbol: positionHistory.symbol,
      trades: sql<number>`count(*)`,
      pnl: sql<number>`COALESCE(SUM(${positionHistory.realizedPnl}::numeric), 0)`,
      winRate: sql<number>`ROUND(count(*) FILTER (WHERE ${positionHistory.realizedPnl}::numeric > 0) * 100.0 / NULLIF(count(*), 0), 1)`,
    })
    .from(positionHistory)
    .where(eq(positionHistory.status, "closed"))
    .groupBy(positionHistory.symbol)
    .orderBy(sql`SUM(${positionHistory.realizedPnl}::numeric) DESC`);

  // 按方向统计
  const sideStats = await db
    .select({
      side: positionHistory.side,
      trades: sql<number>`count(*)`,
      pnl: sql<number>`COALESCE(SUM(${positionHistory.realizedPnl}::numeric), 0)`,
      winRate: sql<number>`ROUND(count(*) FILTER (WHERE ${positionHistory.realizedPnl}::numeric > 0) * 100.0 / NULLIF(count(*), 0), 1)`,
    })
    .from(positionHistory)
    .where(eq(positionHistory.status, "closed"))
    .groupBy(positionHistory.side);

  const stats = overallStats[0] || {};

  return {
    stats: {
      totalTrades: Number(stats.totalTrades) || 0,
      winningTrades: Number(stats.winningTrades) || 0,
      losingTrades: Number(stats.losingTrades) || 0,
      winRate: stats.totalTrades > 0 ? Math.round((Number(stats.winningTrades) / Number(stats.totalTrades)) * 100) : 0,
      totalPnl: Number(stats.totalPnl) || 0,
      avgWin: Number(stats.avgWin) || 0,
      avgLoss: Number(stats.avgLoss) || 0,
      maxWin: Number(stats.maxWin) || 0,
      maxLoss: Number(stats.maxLoss) || 0,
      profitFactor: Math.abs(Number(stats.avgLoss)) > 0 ? Math.abs(Number(stats.avgWin) / Number(stats.avgLoss)) : 0,
    },
    cumulativePnl,
    symbolStats: symbolStats.map(s => ({
      symbol: s.symbol,
      trades: Number(s.trades),
      pnl: Number(s.pnl),
      winRate: Number(s.winRate) || 0,
    })),
    sideStats: sideStats.map(s => ({
      side: s.side,
      trades: Number(s.trades),
      pnl: Number(s.pnl),
      winRate: Number(s.winRate) || 0,
    })),
  };
}
```

**Step 2: 实现组件**

```typescript
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card";
import { StatCard } from "~/components/common/StatCard";
import { formatUSD, cn } from "~/lib/utils";
import { TrendingUp, TrendingDown, Target, Percent, BarChart3, Scale } from "lucide-react";
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";

export default function AnalyticsPage({ loaderData }: Route.ComponentProps) {
  const { stats, cumulativePnl, symbolStats, sideStats } = loaderData;

  return (
    <div className="space-y-6">
      {/* 核心指标 */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard label="总交易数" value={`${stats.totalTrades}`} icon={BarChart3} />
        <StatCard label="胜率" value={`${stats.winRate}%`} icon={Target} />
        <StatCard
          label="总盈亏"
          value={formatUSD(stats.totalPnl)}
          variant={stats.totalPnl >= 0 ? "profit" : "loss"}
          icon={stats.totalPnl >= 0 ? TrendingUp : TrendingDown}
        />
        <StatCard
          label="盈亏比"
          value={stats.profitFactor.toFixed(2)}
          variant={stats.profitFactor >= 1 ? "profit" : "loss"}
          icon={Scale}
        />
      </div>

      {/* 盈亏统计 */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">盈亏详情</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground">盈利交易</p>
                <p className="text-2xl font-bold text-profit">{stats.winningTrades}</p>
              </div>
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground">亏损交易</p>
                <p className="text-2xl font-bold text-loss">{stats.losingTrades}</p>
              </div>
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground">平均盈利</p>
                <p className="text-lg font-medium text-profit">{formatUSD(stats.avgWin)}</p>
              </div>
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground">平均亏损</p>
                <p className="text-lg font-medium text-loss">{formatUSD(stats.avgLoss)}</p>
              </div>
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground">最大盈利</p>
                <p className="text-lg font-medium text-profit">{formatUSD(stats.maxWin)}</p>
              </div>
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground">最大亏损</p>
                <p className="text-lg font-medium text-loss">{formatUSD(stats.maxLoss)}</p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* 多空对比 */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">多空对比</CardTitle>
          </CardHeader>
          <CardContent>
            {sideStats.length > 0 ? (
              <div className="space-y-4">
                {sideStats.map((s) => (
                  <div key={s.side} className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <span className={cn("rounded px-2 py-1 text-sm font-medium",
                        s.side === "long" ? "bg-profit/20 text-profit" : "bg-loss/20 text-loss"
                      )}>
                        {s.side === "long" ? "多" : "空"}
                      </span>
                      <span className="text-sm text-muted-foreground">{s.trades} 笔</span>
                    </div>
                    <div className="text-right">
                      <p className={cn("font-medium", s.pnl >= 0 ? "text-profit" : "text-loss")}>
                        {formatUSD(s.pnl)}
                      </p>
                      <p className="text-sm text-muted-foreground">胜率 {s.winRate}%</p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="flex h-32 items-center justify-center text-muted-foreground">
                暂无数据
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* 累计盈亏曲线 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">累计盈亏曲线</CardTitle>
        </CardHeader>
        <CardContent>
          {cumulativePnl.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <AreaChart data={cumulativePnl}>
                <XAxis dataKey="date" tickFormatter={(v) => v.slice(5)} fontSize={12} />
                <YAxis fontSize={12} tickFormatter={(v) => `$${v}`} />
                <Tooltip
                  formatter={(v: number) => [formatUSD(v), "累计盈亏"]}
                  labelFormatter={(v) => `日期: ${v}`}
                />
                <Area
                  type="monotone"
                  dataKey="cumulative"
                  stroke="#8b5cf6"
                  fill="#8b5cf6"
                  fillOpacity={0.3}
                />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-[300px] items-center justify-center text-muted-foreground">
              暂无数据
            </div>
          )}
        </CardContent>
      </Card>

      {/* 交易对表现 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">交易对表现</CardTitle>
        </CardHeader>
        <CardContent>
          {symbolStats.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={symbolStats} layout="vertical">
                <XAxis type="number" fontSize={12} tickFormatter={(v) => `$${v}`} />
                <YAxis type="category" dataKey="symbol" fontSize={12} width={80} />
                <Tooltip formatter={(v: number) => [formatUSD(v), "盈亏"]} />
                <Bar dataKey="pnl" radius={[0, 4, 4, 0]}>
                  {symbolStats.map((entry, index) => (
                    <Cell key={index} fill={entry.pnl >= 0 ? "#22c55e" : "#ef4444"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-[200px] items-center justify-center text-muted-foreground">
              暂无数据
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
```

**Step 3: 验证**

Run: `docker compose up -d --build dashboard`

访问 http://localhost:3000/dashboard/analytics 确认页面正常加载

**Step 4: Commit**

```bash
git add dashboard/app/routes/dashboard.analytics.tsx
git commit -m "feat(dashboard): implement analytics page with pnl curve and stats"
```

---

## Task 3: 回测页面 (Backtest)

**Files:**
- Modify: `dashboard/app/routes/dashboard.backtest.tsx`

**Step 1: 实现 loader 函数**

```typescript
import type { Route } from "./+types/dashboard.backtest";
import { db } from "db";
import { backtests, backtestTrades, backtestEquity } from "db/schema";
import { desc, eq, sql } from "drizzle-orm";

export async function loader({ request }: Route.LoaderArgs) {
  const url = new URL(request.url);
  const selectedId = url.searchParams.get("id");

  // 回测列表
  const backtestList = await db
    .select({
      id: backtests.id,
      createdAt: backtests.createdAt,
      symbol: backtests.symbol,
      mode: backtests.mode,
      startDate: backtests.startDate,
      endDate: backtests.endDate,
      initialCapital: backtests.initialCapital,
      status: backtests.status,
      finalCapital: backtests.finalCapital,
      totalPnl: backtests.totalPnl,
      totalTrades: backtests.totalTrades,
      winningTrades: backtests.winningTrades,
      maxDrawdown: backtests.maxDrawdown,
      sharpeRatio: backtests.sharpeRatio,
    })
    .from(backtests)
    .orderBy(desc(backtests.createdAt))
    .limit(20);

  let selectedBacktest = null;
  let trades: any[] = [];
  let equityCurve: any[] = [];

  if (selectedId) {
    const result = await db
      .select()
      .from(backtests)
      .where(eq(backtests.id, selectedId))
      .limit(1);

    if (result[0]) {
      selectedBacktest = result[0];

      trades = await db
        .select()
        .from(backtestTrades)
        .where(eq(backtestTrades.backtestId, selectedId))
        .orderBy(backtestTrades.entryTime);

      equityCurve = await db
        .select()
        .from(backtestEquity)
        .where(eq(backtestEquity.backtestId, selectedId))
        .orderBy(backtestEquity.timestamp);
    }
  }

  return {
    backtestList: backtestList.map(b => ({
      id: b.id,
      createdAt: b.createdAt.toISOString(),
      symbol: b.symbol,
      mode: b.mode,
      startDate: b.startDate,
      endDate: b.endDate,
      initialCapital: Number(b.initialCapital),
      status: b.status,
      finalCapital: b.finalCapital ? Number(b.finalCapital) : null,
      totalPnl: b.totalPnl ? Number(b.totalPnl) : null,
      totalTrades: b.totalTrades,
      winningTrades: b.winningTrades,
      maxDrawdown: b.maxDrawdown ? Number(b.maxDrawdown) : null,
      sharpeRatio: b.sharpeRatio ? Number(b.sharpeRatio) : null,
    })),
    selectedBacktest: selectedBacktest ? {
      ...selectedBacktest,
      createdAt: selectedBacktest.createdAt.toISOString(),
      completedAt: selectedBacktest.completedAt?.toISOString(),
      initialCapital: Number(selectedBacktest.initialCapital),
      finalCapital: selectedBacktest.finalCapital ? Number(selectedBacktest.finalCapital) : null,
      totalPnl: selectedBacktest.totalPnl ? Number(selectedBacktest.totalPnl) : null,
      maxDrawdown: selectedBacktest.maxDrawdown ? Number(selectedBacktest.maxDrawdown) : null,
      sharpeRatio: selectedBacktest.sharpeRatio ? Number(selectedBacktest.sharpeRatio) : null,
    } : null,
    trades: trades.map(t => ({
      id: t.id,
      symbol: t.symbol,
      side: t.side,
      entryTime: t.entryTime.toISOString(),
      exitTime: t.exitTime?.toISOString(),
      entryPrice: Number(t.entryPrice),
      exitPrice: t.exitPrice ? Number(t.exitPrice) : null,
      size: Number(t.size),
      pnl: t.pnl ? Number(t.pnl) : null,
      pnlPercent: t.pnlPercent ? Number(t.pnlPercent) : null,
    })),
    equityCurve: equityCurve.map(e => ({
      timestamp: e.timestamp.toISOString(),
      equity: Number(e.totalEquity),
    })),
  };
}
```

**Step 2: 实现组件**

```typescript
import { Link, useSearchParams } from "react-router";
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card";
import { formatUSD, cn } from "~/lib/utils";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { Check, X, Loader2 } from "lucide-react";

export default function BacktestPage({ loaderData }: Route.ComponentProps) {
  const { backtestList, selectedBacktest, trades, equityCurve } = loaderData;
  const [searchParams] = useSearchParams();
  const selectedId = searchParams.get("id");

  return (
    <div className="flex gap-6">
      {/* 回测列表 */}
      <div className="w-80 shrink-0 space-y-4">
        <h2 className="text-lg font-semibold">回测记录</h2>
        {backtestList.length > 0 ? (
          <div className="space-y-2">
            {backtestList.map((b) => (
              <Link
                key={b.id}
                to={`?id=${b.id}`}
                className={cn(
                  "block rounded-lg border p-3 transition-colors hover:bg-accent",
                  selectedId === b.id && "border-primary bg-accent"
                )}
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium">{b.symbol || "组合"}</span>
                  <StatusBadge status={b.status} />
                </div>
                <div className="mt-1 text-sm text-muted-foreground">
                  {b.startDate} ~ {b.endDate}
                </div>
                {b.status === "completed" && (
                  <div className={cn("mt-1 text-sm font-medium", (b.totalPnl ?? 0) >= 0 ? "text-profit" : "text-loss")}>
                    {formatUSD(b.totalPnl ?? 0)} ({b.totalPnl && b.initialCapital ? ((b.totalPnl / b.initialCapital) * 100).toFixed(2) : 0}%)
                  </div>
                )}
              </Link>
            ))}
          </div>
        ) : (
          <div className="text-center text-muted-foreground">暂无回测记录</div>
        )}
      </div>

      {/* 回测详情 */}
      <div className="flex-1 space-y-6">
        {selectedBacktest ? (
          <>
            {/* 统计概览 */}
            <div className="grid gap-4 md:grid-cols-4">
              <Card>
                <CardContent className="pt-4">
                  <p className="text-sm text-muted-foreground">初始资金</p>
                  <p className="text-xl font-bold">{formatUSD(selectedBacktest.initialCapital)}</p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-4">
                  <p className="text-sm text-muted-foreground">最终资金</p>
                  <p className="text-xl font-bold">{formatUSD(selectedBacktest.finalCapital ?? 0)}</p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-4">
                  <p className="text-sm text-muted-foreground">总盈亏</p>
                  <p className={cn("text-xl font-bold", (selectedBacktest.totalPnl ?? 0) >= 0 ? "text-profit" : "text-loss")}>
                    {formatUSD(selectedBacktest.totalPnl ?? 0)}
                  </p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-4">
                  <p className="text-sm text-muted-foreground">夏普比率</p>
                  <p className="text-xl font-bold">{selectedBacktest.sharpeRatio?.toFixed(2) ?? "-"}</p>
                </CardContent>
              </Card>
            </div>

            {/* 权益曲线 */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">权益曲线</CardTitle>
              </CardHeader>
              <CardContent>
                {equityCurve.length > 0 ? (
                  <ResponsiveContainer width="100%" height={300}>
                    <AreaChart data={equityCurve}>
                      <XAxis
                        dataKey="timestamp"
                        tickFormatter={(v) => new Date(v).toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" })}
                        fontSize={12}
                      />
                      <YAxis fontSize={12} tickFormatter={(v) => `$${v}`} />
                      <Tooltip
                        labelFormatter={(v) => new Date(v).toLocaleString("zh-CN")}
                        formatter={(v: number) => [formatUSD(v), "权益"]}
                      />
                      <Area type="monotone" dataKey="equity" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.3} />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="flex h-[300px] items-center justify-center text-muted-foreground">
                    暂无权益数据
                  </div>
                )}
              </CardContent>
            </Card>

            {/* 交易记录 */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">交易记录 ({trades.length})</CardTitle>
              </CardHeader>
              <CardContent>
                {trades.length > 0 ? (
                  <div className="max-h-96 overflow-auto">
                    <table className="w-full text-sm">
                      <thead className="sticky top-0 bg-card">
                        <tr className="border-b text-left text-muted-foreground">
                          <th className="pb-2">交易对</th>
                          <th className="pb-2">方向</th>
                          <th className="pb-2">入场价</th>
                          <th className="pb-2">出场价</th>
                          <th className="pb-2">盈亏</th>
                          <th className="pb-2">收益率</th>
                        </tr>
                      </thead>
                      <tbody>
                        {trades.map((t) => (
                          <tr key={t.id} className="border-b">
                            <td className="py-2">{t.symbol}</td>
                            <td className={cn("py-2", t.side === "long" ? "text-profit" : "text-loss")}>
                              {t.side === "long" ? "多" : "空"}
                            </td>
                            <td className="py-2">{t.entryPrice.toFixed(2)}</td>
                            <td className="py-2">{t.exitPrice?.toFixed(2) ?? "-"}</td>
                            <td className={cn("py-2", (t.pnl ?? 0) >= 0 ? "text-profit" : "text-loss")}>
                              {formatUSD(t.pnl ?? 0)}
                            </td>
                            <td className={cn("py-2", (t.pnlPercent ?? 0) >= 0 ? "text-profit" : "text-loss")}>
                              {t.pnlPercent?.toFixed(2) ?? 0}%
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="flex h-32 items-center justify-center text-muted-foreground">
                    暂无交易记录
                  </div>
                )}
              </CardContent>
            </Card>
          </>
        ) : (
          <div className="flex h-96 items-center justify-center text-muted-foreground">
            选择一个回测记录查看详情
          </div>
        )}
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  if (status === "completed") {
    return <span className="flex items-center gap-1 text-xs text-profit"><Check className="h-3 w-3" /> 完成</span>;
  }
  if (status === "running") {
    return <span className="flex items-center gap-1 text-xs text-blue-500"><Loader2 className="h-3 w-3 animate-spin" /> 运行中</span>;
  }
  if (status === "failed") {
    return <span className="flex items-center gap-1 text-xs text-loss"><X className="h-3 w-3" /> 失败</span>;
  }
  return <span className="text-xs text-muted-foreground">{status}</span>;
}
```

**Step 3: 验证**

Run: `docker compose up -d --build dashboard`

访问 http://localhost:3000/dashboard/backtest 确认页面正常加载

**Step 4: Commit**

```bash
git add dashboard/app/routes/dashboard.backtest.tsx
git commit -m "feat(dashboard): implement backtest page with equity curve and trades"
```

---

## Task 4: 图表页面 (Chart)

**Files:**
- Modify: `dashboard/app/routes/dashboard.chart.tsx`

**Step 1: 实现 loader 函数**

```typescript
import type { Route } from "./+types/dashboard.chart";
import { db } from "db";
import { priceHistory, technicalSnapshots, decisions } from "db/schema";
import { desc, eq, sql, gte } from "drizzle-orm";

export async function loader(_args: Route.LoaderArgs) {
  const sevenDaysAgo = new Date();
  sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);

  // 获取价格历史（如果有数据）
  const prices = await db
    .select()
    .from(priceHistory)
    .where(gte(priceHistory.timestamp, sevenDaysAgo))
    .orderBy(priceHistory.timestamp)
    .limit(500);

  // 获取最近的技术指标快照
  const recentTechnical = await db
    .select({
      createdAt: decisions.createdAt,
      symbol: decisions.symbol,
      price: technicalSnapshots.price,
      rsi: technicalSnapshots.rsi,
      macd: technicalSnapshots.macd,
      ma7: technicalSnapshots.ma7,
      ma25: technicalSnapshots.ma25,
      ma99: technicalSnapshots.ma99,
      trend: technicalSnapshots.trend,
      signalStrength: technicalSnapshots.signalStrength,
    })
    .from(technicalSnapshots)
    .innerJoin(decisions, eq(technicalSnapshots.decisionId, decisions.id))
    .orderBy(desc(decisions.createdAt))
    .limit(100);

  // 获取可用的交易对
  const symbols = await db
    .selectDistinct({ symbol: decisions.symbol })
    .from(decisions)
    .limit(10);

  return {
    prices: prices.map(p => ({
      symbol: p.symbol,
      timestamp: p.timestamp.toISOString(),
      price: Number(p.closePrice),
    })),
    technicalData: recentTechnical.map(t => ({
      timestamp: t.createdAt.toISOString(),
      symbol: t.symbol,
      price: t.price ? Number(t.price) : null,
      rsi: t.rsi ? Number(t.rsi) : null,
      macd: t.macd ? Number(t.macd) : null,
      ma7: t.ma7 ? Number(t.ma7) : null,
      ma25: t.ma25 ? Number(t.ma25) : null,
      ma99: t.ma99 ? Number(t.ma99) : null,
      trend: t.trend,
      signalStrength: t.signalStrength,
    })),
    symbols: symbols.map(s => s.symbol),
  };
}
```

**Step 2: 实现组件**

```typescript
import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card";
import { cn } from "~/lib/utils";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Legend,
  ComposedChart,
  Bar,
} from "recharts";

export default function ChartPage({ loaderData }: Route.ComponentProps) {
  const { prices, technicalData, symbols } = loaderData;
  const [selectedSymbol, setSelectedSymbol] = useState<string>(symbols[0] || "");

  const filteredData = technicalData.filter(t => t.symbol === selectedSymbol);

  return (
    <div className="space-y-6">
      {/* 交易对选择 */}
      <div className="flex gap-2">
        {symbols.map((symbol) => (
          <button
            key={symbol}
            onClick={() => setSelectedSymbol(symbol)}
            className={cn(
              "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
              selectedSymbol === symbol
                ? "bg-primary text-primary-foreground"
                : "bg-muted hover:bg-accent"
            )}
          >
            {symbol}
          </button>
        ))}
      </div>

      {filteredData.length > 0 ? (
        <>
          {/* 价格与均线 */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">价格与均线</CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={filteredData}>
                  <XAxis
                    dataKey="timestamp"
                    tickFormatter={(v) => new Date(v).toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit" })}
                    fontSize={10}
                  />
                  <YAxis fontSize={12} domain={["auto", "auto"]} />
                  <Tooltip
                    labelFormatter={(v) => new Date(v).toLocaleString("zh-CN")}
                    formatter={(v: number, name: string) => [v?.toFixed(2), name]}
                  />
                  <Legend />
                  <Line type="monotone" dataKey="price" stroke="#3b82f6" dot={false} name="价格" />
                  <Line type="monotone" dataKey="ma7" stroke="#22c55e" dot={false} name="MA7" />
                  <Line type="monotone" dataKey="ma25" stroke="#eab308" dot={false} name="MA25" />
                  <Line type="monotone" dataKey="ma99" stroke="#ef4444" dot={false} name="MA99" />
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* RSI 指标 */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">RSI 指标</CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={filteredData}>
                  <XAxis
                    dataKey="timestamp"
                    tickFormatter={(v) => new Date(v).toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" })}
                    fontSize={10}
                  />
                  <YAxis fontSize={12} domain={[0, 100]} />
                  <Tooltip
                    labelFormatter={(v) => new Date(v).toLocaleString("zh-CN")}
                    formatter={(v: number) => [v?.toFixed(2), "RSI"]}
                  />
                  {/* 超买超卖区域 */}
                  <Line type="monotone" dataKey="rsi" stroke="#8b5cf6" dot={false} />
                </LineChart>
              </ResponsiveContainer>
              <div className="mt-2 flex justify-center gap-4 text-xs text-muted-foreground">
                <span>超买 &gt; 70</span>
                <span>超卖 &lt; 30</span>
              </div>
            </CardContent>
          </Card>

          {/* MACD 指标 */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">MACD 指标</CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={200}>
                <ComposedChart data={filteredData}>
                  <XAxis
                    dataKey="timestamp"
                    tickFormatter={(v) => new Date(v).toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" })}
                    fontSize={10}
                  />
                  <YAxis fontSize={12} />
                  <Tooltip
                    labelFormatter={(v) => new Date(v).toLocaleString("zh-CN")}
                    formatter={(v: number) => [v?.toFixed(4), "MACD"]}
                  />
                  <Bar dataKey="macd" fill="#3b82f6" />
                </ComposedChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* 趋势信号 */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">最新技术信号</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                {filteredData.slice(0, 4).map((t, i) => (
                  <div key={i} className="rounded-lg border p-3">
                    <p className="text-xs text-muted-foreground">
                      {new Date(t.timestamp).toLocaleString("zh-CN")}
                    </p>
                    <div className="mt-2 flex items-center justify-between">
                      <span className="text-sm">趋势</span>
                      <TrendBadge trend={t.trend} />
                    </div>
                    <div className="mt-1 flex items-center justify-between">
                      <span className="text-sm">信号</span>
                      <SignalBadge signal={t.signalStrength} />
                    </div>
                    <div className="mt-1 flex items-center justify-between">
                      <span className="text-sm">RSI</span>
                      <span className={cn("text-sm font-medium",
                        (t.rsi ?? 50) > 70 ? "text-loss" : (t.rsi ?? 50) < 30 ? "text-profit" : ""
                      )}>
                        {t.rsi?.toFixed(1) ?? "-"}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </>
      ) : (
        <Card>
          <CardContent className="flex h-96 items-center justify-center text-muted-foreground">
            {symbols.length > 0 ? "暂无该交易对的技术指标数据" : "暂无数据，请先运行交易程序生成决策"}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function TrendBadge({ trend }: { trend: string | null }) {
  const colors: Record<string, string> = {
    strong_bullish: "bg-profit/20 text-profit",
    bullish: "bg-profit/10 text-profit",
    neutral: "bg-muted text-muted-foreground",
    bearish: "bg-loss/10 text-loss",
    strong_bearish: "bg-loss/20 text-loss",
  };
  const labels: Record<string, string> = {
    strong_bullish: "强多",
    bullish: "看多",
    neutral: "中性",
    bearish: "看空",
    strong_bearish: "强空",
  };
  return (
    <span className={cn("rounded px-2 py-0.5 text-xs font-medium", colors[trend || "neutral"])}>
      {labels[trend || "neutral"] || trend}
    </span>
  );
}

function SignalBadge({ signal }: { signal: string | null }) {
  const colors: Record<string, string> = {
    strong_buy: "bg-profit/20 text-profit",
    buy: "bg-profit/10 text-profit",
    neutral: "bg-muted text-muted-foreground",
    sell: "bg-loss/10 text-loss",
    strong_sell: "bg-loss/20 text-loss",
  };
  const labels: Record<string, string> = {
    strong_buy: "强买",
    buy: "买入",
    neutral: "观望",
    sell: "卖出",
    strong_sell: "强卖",
  };
  return (
    <span className={cn("rounded px-2 py-0.5 text-xs font-medium", colors[signal || "neutral"])}>
      {labels[signal || "neutral"] || signal}
    </span>
  );
}
```

**Step 3: 验证**

Run: `docker compose up -d --build dashboard`

访问 http://localhost:3000/dashboard/chart 确认页面正常加载

**Step 4: Commit**

```bash
git add dashboard/app/routes/dashboard.chart.tsx
git commit -m "feat(dashboard): implement chart page with technical indicators"
```

---

## Task 5: 添加类型文件

**Files:**
- Create: `dashboard/app/routes/+types/dashboard.positions.ts`
- Create: `dashboard/app/routes/+types/dashboard.analytics.ts`
- Create: `dashboard/app/routes/+types/dashboard.backtest.ts`
- Create: `dashboard/app/routes/+types/dashboard.chart.ts`

**Step 1: 运行类型生成**

React Router 7 会自动生成类型，运行：

```bash
cd dashboard && npm run typecheck
```

如果类型文件不存在，手动创建空文件占位：

```typescript
// dashboard/app/routes/+types/dashboard.positions.ts
import type { LoaderArgs as BaseLoaderArgs, ComponentProps as BaseComponentProps } from "react-router";

export type LoaderArgs = BaseLoaderArgs;
export type ComponentProps = BaseComponentProps<typeof import("../dashboard.positions").loader>;
export namespace Route {
  export type LoaderArgs = BaseLoaderArgs;
  export type ComponentProps = BaseComponentProps<typeof import("../dashboard.positions").loader>;
}
```

**Step 2: Commit**

```bash
git add dashboard/app/routes/
git commit -m "feat(dashboard): add type definitions for new pages"
```

---

## Task 6: 最终验证与清理

**Step 1: 重新构建所有服务**

```bash
docker compose down
docker compose up -d --build
```

**Step 2: 验证所有页面**

- http://localhost:3000/dashboard/positions
- http://localhost:3000/dashboard/analytics
- http://localhost:3000/dashboard/backtest
- http://localhost:3000/dashboard/chart

**Step 3: 提交最终代码**

```bash
git add .
git commit -m "feat(dashboard): complete positions, analytics, backtest, chart pages"
```

---

## 注意事项

1. **数据依赖**: 图表页面依赖 `technicalSnapshots` 表数据，需要后端 Python 程序运行并生成决策后才有数据显示

2. **实时 K 线**: 当前实现使用技术指标快照数据，如需实时 K 线需额外开发 API 代理或集成 TradingView widget

3. **分页**: 历史数据量大时需要添加分页功能

4. **刷新**: 可考虑添加自动刷新或手动刷新按钮
