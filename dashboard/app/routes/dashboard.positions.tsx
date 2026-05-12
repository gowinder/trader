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
import { positionHistory, decisions as decisionsTable, symbolStrategy, strategyPresets, activeStrategy } from "db/schema";
import { desc, eq, and, gte, lte, or, sql, inArray, isNull } from "drizzle-orm";
import { createClient } from "redis";

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
  reasoningZh: string | null;
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
        reasoningZh: decisionsTable.reasoningZh,
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
      reasoningZh: d.reasoningZh,
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

  // 从 Redis 获取实时持仓数据和当前价格
  let realtimePositions: Record<string, any> = {};
  {
    const redisUrl = process.env.REDIS_URL || "redis://localhost:6379";
    const client = createClient({ url: redisUrl });
    try {
      await client.connect();
      const stateJson = await client.get("trading:account_state");
      if (stateJson) {
        const state = JSON.parse(stateJson);
        const currentPrices: Record<string, number> = state.current_prices ?? {};
        const redisPositions: Record<string, any> = state.positions ?? {};

        // 优先用 Redis 中的持仓数据，否则用当前价格自行计算
        for (const p of openPositions) {
          const rp = redisPositions[p.symbol];
          if (rp && rp.mark_price) {
            realtimePositions[p.symbol] = {
              mark_price: rp.mark_price,
              unrealized_pnl: rp.unrealized_pnl ?? 0,
              roi: rp.roi ?? 0,
            };
          } else if (currentPrices[p.symbol]) {
            const markPrice = currentPrices[p.symbol];
            const entryPrice = Number(p.entryPrice);
            const size = Number(p.entrySize);
            const leverage = p.leverage ? Number(p.leverage) : 1;
            const side = p.side?.toLowerCase();

            const unrealizedPnl = side === "long"
              ? (markPrice - entryPrice) * size
              : (entryPrice - markPrice) * size;
            const margin = leverage > 0 ? (entryPrice * size) / leverage : 0;
            const roi = margin > 0 ? (unrealizedPnl / margin) * 100 : 0;

            realtimePositions[p.symbol] = {
              mark_price: markPrice,
              unrealized_pnl: unrealizedPnl,
              roi,
            };
          }
        }
      }
    } catch (e) {
      console.error("Failed to fetch realtime positions from Redis:", e);
    } finally {
      try { await client.disconnect(); } catch { /* ignore */ }
    }
  }

  // 查询全局策略锁定状态
  let globalLock: { isLocked: boolean; presetName: string; presetDisplayName: string } | null = null;
  try {
    const lockRow = await db
      .select({
        isLocked: activeStrategy.isLocked,
        presetName: strategyPresets.name,
        presetDisplayName: strategyPresets.displayName,
      })
      .from(activeStrategy)
      .innerJoin(strategyPresets, eq(activeStrategy.presetId, strategyPresets.id))
      .where(isNull(activeStrategy.deactivatedAt))
      .orderBy(desc(activeStrategy.activatedAt))
      .limit(1);
    if (lockRow.length > 0 && lockRow[0].isLocked) {
      globalLock = {
        isLocked: true,
        presetName: lockRow[0].presetName,
        presetDisplayName: lockRow[0].presetDisplayName,
      };
    }
  } catch (e) {
    console.error("Failed to query global strategy lock:", e);
  }

  // 获取每个持仓 symbol 的策略配置
  const openSymbols = openPositions.map((p) => p.symbol);
  let symbolStrategyMap: Record<string, { preset_name: string; preset_display_name: string }> = {};
  if (globalLock) {
    // 全局锁定时，所有 symbol 显示锁定的全局策略
    for (const symbol of openSymbols) {
      symbolStrategyMap[symbol] = {
        preset_name: globalLock.presetName,
        preset_display_name: globalLock.presetDisplayName,
      };
    }
  } else if (openSymbols.length > 0) {
    try {
      const ssRows = await db
        .select({
          symbol: symbolStrategy.symbol,
          presetName: strategyPresets.name,
          presetDisplayName: strategyPresets.displayName,
        })
        .from(symbolStrategy)
        .innerJoin(strategyPresets, eq(symbolStrategy.presetId, strategyPresets.id))
        .where(and(
          eq(symbolStrategy.enabled, true),
          inArray(symbolStrategy.symbol, openSymbols)
        ));
      for (const row of ssRows) {
        symbolStrategyMap[row.symbol] = {
          preset_name: row.presetName,
          preset_display_name: row.presetDisplayName,
        };
      }
    } catch (e) {
      console.error("Failed to query symbol strategies:", e);
    }
  }

  // 获取预设列表
  let presetsList: Array<{ name: string; displayName: string; description: string | null }> = [];
  try {
    presetsList = await db
      .select({
        name: strategyPresets.name,
        displayName: strategyPresets.displayName,
        description: strategyPresets.description,
      })
      .from(strategyPresets)
      .orderBy(strategyPresets.name);
  } catch (e) {
    console.error("Failed to query presets:", e);
  }

  const serializePosition = (p: typeof allPositions[0]) => {
    const rt = realtimePositions[p.symbol] || null;
    return {
      ...p,
      entryTime: p.entryTime.toISOString(),
      exitTime: p.exitTime?.toISOString(),
      entryPrice: Number(p.entryPrice),
      exitPrice: p.exitPrice ? Number(p.exitPrice) : null,
      entrySize: Number(p.entrySize),
      leverage: p.leverage ? Number(p.leverage) : null,
      realizedPnl: p.realizedPnl ? Number(p.realizedPnl) : null,
      pnlPercent: p.pnlPercent ? Number(p.pnlPercent) : null,
      // 实时数据
      markPrice: rt?.mark_price ?? null,
      unrealizedPnl: rt?.unrealized_pnl ?? null,
      roi: rt?.roi ?? null,
    };
  };

  return {
    openPositions: openPositions.map(serializePosition),
    closedPositions: closedPositions.map(serializePosition),
    positionDecisions: positionDecisionsMap,
    realtimePositions,
    symbolStrategies: symbolStrategyMap,
    presets: presetsList,
    globalLock,
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
  const { openPositions, closedPositions, stats, positionDecisions, symbolStrategies, presets, globalLock } = loaderData;
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [suggesting, setSuggesting] = useState<Record<string, boolean>>({});
  const [suggestions, setSuggestions] = useState<Record<string, { recommended_preset: string; recommended_display_name: string; reason: string; market_state: string }>>({});
  const [switchingStrategy, setSwitchingStrategy] = useState<Record<string, boolean>>({});

  const handleSuggest = async (symbol: string) => {
    setSuggesting((prev) => ({ ...prev, [symbol]: true }));
    try {
      const triggerRes = await fetch("/api/symbol-strategy-suggest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbols: [symbol] }),
      });
      if (!triggerRes.ok) return;
      const { taskId } = await triggerRes.json();
      for (let i = 0; i < 60; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        const pollRes = await fetch(`/api/symbol-strategy-suggest?taskId=${taskId}`);
        if (!pollRes.ok) continue;
        const result = await pollRes.json();
        if (result.status === "completed" && result.suggestions?.[symbol]) {
          setSuggestions((prev) => ({ ...prev, [symbol]: result.suggestions[symbol] }));
          return;
        }
        if (result.status === "error") return;
      }
    } catch { /* ignore */ } finally {
      setSuggesting((prev) => ({ ...prev, [symbol]: false }));
    }
  };

  const handleSwitchStrategy = async (symbol: string, presetName: string) => {
    setSwitchingStrategy((prev) => ({ ...prev, [symbol]: true }));
    try {
      // Read current configured symbols, update just this one
      const symbolsRes = await fetch("/api/symbols");
      const symbolsJson = await symbolsRes.json();
      const configured = (symbolsJson.configured || []).map((c: any) => ({
        symbol: c.symbol,
        preset_name: c.preset_name,
        config_overrides: c.config_overrides || {},
      }));
      // Update or add the target symbol
      const idx = configured.findIndex((c: any) => c.symbol === symbol);
      if (idx >= 0) {
        configured[idx].preset_name = presetName;
        configured[idx].config_overrides = {};
      } else {
        configured.push({ symbol, preset_name: presetName, config_overrides: {} });
      }
      await fetch("/api/symbols", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ configured }),
      });
      // Clear suggestion after adopting
      setSuggestions((prev) => {
        const next = { ...prev };
        delete next[symbol];
        return next;
      });
    } catch { /* ignore */ } finally {
      setSwitchingStrategy((prev) => ({ ...prev, [symbol]: false }));
    }
  };

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
          tooltip="已平仓的总交易笔数"
        />
        <StatCard
          label="胜率"
          value={`${stats.winRate}%`}
          icon={Target}
          tooltip="盈利交易占总交易的百分比"
        />
        <StatCard
          label="总盈亏"
          value={formatUSD(stats.totalPnl)}
          variant={stats.totalPnl >= 0 ? "profit" : "loss"}
          icon={TrendingUp}
          tooltip="所有已平仓交易的累计盈亏"
        />
        <StatCard
          label="平均收益率"
          value={formatPercent(stats.avgPnlPercent)}
          variant={stats.avgPnlPercent >= 0 ? "profit" : "loss"}
          icon={Percent}
          tooltip="所有已平仓交易的平均收益率百分比"
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
                    <th className="pb-3 font-medium">策略</th>
                    <th className="pb-3 font-medium">方向</th>
                    <th className="pb-3 font-medium text-right">入场价</th>
                    <th className="pb-3 font-medium text-right">数量</th>
                    <th className="pb-3 font-medium text-right">杠杆</th>
                    <th className="pb-3 font-medium text-right">标记价</th>
                    <th className="pb-3 font-medium text-right">未实现盈亏</th>
                    <th className="pb-3 font-medium text-right">收益率</th>
                    <th className="pb-3 font-medium text-right">入场时间</th>
                  </tr>
                </thead>
                <tbody>
                  {openPositions.map((position) => {
                    const decisions = positionDecisions[position.id] || [];
                    const isExpanded = expandedIds.has(position.id);
                    const strategy = symbolStrategies[position.symbol];
                    const suggestion = suggestions[position.symbol];
                    return (
                      <PositionRow
                        key={position.id}
                        position={position}
                        decisions={decisions}
                        isExpanded={isExpanded}
                        onToggle={() => toggleExpand(position.id)}
                        columns="open"
                        strategy={strategy}
                        suggestion={suggestion}
                        presets={presets}
                        onSuggest={() => handleSuggest(position.symbol)}
                        onSwitchStrategy={(presetName) => handleSwitchStrategy(position.symbol, presetName)}
                        isSuggesting={suggesting[position.symbol] || false}
                        isSwitching={switchingStrategy[position.symbol] || false}
                        isGlobalLocked={!!globalLock}
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
  strategy,
  suggestion,
  presets,
  onSuggest,
  onSwitchStrategy,
  isSuggesting,
  isSwitching,
  isGlobalLocked,
}: {
  position: any;
  decisions: DecisionSummary[];
  isExpanded: boolean;
  onToggle: () => void;
  columns: "open" | "closed";
  strategy?: { preset_name: string; preset_display_name: string };
  suggestion?: { recommended_preset: string; recommended_display_name: string; reason: string; market_state: string };
  presets?: Array<{ name: string; displayName: string; description: string | null }>;
  onSuggest?: () => void;
  onSwitchStrategy?: (presetName: string) => void;
  isSuggesting?: boolean;
  isSwitching?: boolean;
  isGlobalLocked?: boolean;
}) {
  const colSpan = columns === "open" ? 11 : 8;

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
          {(decisions.length > 0 || columns === "open") ? (
            isExpanded ? (
              <ChevronUp className="h-4 w-4 text-muted-foreground" />
            ) : (
              <ChevronDown className="h-4 w-4 text-muted-foreground" />
            )
          ) : null}
        </td>
        <td className="py-3 font-medium">{position.symbol}</td>
        {columns === "open" && (
          <td className="py-3">
            {strategy ? (
              <span className="text-[11px] px-2 py-0.5 rounded bg-primary/15 text-blue-400">
                {strategy.preset_display_name}
              </span>
            ) : (
              <span className="text-[11px] text-muted-foreground">-</span>
            )}
          </td>
        )}
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
            <td className="py-3 text-right tabular-nums">
              {position.markPrice ? formatUSD(position.markPrice) : "-"}
            </td>
            <td
              className={cn(
                "py-3 text-right tabular-nums font-medium",
                position.unrealizedPnl != null && position.unrealizedPnl > 0
                  ? "text-profit"
                  : position.unrealizedPnl != null && position.unrealizedPnl < 0
                    ? "text-loss"
                    : ""
              )}
            >
              {position.unrealizedPnl != null
                ? formatUSD(position.unrealizedPnl)
                : "-"}
            </td>
            <td
              className={cn(
                "py-3 text-right tabular-nums",
                position.roi != null && position.roi > 0
                  ? "text-profit"
                  : position.roi != null && position.roi < 0
                    ? "text-loss"
                    : ""
              )}
            >
              {position.roi != null ? formatPercent(position.roi) : "-"}
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
                          <p className="truncate" title={(d.reasoningZh || d.reasoning) ?? undefined}>
                            {d.reasoningZh || d.reasoning || "-"}
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

            {/* Strategy management - only for open positions */}
            {columns === "open" && presets && presets.length > 0 && (
              <div className="mt-3 pt-3 border-t border-border/50">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xs font-medium text-muted-foreground">策略管理</span>
                  {isGlobalLocked && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-yellow-500/20 text-yellow-400 border border-yellow-500/30">
                      全局锁定
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-3 flex-wrap">
                  {/* Current strategy */}
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-muted-foreground">当前:</span>
                    <span className="text-xs font-medium">
                      {strategy?.preset_display_name || "未配置"}
                    </span>
                  </div>

                  {/* Strategy switch dropdown - disabled when globally locked */}
                  <select
                    value={strategy?.preset_name || ""}
                    onChange={(e) => onSwitchStrategy?.(e.target.value)}
                    disabled={isSwitching || isGlobalLocked}
                    className="text-xs rounded border border-input bg-card px-2 py-1 text-foreground focus:outline-none focus:border-primary disabled:opacity-50"
                    onClick={(e) => e.stopPropagation()}
                  >
                    {!strategy && <option value="">选择策略...</option>}
                    {presets.map((p) => (
                      <option key={p.name} value={p.name}>
                        {p.displayName}
                      </option>
                    ))}
                  </select>
                  {isSwitching && <span className="text-xs text-muted-foreground">切换中...</span>}

                  {/* AI suggest button - disabled when globally locked */}
                  <button
                    onClick={(e) => { e.stopPropagation(); onSuggest?.(); }}
                    disabled={isSuggesting || isGlobalLocked}
                    className="text-xs px-2 py-1 rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
                  >
                    {isSuggesting ? "AI 分析中..." : "AI 建议"}
                  </button>

                  {/* Show suggestion */}
                  {suggestion && (
                    <div className="flex items-center gap-2 rounded bg-blue-500/10 border border-blue-500/30 px-2 py-1">
                      <span className="text-xs text-blue-400">
                        建议: {suggestion.recommended_display_name}
                      </span>
                      <span className="text-[10px] text-muted-foreground">
                        ({suggestion.market_state})
                      </span>
                      {suggestion.recommended_preset !== strategy?.preset_name && (
                        <button
                          onClick={(e) => { e.stopPropagation(); onSwitchStrategy?.(suggestion.recommended_preset); }}
                          disabled={isSwitching}
                          className="text-[11px] px-1.5 py-0.5 rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
                        >
                          采纳
                        </button>
                      )}
                      {suggestion.recommended_preset === strategy?.preset_name && (
                        <span className="text-[10px] text-green-400">已是当前策略</span>
                      )}
                    </div>
                  )}
                </div>
                {suggestion?.reason && (
                  <p className="text-[11px] text-muted-foreground mt-1">{suggestion.reason}</p>
                )}
              </div>
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
