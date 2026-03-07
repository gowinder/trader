import type { Route } from "./+types/dashboard._index";
import { StatCard } from "~/components/common/StatCard";
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card";
import { formatUSD, formatPercent, cn } from "~/lib/utils";
import { TrendingUp, TrendingDown, Target, Activity, Clock, Wallet } from "lucide-react";
import { db } from "db";
import { decisions, dailyStats, positionHistory } from "db/schema";
import { desc, sql, eq, gte, and, asc, isNotNull } from "drizzle-orm";
import { useState, useMemo } from "react";
import { createClient } from "redis";
import {
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Legend,
  AreaChart,
  Area,
} from "recharts";

export async function loader(_args: Route.LoaderArgs) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  // 获取最近决策
  const recentDecisionsData = await db
    .select({
      id: decisions.id,
      createdAt: decisions.createdAt,
      symbol: decisions.symbol,
      action: decisions.action,
      confidence: decisions.confidence,
      reasoning: decisions.reasoning,
      reasoningZh: decisions.reasoningZh,
    })
    .from(decisions)
    .orderBy(desc(decisions.createdAt))
    .limit(5);

  // 获取今日统计
  const todayStatsData = await db
    .select({
      totalTrades: sql<number>`COALESCE(SUM(${dailyStats.totalTrades}), 0)`,
      winningTrades: sql<number>`COALESCE(SUM(${dailyStats.winningTrades}), 0)`,
      totalPnl: sql<number>`COALESCE(SUM(${dailyStats.totalPnl}::numeric), 0)`,
    })
    .from(dailyStats)
    .where(eq(dailyStats.date, today.toISOString().split("T")[0]));

  // 获取总决策数
  const totalDecisionsResult = await db
    .select({ count: sql<number>`count(*)` })
    .from(decisions);
  const totalDecisions = totalDecisionsResult[0]?.count || 0;

  // 获取今日决策数
  const todayDecisionsResult = await db
    .select({ count: sql<number>`count(*)` })
    .from(decisions)
    .where(gte(decisions.createdAt, today));
  const todayDecisions = todayDecisionsResult[0]?.count || 0;

  // 获取决策动作分布
  const actionDistribution = await db
    .select({
      action: decisions.action,
      count: sql<number>`count(*)`,
    })
    .from(decisions)
    .groupBy(decisions.action);

  // 获取最近7天决策趋势
  const sevenDaysAgo = new Date();
  sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);
  sevenDaysAgo.setHours(0, 0, 0, 0);

  const dailyTrend = await db
    .select({
      date: sql<string>`DATE(${decisions.createdAt})`,
      count: sql<number>`count(*)`,
    })
    .from(decisions)
    .where(gte(decisions.createdAt, sevenDaysAgo))
    .groupBy(sql`DATE(${decisions.createdAt})`)
    .orderBy(sql`DATE(${decisions.createdAt})`);

  // 获取置信度分布
  const confidenceDistribution = await db
    .select({
      range: sql<string>`
        CASE
          WHEN ${decisions.confidence} >= 90 THEN '90-100'
          WHEN ${decisions.confidence} >= 80 THEN '80-89'
          WHEN ${decisions.confidence} >= 70 THEN '70-79'
          WHEN ${decisions.confidence} >= 60 THEN '60-69'
          ELSE '< 60'
        END
      `,
      count: sql<number>`count(*)`,
    })
    .from(decisions)
    .groupBy(sql`
      CASE
        WHEN ${decisions.confidence} >= 90 THEN '90-100'
        WHEN ${decisions.confidence} >= 80 THEN '80-89'
        WHEN ${decisions.confidence} >= 70 THEN '70-79'
        WHEN ${decisions.confidence} >= 60 THEN '60-69'
        ELSE '< 60'
      END
    `);

  // 获取交易对分布
  const symbolDistribution = await db
    .select({
      symbol: decisions.symbol,
      count: sql<number>`count(*)`,
    })
    .from(decisions)
    .groupBy(decisions.symbol)
    .orderBy(sql`count(*) DESC`)
    .limit(5);

  // 获取每小时决策分布
  const hourlyDistribution = await db
    .select({
      hour: sql<number>`EXTRACT(HOUR FROM ${decisions.createdAt})`,
      count: sql<number>`count(*)`,
    })
    .from(decisions)
    .groupBy(sql`EXTRACT(HOUR FROM ${decisions.createdAt})`)
    .orderBy(sql`EXTRACT(HOUR FROM ${decisions.createdAt})`);

  // 获取最近7天平均置信度趋势
  const confidenceTrend = await db
    .select({
      date: sql<string>`DATE(${decisions.createdAt})`,
      avgConfidence: sql<number>`AVG(${decisions.confidence})`,
      count: sql<number>`count(*)`,
    })
    .from(decisions)
    .where(gte(decisions.createdAt, sevenDaysAgo))
    .groupBy(sql`DATE(${decisions.createdAt})`)
    .orderBy(sql`DATE(${decisions.createdAt})`);

  // 获取 LLM 提供商分布
  const llmDistribution = await db
    .select({
      provider: decisions.llmProvider,
      count: sql<number>`count(*)`,
    })
    .from(decisions)
    .groupBy(decisions.llmProvider);

  // 获取多空比例趋势
  const longShortTrend = await db
    .select({
      date: sql<string>`DATE(${decisions.createdAt})`,
      longCount: sql<number>`SUM(CASE WHEN ${decisions.action} LIKE '%long%' THEN 1 ELSE 0 END)`,
      shortCount: sql<number>`SUM(CASE WHEN ${decisions.action} LIKE '%short%' THEN 1 ELSE 0 END)`,
      holdCount: sql<number>`SUM(CASE WHEN ${decisions.action} = 'hold' THEN 1 ELSE 0 END)`,
    })
    .from(decisions)
    .where(gte(decisions.createdAt, sevenDaysAgo))
    .groupBy(sql`DATE(${decisions.createdAt})`)
    .orderBy(sql`DATE(${decisions.createdAt})`);

  const stats = todayStatsData[0] || {
    totalTrades: 0,
    winningTrades: 0,
    totalPnl: 0,
  };
  const winRate =
    stats.totalTrades > 0
      ? Math.round((stats.winningTrades / stats.totalTrades) * 100)
      : 0;

  // 获取累计已实现 PNL（从 positionHistory）
  const totalRealizedPnlResult = await db
    .select({
      totalPnl: sql<number>`COALESCE(SUM(${positionHistory.realizedPnl}::numeric), 0)`,
      totalTrades: sql<number>`count(*)`,
      winningTrades: sql<number>`count(*) FILTER (WHERE ${positionHistory.realizedPnl}::numeric > 0)`,
    })
    .from(positionHistory)
    .where(eq(positionHistory.status, "closed"));

  const totalRealizedStats = totalRealizedPnlResult[0] || { totalPnl: 0, totalTrades: 0, winningTrades: 0 };
  const totalWinRate = Number(totalRealizedStats.totalTrades) > 0
    ? Math.round((Number(totalRealizedStats.winningTrades) / Number(totalRealizedStats.totalTrades)) * 100)
    : 0;

  // 获取实时账户状态（从 Redis）
  let accountState = null;
  {
    const redisUrl = process.env.REDIS_URL || "redis://localhost:6379";
    const client = createClient({ url: redisUrl });
    try {
      await client.connect();
      const stateJson = await client.get("trading:account_state");
      if (stateJson) {
        accountState = JSON.parse(stateJson);
      }
    } catch (e) {
      console.error("Failed to fetch account state from Redis:", e);
    } finally {
      try { await client.disconnect(); } catch { /* ignore */ }
    }
  }

  // 获取收益走势数据（所有 closed 仓位，按 exit_time 排序）
  const pnlHistoryData = await db
    .select({
      exitTime: positionHistory.exitTime,
      realizedPnl: positionHistory.realizedPnl,
      symbol: positionHistory.symbol,
    })
    .from(positionHistory)
    .where(
      and(
        eq(positionHistory.status, "closed"),
        isNotNull(positionHistory.exitTime)
      )
    )
    .orderBy(asc(positionHistory.exitTime));

  return {
    pnlHistory: pnlHistoryData.map((p) => ({
      exitTime: p.exitTime!.toISOString(),
      realizedPnl: Number(p.realizedPnl) || 0,
      symbol: p.symbol,
    })),
    todayStats: {
      pnl: Number(stats.totalPnl) || 0,
      pnlPct: 0,
      trades: stats.totalTrades,
      winningTrades: stats.winningTrades,
      winRate,
    },
    // 累计已实现 PNL
    totalRealizedPnl: Number(totalRealizedStats.totalPnl) || 0,
    totalTrades: Number(totalRealizedStats.totalTrades) || 0,
    totalWinRate,
    // 实时账户状态（包含未实现 PNL）
    accountState,
    totalDecisions,
    todayDecisions,
    recentDecisions: recentDecisionsData.map((d) => ({
      id: d.id,
      createdAt: d.createdAt.toISOString(),
      symbol: d.symbol,
      action: d.action,
      confidence: d.confidence,
      reasoning: d.reasoning,
      reasoningZh: d.reasoningZh,
    })),
    actionDistribution: actionDistribution.map((d) => ({
      name: formatActionLabel(d.action),
      value: Number(d.count),
      action: d.action,
    })),
    dailyTrend: dailyTrend.map((d) => ({
      date: d.date,
      count: Number(d.count),
    })),
    confidenceDistribution: confidenceDistribution.map((d) => ({
      range: d.range,
      count: Number(d.count),
    })),
    symbolDistribution: symbolDistribution.map((d) => ({
      symbol: d.symbol,
      count: Number(d.count),
    })),
    hourlyDistribution: Array.from({ length: 24 }, (_, i) => {
      const found = hourlyDistribution.find((h) => Number(h.hour) === i);
      return {
        hour: `${i.toString().padStart(2, "0")}:00`,
        count: found ? Number(found.count) : 0,
      };
    }),
    confidenceTrend: confidenceTrend.map((d) => ({
      date: d.date,
      avgConfidence: Math.round(Number(d.avgConfidence)),
      count: Number(d.count),
    })),
    llmDistribution: llmDistribution
      .filter((d) => d.provider)
      .map((d) => ({
        name: d.provider || "Unknown",
        value: Number(d.count),
      })),
    longShortTrend: longShortTrend.map((d) => ({
      date: d.date,
      long: Number(d.longCount),
      short: Number(d.shortCount),
      hold: Number(d.holdCount),
    })),
  };
}

function formatActionLabel(action: string): string {
  const map: Record<string, string> = {
    open_long: "开多",
    open_short: "开空",
    close_long: "平多",
    close_short: "平空",
    hold: "持有",
    add_long: "加多",
    add_short: "加空",
    reduce_long: "减多",
    reduce_short: "减空",
  };
  return map[action] || action;
}

const ACTION_COLORS: Record<string, string> = {
  open_long: "#22c55e",
  open_short: "#ef4444",
  close_long: "#86efac",
  close_short: "#fca5a5",
  hold: "#94a3b8",
  add_long: "#16a34a",
  add_short: "#dc2626",
  reduce_long: "#4ade80",
  reduce_short: "#f87171",
};

const CONFIDENCE_COLORS: Record<string, string> = {
  "90-100": "#22c55e",
  "80-89": "#84cc16",
  "70-79": "#eab308",
  "60-69": "#f97316",
  "< 60": "#ef4444",
};

const SYMBOL_COLORS = ["#3b82f6", "#8b5cf6", "#ec4899", "#14b8a6", "#f59e0b"];

const LLM_COLORS = ["#6366f1", "#8b5cf6", "#a855f7", "#d946ef", "#ec4899"];

export default function DashboardIndex({ loaderData }: Route.ComponentProps) {
  const {
    todayStats,
    totalDecisions,
    todayDecisions,
    recentDecisions,
    actionDistribution,
    dailyTrend,
    confidenceDistribution,
    symbolDistribution,
    hourlyDistribution,
    confidenceTrend,
    llmDistribution,
    longShortTrend,
    totalRealizedPnl,
    totalTrades,
    totalWinRate,
    accountState,
    pnlHistory,
  } = loaderData;

  // 收益走势时间范围
  const timeRanges = [
    { key: "15m", label: "15分钟", ms: 15 * 60 * 1000 },
    { key: "30m", label: "30分钟", ms: 30 * 60 * 1000 },
    { key: "1h", label: "1小时", ms: 60 * 60 * 1000 },
    { key: "12h", label: "12小时", ms: 12 * 60 * 60 * 1000 },
    { key: "24h", label: "24小时", ms: 24 * 60 * 60 * 1000 },
    { key: "1w", label: "1周", ms: 7 * 24 * 60 * 60 * 1000 },
  ] as const;
  const [selectedRange, setSelectedRange] = useState("24h");

  const pnlCurveData = useMemo(() => {
    const range = timeRanges.find((r) => r.key === selectedRange);
    if (!range || !pnlHistory.length) return [];

    const cutoff = Date.now() - range.ms;
    const filtered = pnlHistory.filter(
      (p) => new Date(p.exitTime).getTime() >= cutoff
    );

    let cumPnl = 0;
    return filtered.map((p) => {
      cumPnl += p.realizedPnl;
      return {
        time: p.exitTime,
        pnl: p.realizedPnl,
        cumPnl,
      };
    });
  }, [pnlHistory, selectedRange]);

  const formatTimeAxis = (iso: string) => {
    const d = new Date(iso);
    if (selectedRange === "1w") {
      return `${(d.getMonth() + 1).toString().padStart(2, "0")}-${d.getDate().toString().padStart(2, "0")}`;
    }
    return `${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}`;
  };

  // 从账户状态中提取未实现 PNL
  const unrealizedPnl = accountState?.account?.unrealized_pnl ?? 0;
  const totalEquity = accountState?.account?.total_equity ?? 0;

  // 当前持仓
  const positions = accountState?.positions ?? {};

  // 总 PNL = 已实现 + 未实现
  const totalPnl = totalRealizedPnl + unrealizedPnl;

  return (
    <div className="space-y-6">
      {/* PNL 汇总卡片 */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="累计已实现盈亏"
          value={formatUSD(totalRealizedPnl)}
          variant={totalRealizedPnl >= 0 ? "profit" : "loss"}
          icon={totalRealizedPnl >= 0 ? TrendingUp : TrendingDown}
          tooltip="所有已平仓位的总盈亏金额"
        />
        <StatCard
          label="未实现盈亏"
          value={formatUSD(unrealizedPnl)}
          variant={unrealizedPnl >= 0 ? "profit" : "loss"}
          icon={unrealizedPnl >= 0 ? TrendingUp : TrendingDown}
          tooltip="当前持仓的浮动盈亏，实时从交易所获取"
        />
        <StatCard
          label="总盈亏"
          value={formatUSD(totalPnl)}
          variant={totalPnl >= 0 ? "profit" : "loss"}
          icon={totalPnl >= 0 ? TrendingUp : TrendingDown}
          tooltip="已实现盈亏 + 未实现盈亏"
        />
        <StatCard
          label="账户权益"
          value={totalEquity > 0 ? formatUSD(totalEquity) : "离线"}
          icon={Wallet}
          tooltip="交易所账户总权益，包含可用余额和持仓保证金"
        />
      </div>

      {/* 收益走势曲线 */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-base">收益走势</CardTitle>
          <div className="flex gap-1">
            {timeRanges.map((r) => (
              <button
                key={r.key}
                onClick={() => setSelectedRange(r.key)}
                className={cn(
                  "px-2 py-1 text-xs rounded-md transition-colors",
                  selectedRange === r.key
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted text-muted-foreground hover:bg-muted/80"
                )}
              >
                {r.label}
              </button>
            ))}
          </div>
        </CardHeader>
        <CardContent>
          {pnlCurveData.length > 0 ? (
            <ResponsiveContainer width="100%" height={260}>
              <AreaChart data={pnlCurveData}>
                <XAxis
                  dataKey="time"
                  tickFormatter={formatTimeAxis}
                  fontSize={12}
                />
                <YAxis
                  fontSize={12}
                  tickFormatter={(v) => `$${v.toLocaleString()}`}
                />
                <Tooltip
                  labelFormatter={(v) => {
                    const d = new Date(v);
                    return `${d.getFullYear()}-${(d.getMonth() + 1).toString().padStart(2, "0")}-${d.getDate().toString().padStart(2, "0")} ${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}`;
                  }}
                  formatter={(v: number, name: string) => {
                    const labels: Record<string, string> = {
                      cumPnl: "累计盈亏",
                      pnl: "单笔盈亏",
                    };
                    return [formatUSD(v), labels[name] || name];
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="cumPnl"
                  stroke="#3b82f6"
                  fill="#3b82f6"
                  fillOpacity={0.3}
                />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-[260px] items-center justify-center text-muted-foreground">
              暂无收益数据
            </div>
          )}
        </CardContent>
      </Card>

      {/* Stats Grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
        <StatCard
          label="总决策数"
          value={`${totalDecisions}`}
          icon={Activity}
          tooltip="AI 系统累计做出的交易决策总数"
        />
        <StatCard
          label="今日决策"
          value={`${todayDecisions}`}
          icon={Clock}
          tooltip="今天 AI 系统做出的决策数量"
        />
        <StatCard
          label="累计交易"
          value={`${totalTrades} 笔`}
          icon={Target}
          tooltip="累计实际执行的交易笔数（已平仓）"
        />
        <StatCard
          label="历史胜率"
          value={`${totalWinRate}%`}
          icon={Target}
          tooltip="所有已平仓交易中盈利交易的占比"
        />
        <StatCard
          label="今日盈亏"
          value={formatUSD(todayStats.pnl)}
          variant={todayStats.pnl >= 0 ? "profit" : "loss"}
          icon={todayStats.pnl >= 0 ? TrendingUp : TrendingDown}
          tooltip="今日已平仓交易的盈亏合计"
        />
      </div>

      {/* Charts */}
      <div className="grid gap-4 lg:grid-cols-2">
        {/* Action Distribution */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">决策动作分布</CardTitle>
          </CardHeader>
          <CardContent>
            {actionDistribution.length > 0 ? (
              <ResponsiveContainer width="100%" height={200}>
                <PieChart>
                  <Pie
                    data={actionDistribution}
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={80}
                    paddingAngle={2}
                    dataKey="value"
                    label={({ name, percent }) =>
                      `${name} ${(percent * 100).toFixed(0)}%`
                    }
                    labelLine={false}
                  >
                    {actionDistribution.map((entry) => (
                      <Cell
                        key={entry.action}
                        fill={ACTION_COLORS[entry.action] || "#94a3b8"}
                      />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-[200px] items-center justify-center text-muted-foreground">
                暂无数据
              </div>
            )}
          </CardContent>
        </Card>

        {/* Daily Trend */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">最近7天决策趋势</CardTitle>
          </CardHeader>
          <CardContent>
            {dailyTrend.length > 0 ? (
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={dailyTrend}>
                  <XAxis
                    dataKey="date"
                    tickFormatter={(v) => v.slice(5)}
                    fontSize={12}
                  />
                  <YAxis fontSize={12} allowDecimals={false} />
                  <Tooltip
                    labelFormatter={(v) => `日期: ${v}`}
                    formatter={(v: number) => [`${v} 次`, "决策数"]}
                  />
                  <Bar dataKey="count" fill="#3b82f6" radius={[4, 4, 0, 0]} />
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

      {/* Confidence & Symbol Distribution */}
      <div className="grid gap-4 lg:grid-cols-2">
        {/* Confidence Distribution */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">置信度分布</CardTitle>
          </CardHeader>
          <CardContent>
            {confidenceDistribution.length > 0 ? (
              <ResponsiveContainer width="100%" height={200}>
                <BarChart
                  data={confidenceDistribution}
                  layout="vertical"
                  margin={{ left: 20 }}
                >
                  <XAxis type="number" fontSize={12} allowDecimals={false} />
                  <YAxis
                    type="category"
                    dataKey="range"
                    fontSize={12}
                    width={60}
                  />
                  <Tooltip
                    formatter={(v: number) => [`${v} 次`, "决策数"]}
                  />
                  <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                    {confidenceDistribution.map((entry) => (
                      <Cell
                        key={entry.range}
                        fill={CONFIDENCE_COLORS[entry.range] || "#94a3b8"}
                      />
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

        {/* Symbol Distribution */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">交易对分布 (Top 5)</CardTitle>
          </CardHeader>
          <CardContent>
            {symbolDistribution.length > 0 ? (
              <ResponsiveContainer width="100%" height={200}>
                <PieChart>
                  <Pie
                    data={symbolDistribution}
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={80}
                    paddingAngle={2}
                    dataKey="count"
                    nameKey="symbol"
                    label={({ symbol, percent }) =>
                      `${symbol} ${(percent * 100).toFixed(0)}%`
                    }
                    labelLine={false}
                  >
                    {symbolDistribution.map((_, index) => (
                      <Cell
                        key={index}
                        fill={SYMBOL_COLORS[index % SYMBOL_COLORS.length]}
                      />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-[200px] items-center justify-center text-muted-foreground">
                暂无数据
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Hourly Distribution & Confidence Trend */}
      <div className="grid gap-4 lg:grid-cols-2">
        {/* Hourly Distribution */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">每小时决策分布</CardTitle>
          </CardHeader>
          <CardContent>
            {hourlyDistribution.some((h) => h.count > 0) ? (
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={hourlyDistribution}>
                  <XAxis
                    dataKey="hour"
                    fontSize={10}
                    tickFormatter={(v) => v.slice(0, 2)}
                    interval={2}
                  />
                  <YAxis fontSize={12} allowDecimals={false} />
                  <Tooltip
                    labelFormatter={(v) => `时间: ${v}`}
                    formatter={(v: number) => [`${v} 次`, "决策数"]}
                  />
                  <Bar dataKey="count" radius={[2, 2, 0, 0]}>
                    {hourlyDistribution.map((entry, index) => (
                      <Cell
                        key={index}
                        fill={
                          entry.count > 5
                            ? "#22c55e"
                            : entry.count > 2
                              ? "#eab308"
                              : entry.count > 0
                                ? "#3b82f6"
                                : "#334155"
                        }
                      />
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

        {/* Confidence Trend */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">置信度趋势 (7天)</CardTitle>
          </CardHeader>
          <CardContent>
            {confidenceTrend.length > 0 ? (
              <ResponsiveContainer width="100%" height={200}>
                <AreaChart data={confidenceTrend}>
                  <XAxis
                    dataKey="date"
                    tickFormatter={(v) => v.slice(5)}
                    fontSize={12}
                  />
                  <YAxis fontSize={12} domain={[0, 100]} />
                  <Tooltip
                    labelFormatter={(v) => `日期: ${v}`}
                    formatter={(v: number, name: string) => [
                      name === "avgConfidence" ? `${v}%` : `${v} 次`,
                      name === "avgConfidence" ? "平均置信度" : "决策数",
                    ]}
                  />
                  <Area
                    type="monotone"
                    dataKey="avgConfidence"
                    stroke="#8b5cf6"
                    fill="#8b5cf6"
                    fillOpacity={0.3}
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-[200px] items-center justify-center text-muted-foreground">
                暂无数据
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* LLM Distribution & Long/Short Trend */}
      <div className="grid gap-4 lg:grid-cols-2">
        {/* LLM Provider Distribution */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">LLM 提供商分布</CardTitle>
          </CardHeader>
          <CardContent>
            {llmDistribution.length > 0 ? (
              <ResponsiveContainer width="100%" height={200}>
                <PieChart>
                  <Pie
                    data={llmDistribution}
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={80}
                    paddingAngle={2}
                    dataKey="value"
                    label={({ name, percent }) =>
                      `${name} ${(percent * 100).toFixed(0)}%`
                    }
                    labelLine={false}
                  >
                    {llmDistribution.map((_, index) => (
                      <Cell
                        key={index}
                        fill={LLM_COLORS[index % LLM_COLORS.length]}
                      />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-[200px] items-center justify-center text-muted-foreground">
                暂无数据
              </div>
            )}
          </CardContent>
        </Card>

        {/* Long/Short Trend */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">多空趋势 (7天)</CardTitle>
          </CardHeader>
          <CardContent>
            {longShortTrend.length > 0 ? (
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={longShortTrend}>
                  <XAxis
                    dataKey="date"
                    tickFormatter={(v) => v.slice(5)}
                    fontSize={12}
                  />
                  <YAxis fontSize={12} allowDecimals={false} />
                  <Tooltip
                    labelFormatter={(v) => `日期: ${v}`}
                    formatter={(v: number, name: string) => {
                      const labels: Record<string, string> = {
                        long: "做多",
                        short: "做空",
                        hold: "观望",
                      };
                      return [`${v} 次`, labels[name] || name];
                    }}
                  />
                  <Legend
                    formatter={(value) => {
                      const labels: Record<string, string> = {
                        long: "做多",
                        short: "做空",
                        hold: "观望",
                      };
                      return labels[value] || value;
                    }}
                  />
                  <Bar dataKey="long" stackId="a" fill="#22c55e" />
                  <Bar dataKey="short" stackId="a" fill="#ef4444" />
                  <Bar dataKey="hold" stackId="a" fill="#94a3b8" />
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

      {/* Position & Recent Decisions */}
      <div className="grid gap-4 lg:grid-cols-2">
        {/* Current Position */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">当前持仓</CardTitle>
          </CardHeader>
          <CardContent>
            {Object.keys(positions).length > 0 ? (
              <div className="space-y-3">
                {Object.entries(positions).map(([symbol, pos]: [string, any]) => (
                  pos && (
                    <div key={symbol} className="rounded-md border p-3">
                      <div className="flex items-center justify-between mb-2">
                        <span className="font-medium">{symbol}</span>
                        <span
                          className={cn(
                            "rounded px-2 py-0.5 text-xs font-medium",
                            pos.side === "long"
                              ? "bg-profit/20 text-profit"
                              : "bg-loss/20 text-loss"
                          )}
                        >
                          {pos.side === "long" ? "做多" : "做空"} {pos.leverage}x
                        </span>
                      </div>
                      <div className="grid grid-cols-2 gap-2 text-sm">
                        <div>
                          <span className="text-muted-foreground">数量: </span>
                          <span className="tabular-nums">{pos.size?.toFixed(4)}</span>
                        </div>
                        <div>
                          <span className="text-muted-foreground">入场价: </span>
                          <span className="tabular-nums">{formatUSD(pos.entry_price)}</span>
                        </div>
                        <div>
                          <span className="text-muted-foreground">标记价: </span>
                          <span className="tabular-nums">{formatUSD(pos.mark_price)}</span>
                        </div>
                        <div>
                          <span className="text-muted-foreground">未实现盈亏: </span>
                          <span className={cn(
                            "tabular-nums font-medium",
                            pos.unrealized_pnl >= 0 ? "text-profit" : "text-loss"
                          )}>
                            {formatUSD(pos.unrealized_pnl)} ({formatPercent(pos.roi)})
                          </span>
                        </div>
                      </div>
                    </div>
                  )
                ))}
              </div>
            ) : (
              <div className="flex h-32 items-center justify-center text-muted-foreground">
                {accountState ? "暂无持仓" : "交易系统离线"}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Recent Decisions */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">最近决策</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {recentDecisions.map((decision) => (
                <div
                  key={decision.id}
                  className="flex items-start justify-between rounded-md border p-3"
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{decision.symbol}</span>
                      <span
                        className={cn(
                          "rounded px-1.5 py-0.5 text-xs font-medium",
                          decision.action.includes("long")
                            ? "bg-profit/20 text-profit"
                            : decision.action.includes("short")
                            ? "bg-loss/20 text-loss"
                            : "bg-muted text-muted-foreground"
                        )}
                      >
                        {formatActionLabel(decision.action)}
                      </span>
                    </div>
                    <p className="text-sm text-muted-foreground line-clamp-1">
                      {decision.reasoningZh || decision.reasoning}
                    </p>
                  </div>
                  <div className="text-right text-sm">
                    <p className="font-medium">{decision.confidence}%</p>
                    <p className="text-muted-foreground">
                      <Clock className="mr-1 inline h-3 w-3" />
                      {formatTimeAgo(decision.createdAt)}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function formatTimeAgo(date: string): string {
  const seconds = Math.floor((Date.now() - new Date(date).getTime()) / 1000);
  if (seconds < 60) return "刚刚";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}分钟前`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}小时前`;
  return `${Math.floor(seconds / 86400)}天前`;
}
