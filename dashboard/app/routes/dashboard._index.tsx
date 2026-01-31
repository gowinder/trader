import type { Route } from "./+types/dashboard._index";
import { StatCard } from "~/components/common/StatCard";
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card";
import { formatUSD, cn } from "~/lib/utils";
import { TrendingUp, TrendingDown, Target, Activity, Clock } from "lucide-react";
import { db } from "db";
import { decisions, dailyStats } from "db/schema";
import { desc, sql, eq, gte } from "drizzle-orm";
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

  const stats = todayStatsData[0] || {
    totalTrades: 0,
    winningTrades: 0,
    totalPnl: 0,
  };
  const winRate =
    stats.totalTrades > 0
      ? Math.round((stats.winningTrades / stats.totalTrades) * 100)
      : 0;

  return {
    todayStats: {
      pnl: Number(stats.totalPnl) || 0,
      pnlPct: 0, // 需要计算
      trades: stats.totalTrades,
      winningTrades: stats.winningTrades,
      winRate,
    },
    totalDecisions,
    todayDecisions,
    recentDecisions: recentDecisionsData.map((d) => ({
      id: d.id,
      createdAt: d.createdAt.toISOString(),
      symbol: d.symbol,
      action: d.action,
      confidence: d.confidence,
      reasoning: d.reasoning,
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
  } = loaderData;

  return (
    <div className="space-y-6">
      {/* Stats Grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="总决策数"
          value={`${totalDecisions}`}
          icon={Activity}
        />
        <StatCard
          label="今日决策"
          value={`${todayDecisions}`}
          icon={Clock}
        />
        <StatCard
          label="今日交易"
          value={`${todayStats.trades} 笔`}
          icon={Target}
        />
        <StatCard
          label="今日盈亏"
          value={formatUSD(todayStats.pnl)}
          variant={todayStats.pnl >= 0 ? "profit" : "loss"}
          icon={todayStats.pnl >= 0 ? TrendingUp : TrendingDown}
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

      {/* Position & Recent Decisions */}
      <div className="grid gap-4 lg:grid-cols-2">
        {/* Current Position */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">当前持仓</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex h-32 items-center justify-center text-muted-foreground">
              暂无持仓数据（需要连接交易所 API）
            </div>
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
                      {decision.reasoning}
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
