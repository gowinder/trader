import { Link, useSearchParams } from "react-router";
import type { Route } from "./+types/dashboard.backtest";
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card";
import { StatCard } from "~/components/common/StatCard";
import {
  cn,
  formatUSD,
  formatPercent,
  formatDateTime,
  formatDate,
  getPnlColorClass,
} from "~/lib/utils";
import { Check, X, Loader2, DollarSign, TrendingUp, BarChart3 } from "lucide-react";
import { db } from "db";
import { backtests, backtestTrades, backtestEquity } from "db/schema";
import { desc, eq } from "drizzle-orm";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

export async function loader({ request }: Route.LoaderArgs) {
  const url = new URL(request.url);
  const selectedId = url.searchParams.get("id");

  // 获取回测列表（最近20条）
  const backtestList = await db
    .select({
      id: backtests.id,
      createdAt: backtests.createdAt,
      mode: backtests.mode,
      symbol: backtests.symbol,
      startDate: backtests.startDate,
      endDate: backtests.endDate,
      status: backtests.status,
      totalPnl: backtests.totalPnl,
      initialCapital: backtests.initialCapital,
      finalCapital: backtests.finalCapital,
    })
    .from(backtests)
    .orderBy(desc(backtests.createdAt))
    .limit(20);

  let selectedBacktest = null;
  let trades: {
    id: string;
    symbol: string;
    side: string;
    entryTime: string;
    exitTime: string | null;
    entryPrice: number;
    exitPrice: number | null;
    pnl: number | null;
    pnlPercent: number | null;
  }[] = [];
  let equityCurve: { timestamp: string; totalEquity: number }[] = [];

  if (selectedId) {
    // 获取选中回测的详情
    const backtestDetail = await db
      .select()
      .from(backtests)
      .where(eq(backtests.id, selectedId))
      .limit(1);

    if (backtestDetail.length > 0) {
      const bt = backtestDetail[0];
      selectedBacktest = {
        id: bt.id,
        createdAt: bt.createdAt.toISOString(),
        mode: bt.mode,
        symbol: bt.symbol,
        startDate: bt.startDate,
        endDate: bt.endDate,
        status: bt.status,
        progress: bt.progress,
        errorMessage: bt.errorMessage,
        initialCapital: bt.initialCapital ? parseFloat(bt.initialCapital) : 0,
        finalCapital: bt.finalCapital ? parseFloat(bt.finalCapital) : null,
        totalPnl: bt.totalPnl ? parseFloat(bt.totalPnl) : null,
        totalTrades: bt.totalTrades,
        winningTrades: bt.winningTrades,
        maxDrawdown: bt.maxDrawdown ? parseFloat(bt.maxDrawdown) : null,
        sharpeRatio: bt.sharpeRatio ? parseFloat(bt.sharpeRatio) : null,
      };

      // 获取交易记录
      const tradesData = await db
        .select({
          id: backtestTrades.id,
          symbol: backtestTrades.symbol,
          side: backtestTrades.side,
          entryTime: backtestTrades.entryTime,
          exitTime: backtestTrades.exitTime,
          entryPrice: backtestTrades.entryPrice,
          exitPrice: backtestTrades.exitPrice,
          pnl: backtestTrades.pnl,
          pnlPercent: backtestTrades.pnlPercent,
        })
        .from(backtestTrades)
        .where(eq(backtestTrades.backtestId, selectedId))
        .orderBy(desc(backtestTrades.entryTime));

      trades = tradesData.map((t) => ({
        id: t.id,
        symbol: t.symbol,
        side: t.side,
        entryTime: t.entryTime.toISOString(),
        exitTime: t.exitTime ? t.exitTime.toISOString() : null,
        entryPrice: parseFloat(t.entryPrice),
        exitPrice: t.exitPrice ? parseFloat(t.exitPrice) : null,
        pnl: t.pnl ? parseFloat(t.pnl) : null,
        pnlPercent: t.pnlPercent ? parseFloat(t.pnlPercent) : null,
      }));

      // 获取权益曲线
      const equityData = await db
        .select({
          timestamp: backtestEquity.timestamp,
          totalEquity: backtestEquity.totalEquity,
        })
        .from(backtestEquity)
        .where(eq(backtestEquity.backtestId, selectedId))
        .orderBy(backtestEquity.timestamp);

      equityCurve = equityData.map((e) => ({
        timestamp: e.timestamp.toISOString(),
        totalEquity: parseFloat(e.totalEquity),
      }));
    }
  }

  return {
    backtestList: backtestList.map((bt) => ({
      id: bt.id,
      createdAt: bt.createdAt.toISOString(),
      mode: bt.mode,
      symbol: bt.symbol,
      startDate: bt.startDate,
      endDate: bt.endDate,
      status: bt.status,
      totalPnl: bt.totalPnl ? parseFloat(bt.totalPnl) : null,
      initialCapital: bt.initialCapital ? parseFloat(bt.initialCapital) : 0,
      finalCapital: bt.finalCapital ? parseFloat(bt.finalCapital) : null,
    })),
    selectedBacktest,
    trades,
    equityCurve,
  };
}

function StatusBadge({ status }: { status: string }) {
  if (status === "completed")
    return (
      <span className="text-xs text-profit flex items-center gap-1">
        <Check className="h-3 w-3" /> 完成
      </span>
    );
  if (status === "running")
    return (
      <span className="text-xs text-blue-500 flex items-center gap-1">
        <Loader2 className="h-3 w-3 animate-spin" /> 运行中
      </span>
    );
  if (status === "failed")
    return (
      <span className="text-xs text-loss flex items-center gap-1">
        <X className="h-3 w-3" /> 失败
      </span>
    );
  return <span className="text-xs text-muted-foreground">{status}</span>;
}

export default function BacktestPage({ loaderData }: Route.ComponentProps) {
  const { backtestList, selectedBacktest, trades, equityCurve } = loaderData;
  const [searchParams] = useSearchParams();
  const selectedId = searchParams.get("id");

  return (
    <div className="flex h-full gap-4">
      {/* 左侧回测列表 */}
      <div className="w-80 shrink-0 overflow-y-auto border-r pr-4">
        <h2 className="mb-4 text-lg font-semibold">回测列表</h2>
        <div className="space-y-2">
          {backtestList.length === 0 ? (
            <div className="py-8 text-center text-muted-foreground">
              暂无回测记录
            </div>
          ) : (
            backtestList.map((bt) => {
              const pnlPercent =
                bt.totalPnl !== null && bt.initialCapital > 0
                  ? (bt.totalPnl / bt.initialCapital) * 100
                  : null;
              return (
                <Link
                  key={bt.id}
                  to={`?id=${bt.id}`}
                  className={cn(
                    "block rounded-lg border p-3 transition-colors hover:bg-muted/50",
                    selectedId === bt.id && "border-primary bg-muted/50"
                  )}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium">
                      {bt.symbol || "组合"}
                    </span>
                    <StatusBadge status={bt.status} />
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    {bt.startDate} ~ {bt.endDate}
                  </div>
                  {bt.status === "completed" && bt.totalPnl !== null && (
                    <div className="mt-2 flex items-center justify-between">
                      <span className={cn("text-sm font-medium", getPnlColorClass(bt.totalPnl))}>
                        {formatUSD(bt.totalPnl)}
                      </span>
                      {pnlPercent !== null && (
                        <span className={cn("text-xs", getPnlColorClass(pnlPercent))}>
                          {formatPercent(pnlPercent)}
                        </span>
                      )}
                    </div>
                  )}
                </Link>
              );
            })
          )}
        </div>
      </div>

      {/* 右侧详情 */}
      <div className="flex-1 overflow-y-auto">
        {!selectedBacktest ? (
          <div className="flex h-full items-center justify-center text-muted-foreground">
            请选择一个回测查看详情
          </div>
        ) : (
          <div className="space-y-4">
            {/* 标题 */}
            <div>
              <h1 className="text-2xl font-bold">
                {selectedBacktest.symbol || "组合回测"}
              </h1>
              <p className="text-sm text-muted-foreground">
                {selectedBacktest.startDate} ~ {selectedBacktest.endDate}
              </p>
            </div>

            {/* 统计卡片 */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
              <StatCard
                label="初始资金"
                value={formatUSD(selectedBacktest.initialCapital)}
                icon={DollarSign}
              />
              <StatCard
                label="最终资金"
                value={
                  selectedBacktest.finalCapital !== null
                    ? formatUSD(selectedBacktest.finalCapital)
                    : "-"
                }
                icon={DollarSign}
                variant={
                  selectedBacktest.finalCapital !== null &&
                  selectedBacktest.finalCapital > selectedBacktest.initialCapital
                    ? "profit"
                    : selectedBacktest.finalCapital !== null &&
                      selectedBacktest.finalCapital < selectedBacktest.initialCapital
                    ? "loss"
                    : "default"
                }
              />
              <StatCard
                label="总盈亏"
                value={
                  selectedBacktest.totalPnl !== null
                    ? formatUSD(selectedBacktest.totalPnl)
                    : "-"
                }
                icon={TrendingUp}
                variant={
                  selectedBacktest.totalPnl !== null && selectedBacktest.totalPnl > 0
                    ? "profit"
                    : selectedBacktest.totalPnl !== null && selectedBacktest.totalPnl < 0
                    ? "loss"
                    : "default"
                }
              />
              <StatCard
                label="夏普比率"
                value={
                  selectedBacktest.sharpeRatio !== null
                    ? selectedBacktest.sharpeRatio.toFixed(2)
                    : "-"
                }
                icon={BarChart3}
              />
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
                        tickFormatter={(v) => formatDate(v)}
                        fontSize={12}
                      />
                      <YAxis
                        fontSize={12}
                        tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
                      />
                      <Tooltip
                        labelFormatter={(v) => formatDateTime(v as string)}
                        formatter={(v: number) => [formatUSD(v), "权益"]}
                      />
                      <Area
                        type="monotone"
                        dataKey="totalEquity"
                        stroke="#3b82f6"
                        fill="#3b82f6"
                        fillOpacity={0.3}
                      />
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
                <CardTitle className="text-base">
                  交易记录 ({trades.length})
                </CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b bg-muted/50">
                        <th className="px-4 py-3 text-left text-sm font-medium">
                          交易对
                        </th>
                        <th className="px-4 py-3 text-left text-sm font-medium">
                          方向
                        </th>
                        <th className="px-4 py-3 text-left text-sm font-medium">
                          入场价
                        </th>
                        <th className="px-4 py-3 text-left text-sm font-medium">
                          出场价
                        </th>
                        <th className="px-4 py-3 text-left text-sm font-medium">
                          盈亏
                        </th>
                        <th className="px-4 py-3 text-left text-sm font-medium">
                          收益率
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {trades.length === 0 ? (
                        <tr>
                          <td
                            colSpan={6}
                            className="px-4 py-8 text-center text-muted-foreground"
                          >
                            暂无交易记录
                          </td>
                        </tr>
                      ) : (
                        trades.map((trade) => (
                          <tr
                            key={trade.id}
                            className="border-b transition-colors hover:bg-muted/50"
                          >
                            <td className="px-4 py-3 text-sm font-medium">
                              {trade.symbol}
                            </td>
                            <td className="px-4 py-3">
                              <span
                                className={cn(
                                  "rounded px-2 py-1 text-xs font-medium",
                                  trade.side === "long"
                                    ? "bg-profit/20 text-profit"
                                    : "bg-loss/20 text-loss"
                                )}
                              >
                                {trade.side === "long" ? "做多" : "做空"}
                              </span>
                            </td>
                            <td className="px-4 py-3 text-sm tabular-nums">
                              {formatUSD(trade.entryPrice)}
                            </td>
                            <td className="px-4 py-3 text-sm tabular-nums">
                              {trade.exitPrice !== null
                                ? formatUSD(trade.exitPrice)
                                : "-"}
                            </td>
                            <td className="px-4 py-3 text-sm tabular-nums">
                              {trade.pnl !== null ? (
                                <span className={getPnlColorClass(trade.pnl)}>
                                  {formatUSD(trade.pnl)}
                                </span>
                              ) : (
                                "-"
                              )}
                            </td>
                            <td className="px-4 py-3 text-sm tabular-nums">
                              {trade.pnlPercent !== null ? (
                                <span className={getPnlColorClass(trade.pnlPercent)}>
                                  {formatPercent(trade.pnlPercent)}
                                </span>
                              ) : (
                                "-"
                              )}
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </div>
  );
}
