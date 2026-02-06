import type { Route } from "./+types/dashboard.positions";
import { StatCard } from "~/components/common/StatCard";
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card";
import { formatUSD, formatPercent, formatDateTime, cn } from "~/lib/utils";
import { Activity, Target, TrendingUp, Percent, ArrowUpRight, ArrowDownRight } from "lucide-react";
import { db } from "db";
import { positionHistory } from "db/schema";
import { desc, eq, sql } from "drizzle-orm";

export async function loader(_args: Route.LoaderArgs) {
  // 当前持仓（status = "open"）
  const openPositions = await db
    .select()
    .from(positionHistory)
    .where(eq(positionHistory.status, "open"))
    .orderBy(desc(positionHistory.entryTime));

  // 历史持仓（status = "closed"），限制50条
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

export default function PositionsPage({ loaderData }: Route.ComponentProps) {
  const { openPositions, closedPositions, stats } = loaderData;

  return (
    <div className="space-y-6">
      {/* 统计卡片 */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="总交易数"
          value={`${stats.totalTrades}`}
          icon={Activity}
        />
        <StatCard
          label="胜率"
          value={`${stats.winRate}%`}
          icon={Target}
        />
        <StatCard
          label="总盈亏"
          value={formatUSD(stats.totalPnl)}
          variant={stats.totalPnl >= 0 ? "profit" : "loss"}
          icon={TrendingUp}
        />
        <StatCard
          label="平均收益率"
          value={formatPercent(stats.avgPnlPercent)}
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
                    <th className="pb-3 font-medium">交易对</th>
                    <th className="pb-3 font-medium">方向</th>
                    <th className="pb-3 font-medium text-right">入场价</th>
                    <th className="pb-3 font-medium text-right">数量</th>
                    <th className="pb-3 font-medium text-right">杠杆</th>
                    <th className="pb-3 font-medium text-right">入场时间</th>
                  </tr>
                </thead>
                <tbody>
                  {openPositions.map((position) => (
                    <tr key={position.id} className="border-b last:border-0">
                      <td className="py-3 font-medium">{position.symbol}</td>
                      <td className="py-3">
                        <span
                          className={cn(
                            "inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium",
                            position.side === "long"
                              ? "bg-profit/20 text-profit"
                              : "bg-loss/20 text-loss"
                          )}
                        >
                          {position.side === "long" ? (
                            <ArrowUpRight className="h-3 w-3" />
                          ) : (
                            <ArrowDownRight className="h-3 w-3" />
                          )}
                          {position.side === "long" ? "做多" : "做空"}
                        </span>
                      </td>
                      <td className="py-3 text-right tabular-nums">
                        {formatUSD(position.entryPrice)}
                      </td>
                      <td className="py-3 text-right tabular-nums">
                        {position.entrySize.toFixed(4)}
                      </td>
                      <td className="py-3 text-right tabular-nums">
                        {position.leverage ? `${position.leverage}x` : "-"}
                      </td>
                      <td className="py-3 text-right text-muted-foreground">
                        {formatDateTime(position.entryTime)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="flex h-32 items-center justify-center text-muted-foreground">
              暂无当前持仓
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
                    <th className="pb-3 font-medium">交易对</th>
                    <th className="pb-3 font-medium">方向</th>
                    <th className="pb-3 font-medium text-right">入场价</th>
                    <th className="pb-3 font-medium text-right">出场价</th>
                    <th className="pb-3 font-medium text-right">盈亏</th>
                    <th className="pb-3 font-medium text-right">收益率</th>
                    <th className="pb-3 font-medium text-right">平仓时间</th>
                  </tr>
                </thead>
                <tbody>
                  {closedPositions.map((position) => (
                    <tr key={position.id} className="border-b last:border-0">
                      <td className="py-3 font-medium">{position.symbol}</td>
                      <td className="py-3">
                        <span
                          className={cn(
                            "inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium",
                            position.side === "long"
                              ? "bg-profit/20 text-profit"
                              : "bg-loss/20 text-loss"
                          )}
                        >
                          {position.side === "long" ? (
                            <ArrowUpRight className="h-3 w-3" />
                          ) : (
                            <ArrowDownRight className="h-3 w-3" />
                          )}
                          {position.side === "long" ? "做多" : "做空"}
                        </span>
                      </td>
                      <td className="py-3 text-right tabular-nums">
                        {formatUSD(position.entryPrice)}
                      </td>
                      <td className="py-3 text-right tabular-nums">
                        {position.exitPrice ? formatUSD(position.exitPrice) : "-"}
                      </td>
                      <td
                        className={cn(
                          "py-3 text-right tabular-nums font-medium",
                          position.realizedPnl !== null && position.realizedPnl > 0
                            ? "text-profit"
                            : position.realizedPnl !== null && position.realizedPnl < 0
                              ? "text-loss"
                              : ""
                        )}
                      >
                        {position.realizedPnl !== null
                          ? formatUSD(position.realizedPnl)
                          : "-"}
                      </td>
                      <td
                        className={cn(
                          "py-3 text-right tabular-nums",
                          position.pnlPercent !== null && position.pnlPercent > 0
                            ? "text-profit"
                            : position.pnlPercent !== null && position.pnlPercent < 0
                              ? "text-loss"
                              : ""
                        )}
                      >
                        {position.pnlPercent !== null
                          ? formatPercent(position.pnlPercent)
                          : "-"}
                      </td>
                      <td className="py-3 text-right text-muted-foreground">
                        {position.exitTime ? formatDateTime(position.exitTime) : "-"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="flex h-32 items-center justify-center text-muted-foreground">
              暂无历史持仓
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
