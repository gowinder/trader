import type { Route } from "./+types/dashboard.analytics";
import { StatCard } from "~/components/common/StatCard";
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card";
import { formatUSD, formatPercent, cn } from "~/lib/utils";
import { TrendingUp, TrendingDown, Target, BarChart3 } from "lucide-react";
import { db } from "db";
import { positionHistory, dailyStats } from "db/schema";
import { sql, asc, isNotNull } from "drizzle-orm";
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

export async function loader(_args: Route.LoaderArgs) {
  // 从 positionHistory 获取已完成交易的统计
  const completedTrades = await db
    .select({
      id: positionHistory.id,
      symbol: positionHistory.symbol,
      side: positionHistory.side,
      realizedPnl: positionHistory.realizedPnl,
    })
    .from(positionHistory)
    .where(isNotNull(positionHistory.exitTime));

  // 总体统计
  const totalTrades = completedTrades.length;
  const winningTrades = completedTrades.filter(
    (t) => Number(t.realizedPnl) > 0
  ).length;
  const losingTrades = completedTrades.filter(
    (t) => Number(t.realizedPnl) < 0
  ).length;
  const totalPnl = completedTrades.reduce(
    (sum, t) => sum + Number(t.realizedPnl || 0),
    0
  );

  const winningPnls = completedTrades
    .filter((t) => Number(t.realizedPnl) > 0)
    .map((t) => Number(t.realizedPnl));
  const losingPnls = completedTrades
    .filter((t) => Number(t.realizedPnl) < 0)
    .map((t) => Number(t.realizedPnl));

  const avgWin =
    winningPnls.length > 0
      ? winningPnls.reduce((a, b) => a + b, 0) / winningPnls.length
      : 0;
  const avgLoss =
    losingPnls.length > 0
      ? losingPnls.reduce((a, b) => a + b, 0) / losingPnls.length
      : 0;
  const maxWin = winningPnls.length > 0 ? Math.max(...winningPnls) : 0;
  const maxLoss = losingPnls.length > 0 ? Math.min(...losingPnls) : 0;

  // 胜率
  const winRate = totalTrades > 0 ? (winningTrades / totalTrades) * 100 : 0;

  // 盈亏比 (Profit Factor)
  const totalWinAmount = winningPnls.reduce((a, b) => a + b, 0);
  const totalLossAmount = Math.abs(losingPnls.reduce((a, b) => a + b, 0));
  const profitFactor =
    totalLossAmount > 0 ? totalWinAmount / totalLossAmount : totalWinAmount > 0 ? Infinity : 0;

  // 每日盈亏曲线（从 dailyStats 获取）
  const dailyStatsData = await db
    .select({
      date: dailyStats.date,
      totalPnl: sql<number>`COALESCE(SUM(${dailyStats.totalPnl}::numeric), 0)`,
    })
    .from(dailyStats)
    .groupBy(dailyStats.date)
    .orderBy(asc(dailyStats.date));

  // 计算累计盈亏
  let cumPnl = 0;
  const pnlCurve = dailyStatsData.map((d) => {
    cumPnl += Number(d.totalPnl);
    return {
      date: d.date,
      dailyPnl: Number(d.totalPnl),
      cumulativePnl: cumPnl,
    };
  });

  // 按交易对统计
  const symbolStatsMap = new Map<
    string,
    { trades: number; pnl: number; wins: number }
  >();
  for (const t of completedTrades) {
    const existing = symbolStatsMap.get(t.symbol) || {
      trades: 0,
      pnl: 0,
      wins: 0,
    };
    existing.trades += 1;
    existing.pnl += Number(t.realizedPnl || 0);
    if (Number(t.realizedPnl) > 0) existing.wins += 1;
    symbolStatsMap.set(t.symbol, existing);
  }
  const symbolStats = Array.from(symbolStatsMap.entries())
    .map(([symbol, stats]) => ({
      symbol,
      trades: stats.trades,
      pnl: stats.pnl,
      winRate: stats.trades > 0 ? (stats.wins / stats.trades) * 100 : 0,
    }))
    .sort((a, b) => b.pnl - a.pnl);

  // 按方向统计
  const sideStatsMap = new Map<
    string,
    { trades: number; pnl: number; wins: number }
  >();
  for (const t of completedTrades) {
    const side = t.side.toLowerCase();
    const existing = sideStatsMap.get(side) || { trades: 0, pnl: 0, wins: 0 };
    existing.trades += 1;
    existing.pnl += Number(t.realizedPnl || 0);
    if (Number(t.realizedPnl) > 0) existing.wins += 1;
    sideStatsMap.set(side, existing);
  }
  const sideStats = Array.from(sideStatsMap.entries()).map(([side, stats]) => ({
    side,
    trades: stats.trades,
    pnl: stats.pnl,
    winRate: stats.trades > 0 ? (stats.wins / stats.trades) * 100 : 0,
  }));

  return {
    overview: {
      totalTrades,
      winningTrades,
      losingTrades,
      totalPnl,
      avgWin,
      avgLoss,
      maxWin,
      maxLoss,
      winRate,
      profitFactor: profitFactor === Infinity ? 999 : profitFactor,
    },
    pnlCurve,
    symbolStats,
    sideStats,
  };
}

export default function AnalyticsPage({ loaderData }: Route.ComponentProps) {
  const { overview, pnlCurve, symbolStats, sideStats } = loaderData;

  const longStats = sideStats.find((s) => s.side === "long") || {
    trades: 0,
    pnl: 0,
    winRate: 0,
  };
  const shortStats = sideStats.find((s) => s.side === "short") || {
    trades: 0,
    pnl: 0,
    winRate: 0,
  };

  return (
    <div className="space-y-6">
      {/* 核心指标卡片 */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="总交易数"
          value={`${overview.totalTrades} 笔`}
          icon={Target}
        />
        <StatCard
          label="胜率"
          value={formatPercent(overview.winRate, false)}
          icon={BarChart3}
        />
        <StatCard
          label="总盈亏"
          value={formatUSD(overview.totalPnl)}
          variant={overview.totalPnl >= 0 ? "profit" : "loss"}
          icon={overview.totalPnl >= 0 ? TrendingUp : TrendingDown}
        />
        <StatCard
          label="盈亏比"
          value={overview.profitFactor.toFixed(2)}
          variant={overview.profitFactor >= 1 ? "profit" : "loss"}
          icon={BarChart3}
        />
      </div>

      {/* 盈亏详情 + 多空对比 */}
      <div className="grid gap-4 lg:grid-cols-2">
        {/* 盈亏详情 */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">盈亏详情</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-3">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">盈利交易数</span>
                  <span className="font-medium text-profit">
                    {overview.winningTrades}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">平均盈利</span>
                  <span className="font-medium text-profit">
                    {formatUSD(overview.avgWin)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">最大盈利</span>
                  <span className="font-medium text-profit">
                    {formatUSD(overview.maxWin)}
                  </span>
                </div>
              </div>
              <div className="space-y-3">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">亏损交易数</span>
                  <span className="font-medium text-loss">
                    {overview.losingTrades}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">平均亏损</span>
                  <span className="font-medium text-loss">
                    {formatUSD(overview.avgLoss)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">最大亏损</span>
                  <span className="font-medium text-loss">
                    {formatUSD(overview.maxLoss)}
                  </span>
                </div>
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
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-3">
                <div className="text-center mb-2">
                  <span className="text-sm font-medium text-profit">做多</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">交易数</span>
                  <span className="font-medium">{longStats.trades}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">盈亏</span>
                  <span
                    className={cn(
                      "font-medium",
                      longStats.pnl >= 0 ? "text-profit" : "text-loss"
                    )}
                  >
                    {formatUSD(longStats.pnl)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">胜率</span>
                  <span className="font-medium">
                    {formatPercent(longStats.winRate, false)}
                  </span>
                </div>
              </div>
              <div className="space-y-3">
                <div className="text-center mb-2">
                  <span className="text-sm font-medium text-loss">做空</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">交易数</span>
                  <span className="font-medium">{shortStats.trades}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">盈亏</span>
                  <span
                    className={cn(
                      "font-medium",
                      shortStats.pnl >= 0 ? "text-profit" : "text-loss"
                    )}
                  >
                    {formatUSD(shortStats.pnl)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">胜率</span>
                  <span className="font-medium">
                    {formatPercent(shortStats.winRate, false)}
                  </span>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* 累计盈亏曲线 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">累计盈亏曲线</CardTitle>
        </CardHeader>
        <CardContent>
          {pnlCurve.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <AreaChart data={pnlCurve}>
                <XAxis
                  dataKey="date"
                  tickFormatter={(v) => v.slice(5)}
                  fontSize={12}
                />
                <YAxis
                  fontSize={12}
                  tickFormatter={(v) => `$${v.toLocaleString()}`}
                />
                <Tooltip
                  labelFormatter={(v) => `日期: ${v}`}
                  formatter={(v: number, name: string) => {
                    const labels: Record<string, string> = {
                      cumulativePnl: "累计盈亏",
                      dailyPnl: "当日盈亏",
                    };
                    return [formatUSD(v), labels[name] || name];
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="cumulativePnl"
                  stroke="#3b82f6"
                  fill="#3b82f6"
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
            <ResponsiveContainer width="100%" height={Math.max(200, symbolStats.length * 40)}>
              <BarChart data={symbolStats} layout="vertical" margin={{ left: 60 }}>
                <XAxis
                  type="number"
                  fontSize={12}
                  tickFormatter={(v) => `$${v.toLocaleString()}`}
                />
                <YAxis
                  type="category"
                  dataKey="symbol"
                  fontSize={12}
                  width={80}
                />
                <Tooltip
                  formatter={(v: number, name: string) => {
                    if (name === "pnl") return [formatUSD(v), "盈亏"];
                    return [v, name];
                  }}
                  labelFormatter={(v) => `交易对: ${v}`}
                />
                <Bar dataKey="pnl" radius={[0, 4, 4, 0]}>
                  {symbolStats.map((entry, index) => (
                    <Cell
                      key={index}
                      fill={entry.pnl >= 0 ? "#22c55e" : "#ef4444"}
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

      {/* 交易对详情表格 */}
      {symbolStats.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">交易对详情</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b">
                    <th className="text-left py-2 px-3 font-medium">交易对</th>
                    <th className="text-right py-2 px-3 font-medium">交易数</th>
                    <th className="text-right py-2 px-3 font-medium">盈亏</th>
                    <th className="text-right py-2 px-3 font-medium">胜率</th>
                  </tr>
                </thead>
                <tbody>
                  {symbolStats.map((stat) => (
                    <tr key={stat.symbol} className="border-b last:border-0">
                      <td className="py-2 px-3 font-medium">{stat.symbol}</td>
                      <td className="py-2 px-3 text-right">{stat.trades}</td>
                      <td
                        className={cn(
                          "py-2 px-3 text-right font-medium",
                          stat.pnl >= 0 ? "text-profit" : "text-loss"
                        )}
                      >
                        {formatUSD(stat.pnl)}
                      </td>
                      <td className="py-2 px-3 text-right">
                        {formatPercent(stat.winRate, false)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
