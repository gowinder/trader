import { useState } from "react";
import { Link } from "react-router";
import type { Route } from "./+types/dashboard.positions";
import { StatCard } from "~/components/common/StatCard";
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card";
import { Button } from "~/components/ui/button";
import { formatUSD, formatPercent, formatDateTime, cn } from "~/lib/utils";
import {
  Activity,
  Target,
  TrendingUp,
  Percent,
  ArrowUpRight,
  ArrowDownRight,
  ChevronDown,
  ChevronUp,
  ExternalLink,
} from "lucide-react";
import { db } from "db";
import { positionHistory, decisions as decisionsTable } from "db/schema";
import { desc, eq, and, gte, lte, or, sql, inArray } from "drizzle-orm";

interface DecisionSummary {
  id: string;
  createdAt: string;
  symbol: string;
  action: string;
  confidence: number;
  entryPrice: number | null;
  stopLoss: number | null;
  takeProfit: number | null;
  reasoning: string | null;
  llmProvider: string | null;
  strategyPreset: string | null;
}

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

  // 收集所有仓位的关联决策ID和时间范围
  const allPositions = [...openPositions, ...closedPositions];

  // 收集所有直接关联的决策ID
  const directDecisionIds = allPositions
    .flatMap((p) => [p.entryDecisionId, p.exitDecisionId])
    .filter((id): id is string => id !== null);

  // 查询所有相关决策：直接关联 + 同symbol时间范围内的决策
  const decisionConditions = [];

  // 直接关联的决策
  if (directDecisionIds.length > 0) {
    decisionConditions.push(inArray(decisionsTable.id, directDecisionIds));
  }

  // 每个仓位时间范围内同symbol的决策
  for (const p of allPositions) {
    const endTime = p.exitTime || new Date();
    decisionConditions.push(
      and(
        eq(decisionsTable.symbol, p.symbol),
        gte(decisionsTable.createdAt, p.entryTime),
        lte(decisionsTable.createdAt, endTime)
      )
    );
  }

  let allDecisions: DecisionSummary[] = [];
  if (decisionConditions.length > 0) {
    const rows = await db
      .select({
        id: decisionsTable.id,
        createdAt: decisionsTable.createdAt,
        symbol: decisionsTable.symbol,
        action: decisionsTable.action,
        confidence: decisionsTable.confidence,
        entryPrice: decisionsTable.entryPrice,
        stopLoss: decisionsTable.stopLoss,
        takeProfit: decisionsTable.takeProfit,
        reasoning: decisionsTable.reasoning,
        llmProvider: decisionsTable.llmProvider,
        strategyPreset: decisionsTable.strategyPreset,
      })
      .from(decisionsTable)
      .where(or(...decisionConditions))
      .orderBy(desc(decisionsTable.createdAt));

    allDecisions = rows.map((d) => ({
      id: d.id,
      createdAt: d.createdAt.toISOString(),
      symbol: d.symbol,
      action: d.action,
      confidence: d.confidence,
      entryPrice: d.entryPrice ? parseFloat(d.entryPrice) : null,
      stopLoss: d.stopLoss ? parseFloat(d.stopLoss) : null,
      takeProfit: d.takeProfit ? parseFloat(d.takeProfit) : null,
      reasoning: d.reasoning,
      llmProvider: d.llmProvider,
      strategyPreset: d.strategyPreset,
    }));
  }

  // 将决策按仓位分组
  const positionDecisionsMap: Record<string, DecisionSummary[]> = {};
  for (const p of allPositions) {
    const endTime = p.exitTime ? new Date(p.exitTime).getTime() : Date.now();
    const startTime = new Date(p.entryTime).getTime();

    // 匹配条件：直接关联 或 同symbol+时间范围
    const matched = allDecisions.filter((d) => {
      if (d.id === p.entryDecisionId || d.id === p.exitDecisionId) return true;
      if (d.symbol !== p.symbol) return false;
      const dTime = new Date(d.createdAt).getTime();
      return dTime >= startTime && dTime <= endTime;
    });

    positionDecisionsMap[p.id] = matched;
  }

  const serializePosition = (p: typeof allPositions[0]) => ({
    ...p,
    entryTime: p.entryTime.toISOString(),
    exitTime: p.exitTime?.toISOString(),
    entryPrice: Number(p.entryPrice),
    exitPrice: p.exitPrice ? Number(p.exitPrice) : null,
    entrySize: Number(p.entrySize),
    leverage: p.leverage ? Number(p.leverage) : null,
    realizedPnl: p.realizedPnl ? Number(p.realizedPnl) : null,
    pnlPercent: p.pnlPercent ? Number(p.pnlPercent) : null,
  });

  return {
    openPositions: openPositions.map(serializePosition),
    closedPositions: closedPositions.map(serializePosition),
    positionDecisions: positionDecisionsMap,
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
  const { openPositions, closedPositions, stats, positionDecisions } = loaderData;
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  const toggleExpand = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

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
                    <th className="pb-3 pl-1 font-medium w-8"></th>
                    <th className="pb-3 font-medium">交易对</th>
                    <th className="pb-3 font-medium">方向</th>
                    <th className="pb-3 font-medium text-right">入场价</th>
                    <th className="pb-3 font-medium text-right">数量</th>
                    <th className="pb-3 font-medium text-right">杠杆</th>
                    <th className="pb-3 font-medium text-right">入场时间</th>
                  </tr>
                </thead>
                <tbody>
                  {openPositions.map((position) => {
                    const decisions = positionDecisions[position.id] || [];
                    const isExpanded = expandedIds.has(position.id);
                    return (
                      <PositionRow
                        key={position.id}
                        position={position}
                        decisions={decisions}
                        isExpanded={isExpanded}
                        onToggle={() => toggleExpand(position.id)}
                        columns="open"
                      />
                    );
                  })}
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
                    <th className="pb-3 pl-1 font-medium w-8"></th>
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
                  {closedPositions.map((position) => {
                    const decisions = positionDecisions[position.id] || [];
                    const isExpanded = expandedIds.has(position.id);
                    return (
                      <PositionRow
                        key={position.id}
                        position={position}
                        decisions={decisions}
                        isExpanded={isExpanded}
                        onToggle={() => toggleExpand(position.id)}
                        columns="closed"
                      />
                    );
                  })}
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

function PositionRow({
  position,
  decisions,
  isExpanded,
  onToggle,
  columns,
}: {
  position: any;
  decisions: DecisionSummary[];
  isExpanded: boolean;
  onToggle: () => void;
  columns: "open" | "closed";
}) {
  const colSpan = columns === "open" ? 7 : 8;

  return (
    <>
      <tr
        className={cn(
          "border-b cursor-pointer transition-colors hover:bg-muted/50",
          isExpanded && "bg-muted/30"
        )}
        onClick={onToggle}
      >
        <td className="py-3 pl-1">
          {decisions.length > 0 ? (
            isExpanded ? (
              <ChevronUp className="h-4 w-4 text-muted-foreground" />
            ) : (
              <ChevronDown className="h-4 w-4 text-muted-foreground" />
            )
          ) : null}
        </td>
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
        {columns === "open" ? (
          <>
            <td className="py-3 text-right tabular-nums">
              {position.entrySize.toFixed(4)}
            </td>
            <td className="py-3 text-right tabular-nums">
              {position.leverage ? `${position.leverage}x` : "-"}
            </td>
            <td className="py-3 text-right text-muted-foreground">
              {formatDateTime(position.entryTime)}
            </td>
          </>
        ) : (
          <>
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
          </>
        )}
      </tr>
      {isExpanded && (
        <tr>
          <td colSpan={colSpan} className="bg-muted/20 px-4 py-3">
            {decisions.length > 0 ? (
              <div className="space-y-2">
                <div className="text-xs font-medium text-muted-foreground mb-2">
                  关联决策记录 ({decisions.length})
                </div>
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-left text-muted-foreground">
                      <th className="pb-2 font-medium">时间</th>
                      <th className="pb-2 font-medium">动作</th>
                      <th className="pb-2 font-medium">置信度</th>
                      <th className="pb-2 font-medium text-right">入场价</th>
                      <th className="pb-2 font-medium text-right">止损</th>
                      <th className="pb-2 font-medium text-right">止盈</th>
                      <th className="pb-2 font-medium">策略</th>
                      <th className="pb-2 font-medium">理由</th>
                      <th className="pb-2 font-medium w-8"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {decisions.map((d) => (
                      <tr key={d.id} className="border-t border-border/50">
                        <td className="py-2 tabular-nums">
                          {formatDateTime(d.createdAt)}
                        </td>
                        <td className="py-2">
                          <span
                            className={cn(
                              "rounded px-1.5 py-0.5 text-xs font-medium",
                              d.action.includes("long")
                                ? "bg-profit/20 text-profit"
                                : d.action.includes("short")
                                  ? "bg-loss/20 text-loss"
                                  : "bg-muted text-muted-foreground"
                            )}
                          >
                            {formatAction(d.action)}
                          </span>
                        </td>
                        <td className="py-2">
                          <div className="flex items-center gap-1">
                            <div className="h-1.5 w-10 overflow-hidden rounded-full bg-muted">
                              <div
                                className={cn(
                                  "h-full",
                                  d.confidence >= 80
                                    ? "bg-green-500"
                                    : d.confidence >= 60
                                      ? "bg-yellow-500"
                                      : "bg-red-500"
                                )}
                                style={{ width: `${d.confidence}%` }}
                              />
                            </div>
                            <span className="tabular-nums">{d.confidence}%</span>
                          </div>
                        </td>
                        <td className="py-2 text-right tabular-nums">
                          {d.entryPrice ? formatUSD(d.entryPrice) : "-"}
                        </td>
                        <td className="py-2 text-right tabular-nums text-loss">
                          {d.stopLoss ? formatUSD(d.stopLoss) : "-"}
                        </td>
                        <td className="py-2 text-right tabular-nums text-profit">
                          {d.takeProfit ? formatUSD(d.takeProfit) : "-"}
                        </td>
                        <td className="py-2">
                          {d.strategyPreset ? (
                            <span className="rounded bg-muted px-1.5 py-0.5 text-xs">
                              {formatPresetName(d.strategyPreset)}
                            </span>
                          ) : (
                            "-"
                          )}
                        </td>
                        <td className="max-w-[200px] py-2 text-muted-foreground">
                          <p className="truncate" title={d.reasoning ?? undefined}>
                            {d.reasoning ?? "-"}
                          </p>
                        </td>
                        <td className="py-2">
                          <Link
                            to={`/dashboard/decisions/${d.id}`}
                            onClick={(e) => e.stopPropagation()}
                          >
                            <Button variant="ghost" size="sm" className="h-6 w-6 p-0">
                              <ExternalLink className="h-3 w-3" />
                            </Button>
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="text-xs text-muted-foreground">暂无关联决策记录</div>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

function formatAction(action: string): string {
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

function formatPresetName(name: string): string {
  const map: Record<string, string> = {
    steady_trend: "稳健趋势",
    aggressive_trend: "激进趋势",
    range_harvest: "震荡收割",
    breakout_hunter: "突破猎手",
    mild_scalping: "温和剥头皮",
    aggressive_scalping: "激进剥头皮",
    balanced_conservative: "均衡保守",
  };
  return map[name] || name;
}
