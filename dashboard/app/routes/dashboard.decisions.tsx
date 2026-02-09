import { Link, useSearchParams } from "react-router";
import type { Route } from "./+types/dashboard.decisions";
import { Card, CardContent } from "~/components/ui/card";
import { Button } from "~/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select";
import { cn, formatDateTime, formatUSD, getPnlColorClass } from "~/lib/utils";
import { ChevronLeft, ChevronRight, ExternalLink, X } from "lucide-react";
import { db } from "db";
import { decisions as decisionsTable } from "db/schema";
import { desc, count, eq, and, gte, ne } from "drizzle-orm";

export async function loader({ request }: Route.LoaderArgs) {
  const url = new URL(request.url);
  const page = parseInt(url.searchParams.get("page") || "1");
  const symbol = url.searchParams.get("symbol") || "";
  const action = url.searchParams.get("action") || "";
  const days = parseInt(url.searchParams.get("days") || "0");
  const limit = 20;
  const offset = (page - 1) * limit;

  // 构建筛选条件
  const conditions = [];
  if (symbol) {
    conditions.push(eq(decisionsTable.symbol, symbol));
  }
  if (action) {
    if (action === "not_hold") {
      conditions.push(ne(decisionsTable.action, "hold"));
    } else {
      conditions.push(eq(decisionsTable.action, action));
    }
  }
  if (days > 0) {
    const startDate = new Date();
    startDate.setDate(startDate.getDate() - days);
    conditions.push(gte(decisionsTable.createdAt, startDate));
  }

  const whereClause = conditions.length > 0 ? and(...conditions) : undefined;

  // 获取所有可用的交易对（用于筛选器）
  const symbolsResult = await db
    .selectDistinct({ symbol: decisionsTable.symbol })
    .from(decisionsTable)
    .orderBy(decisionsTable.symbol);

  // 从数据库获取决策数据
  const [decisions, totalResult] = await Promise.all([
    db
      .select({
        id: decisionsTable.id,
        createdAt: decisionsTable.createdAt,
        symbol: decisionsTable.symbol,
        action: decisionsTable.action,
        confidence: decisionsTable.confidence,
        leverage: decisionsTable.leverage,
        entryPrice: decisionsTable.entryPrice,
        stopLoss: decisionsTable.stopLoss,
        takeProfit: decisionsTable.takeProfit,
        reasoning: decisionsTable.reasoning,
        reasoningZh: decisionsTable.reasoningZh,
        llmProvider: decisionsTable.llmProvider,
        strategyPreset: decisionsTable.strategyPreset,
      })
      .from(decisionsTable)
      .where(whereClause)
      .orderBy(desc(decisionsTable.createdAt))
      .limit(limit)
      .offset(offset),
    db.select({ count: count() }).from(decisionsTable).where(whereClause),
  ]);

  const total = totalResult[0]?.count || 0;

  return {
    decisions: decisions.map((d) => ({
      id: d.id,
      createdAt: d.createdAt.toISOString(),
      symbol: d.symbol,
      action: d.action,
      confidence: d.confidence,
      leverage: d.leverage ? parseFloat(d.leverage) : null,
      entryPrice: d.entryPrice ? parseFloat(d.entryPrice) : null,
      stopLoss: d.stopLoss ? parseFloat(d.stopLoss) : null,
      takeProfit: d.takeProfit ? parseFloat(d.takeProfit) : null,
      reasoning: d.reasoning,
      reasoningZh: d.reasoningZh,
      llmProvider: d.llmProvider,
      strategyPreset: d.strategyPreset,
      resultPnl: null, // TODO: 从 position_history 计算
    })),
    pagination: {
      page,
      limit,
      total,
      totalPages: Math.ceil(total / limit),
    },
    filters: {
      symbol,
      action,
      days,
      availableSymbols: symbolsResult.map((s) => s.symbol),
    },
  };
}

export default function DecisionsPage({ loaderData }: Route.ComponentProps) {
  const { decisions, pagination, filters } = loaderData;
  const [searchParams, setSearchParams] = useSearchParams();

  const updateFilter = (key: string, value: string) => {
    const params = new URLSearchParams(searchParams);
    if (value) {
      params.set(key, value);
    } else {
      params.delete(key);
    }
    params.set("page", "1"); // 重置到第一页
    setSearchParams(params);
  };

  const clearFilters = () => {
    setSearchParams({});
  };

  const hasFilters = filters.symbol || filters.action || filters.days > 0;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">决策记录</h1>
        <div className="text-sm text-muted-foreground">
          共 {pagination.total} 条记录
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <Select
          value={filters.symbol}
          onValueChange={(v) => updateFilter("symbol", v)}
        >
          <SelectTrigger className="w-[140px]">
            <SelectValue placeholder="交易对" />
          </SelectTrigger>
          <SelectContent>
            {filters.availableSymbols.map((s) => (
              <SelectItem key={s} value={s}>
                {s}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={filters.action}
          onValueChange={(v) => updateFilter("action", v)}
        >
          <SelectTrigger className="w-[120px]">
            <SelectValue placeholder="动作" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="not_hold">非持有</SelectItem>
            <SelectItem value="open_long">开多</SelectItem>
            <SelectItem value="open_short">开空</SelectItem>
            <SelectItem value="close_long">平多</SelectItem>
            <SelectItem value="close_short">平空</SelectItem>
            <SelectItem value="hold">持有</SelectItem>
          </SelectContent>
        </Select>

        <Select
          value={filters.days > 0 ? String(filters.days) : ""}
          onValueChange={(v) => updateFilter("days", v)}
        >
          <SelectTrigger className="w-[120px]">
            <SelectValue placeholder="时间范围" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="1">最近 1 天</SelectItem>
            <SelectItem value="7">最近 7 天</SelectItem>
            <SelectItem value="30">最近 30 天</SelectItem>
            <SelectItem value="90">最近 90 天</SelectItem>
          </SelectContent>
        </Select>

        {hasFilters && (
          <Button variant="ghost" size="sm" onClick={clearFilters}>
            <X className="mr-1 h-4 w-4" />
            清除筛选
          </Button>
        )}
      </div>

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="px-4 py-3 text-left text-sm font-medium">
                    时间
                  </th>
                  <th className="px-4 py-3 text-left text-sm font-medium">
                    交易对
                  </th>
                  <th className="px-4 py-3 text-left text-sm font-medium">
                    动作
                  </th>
                  <th className="px-4 py-3 text-left text-sm font-medium">
                    置信度
                  </th>
                  <th className="px-4 py-3 text-left text-sm font-medium">
                    入场价
                  </th>
                  <th className="px-4 py-3 text-left text-sm font-medium">
                    策略
                  </th>
                  <th className="px-4 py-3 text-left text-sm font-medium">
                    盈亏
                  </th>
                  <th className="px-4 py-3 text-left text-sm font-medium">
                    理由
                  </th>
                  <th className="px-4 py-3 text-center text-sm font-medium">
                    详情
                  </th>
                </tr>
              </thead>
              <tbody>
                {decisions.length === 0 ? (
                  <tr>
                    <td
                      colSpan={9}
                      className="px-4 py-8 text-center text-muted-foreground"
                    >
                      暂无数据
                    </td>
                  </tr>
                ) : (
                  decisions.map((decision) => (
                    <tr
                      key={decision.id}
                      className="border-b transition-colors hover:bg-muted/50"
                    >
                      <td className="px-4 py-3 text-sm tabular-nums">
                        {formatDateTime(decision.createdAt)}
                      </td>
                      <td className="px-4 py-3 text-sm font-medium">
                        {decision.symbol}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={cn(
                            "rounded px-2 py-1 text-xs font-medium",
                            decision.action.includes("long")
                              ? "bg-profit/20 text-profit"
                              : decision.action.includes("short")
                                ? "bg-loss/20 text-loss"
                                : "bg-muted text-muted-foreground"
                          )}
                        >
                          {formatAction(decision.action)}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm">
                        <div className="flex items-center gap-2">
                          <div className="h-2 w-16 overflow-hidden rounded-full bg-muted">
                            <div
                              className={cn(
                                "h-full",
                                decision.confidence >= 80
                                  ? "bg-green-500"
                                  : decision.confidence >= 60
                                    ? "bg-yellow-500"
                                    : "bg-red-500"
                              )}
                              style={{ width: `${decision.confidence}%` }}
                            />
                          </div>
                          <span className="tabular-nums">
                            {decision.confidence}%
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-sm tabular-nums">
                        {decision.entryPrice
                          ? formatUSD(decision.entryPrice)
                          : "-"}
                      </td>
                      <td className="px-4 py-3 text-sm">
                        {decision.strategyPreset ? (
                          <span className="rounded bg-muted px-2 py-0.5 text-xs">
                            {formatPresetName(decision.strategyPreset)}
                          </span>
                        ) : (
                          <span className="text-muted-foreground">-</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-sm tabular-nums">
                        {decision.resultPnl !== null ? (
                          <span className={getPnlColorClass(decision.resultPnl)}>
                            {formatUSD(decision.resultPnl)}
                          </span>
                        ) : (
                          <span className="text-muted-foreground">-</span>
                        )}
                      </td>
                      <td className="max-w-xs px-4 py-3 text-sm text-muted-foreground">
                        <p
                          className="truncate"
                          title={(decision.reasoningZh || decision.reasoning) ?? undefined}
                        >
                          {decision.reasoningZh || decision.reasoning || "-"}
                        </p>
                      </td>
                      <td className="px-4 py-3 text-center">
                        <Link to={`/dashboard/decisions/${decision.id}`}>
                          <Button variant="ghost" size="sm">
                            <ExternalLink className="h-4 w-4" />
                          </Button>
                        </Link>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Pagination */}
      <div className="flex items-center justify-between">
        <div className="text-sm text-muted-foreground">
          第 {pagination.page} 页，共 {pagination.totalPages} 页
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={pagination.page <= 1}
            onClick={() => {
              const params = new URLSearchParams(searchParams);
              params.set("page", String(pagination.page - 1));
              setSearchParams(params);
            }}
          >
            <ChevronLeft className="h-4 w-4" />
            上一页
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={pagination.page >= pagination.totalPages}
            onClick={() => {
              const params = new URLSearchParams(searchParams);
              params.set("page", String(pagination.page + 1));
              setSearchParams(params);
            }}
          >
            下一页
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
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
