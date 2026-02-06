import { useState } from "react";
import type { Route } from "./+types/dashboard.chart";
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card";
import { cn } from "~/lib/utils";
import { db } from "db";
import { decisions, technicalSnapshots } from "db/schema";
import { desc, eq } from "drizzle-orm";
import {
  LineChart,
  Line,
  ComposedChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";

export async function loader(_args: Route.LoaderArgs) {
  // 获取技术指标数据 (technicalSnapshots JOIN decisions)
  const technicalData = await db
    .select({
      id: technicalSnapshots.id,
      decisionId: technicalSnapshots.decisionId,
      createdAt: decisions.createdAt,
      symbol: decisions.symbol,
      trend: technicalSnapshots.trend,
      trendConfidence: technicalSnapshots.trendConfidence,
      signalStrength: technicalSnapshots.signalStrength,
      price: technicalSnapshots.price,
      rsi: technicalSnapshots.rsi,
      macd: technicalSnapshots.macd,
      macdSignal: technicalSnapshots.macdSignal,
      ma7: technicalSnapshots.ma7,
      ma25: technicalSnapshots.ma25,
      ma99: technicalSnapshots.ma99,
    })
    .from(technicalSnapshots)
    .innerJoin(decisions, eq(technicalSnapshots.decisionId, decisions.id))
    .orderBy(desc(decisions.createdAt))
    .limit(100);

  // 获取可用的交易对列表
  const symbolsResult = await db
    .selectDistinct({ symbol: decisions.symbol })
    .from(decisions)
    .orderBy(decisions.symbol);

  return {
    technicalData: technicalData.map((d) => ({
      id: d.id,
      decisionId: d.decisionId,
      createdAt: d.createdAt.toISOString(),
      symbol: d.symbol,
      trend: d.trend,
      trendConfidence: d.trendConfidence,
      signalStrength: d.signalStrength,
      price: d.price ? Number(d.price) : null,
      rsi: d.rsi ? Number(d.rsi) : null,
      macd: d.macd ? Number(d.macd) : null,
      macdSignal: d.macdSignal ? Number(d.macdSignal) : null,
      ma7: d.ma7 ? Number(d.ma7) : null,
      ma25: d.ma25 ? Number(d.ma25) : null,
      ma99: d.ma99 ? Number(d.ma99) : null,
    })),
    symbols: symbolsResult.map((s) => s.symbol),
  };
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
    <span
      className={cn(
        "rounded px-2 py-0.5 text-xs font-medium",
        colors[trend || "neutral"]
      )}
    >
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
    <span
      className={cn(
        "rounded px-2 py-0.5 text-xs font-medium",
        colors[signal || "neutral"]
      )}
    >
      {labels[signal || "neutral"] || signal}
    </span>
  );
}

function formatTime(dateStr: string) {
  const d = new Date(dateStr);
  return `${(d.getMonth() + 1).toString().padStart(2, "0")}/${d.getDate().toString().padStart(2, "0")} ${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}`;
}

export default function ChartPage({ loaderData }: Route.ComponentProps) {
  const { technicalData, symbols } = loaderData;
  const [selectedSymbol, setSelectedSymbol] = useState<string>(
    symbols[0] || ""
  );

  const filteredData = technicalData
    .filter((d) => d.symbol === selectedSymbol)
    .reverse(); // 按时间正序显示

  const hasData = filteredData.length > 0;

  return (
    <div className="space-y-6">
      {/* 交易对选择器 */}
      <div className="flex flex-wrap gap-2">
        {symbols.map((symbol) => (
          <button
            key={symbol}
            onClick={() => setSelectedSymbol(symbol)}
            className={cn(
              "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
              selectedSymbol === symbol
                ? "bg-primary text-primary-foreground"
                : "bg-muted text-muted-foreground hover:bg-muted/80"
            )}
          >
            {symbol}
          </button>
        ))}
      </div>

      {!hasData ? (
        <div className="flex h-64 items-center justify-center text-muted-foreground">
          暂无数据，请先运行交易程序生成决策
        </div>
      ) : (
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
                    dataKey="createdAt"
                    tickFormatter={formatTime}
                    fontSize={12}
                  />
                  <YAxis
                    fontSize={12}
                    domain={["auto", "auto"]}
                    tickFormatter={(v) => v.toFixed(0)}
                  />
                  <Tooltip
                    labelFormatter={(v) => formatTime(v as string)}
                    formatter={(v: number, name: string) => {
                      const labels: Record<string, string> = {
                        price: "价格",
                        ma7: "MA7",
                        ma25: "MA25",
                        ma99: "MA99",
                      };
                      return [v?.toFixed(2), labels[name] || name];
                    }}
                  />
                  <Legend
                    formatter={(value) => {
                      const labels: Record<string, string> = {
                        price: "价格",
                        ma7: "MA7",
                        ma25: "MA25",
                        ma99: "MA99",
                      };
                      return labels[value] || value;
                    }}
                  />
                  <Line
                    type="monotone"
                    dataKey="price"
                    stroke="#3b82f6"
                    strokeWidth={2}
                    dot={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="ma7"
                    stroke="#22c55e"
                    strokeWidth={1}
                    dot={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="ma25"
                    stroke="#f59e0b"
                    strokeWidth={1}
                    dot={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="ma99"
                    stroke="#ef4444"
                    strokeWidth={1}
                    dot={false}
                  />
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
                    dataKey="createdAt"
                    tickFormatter={formatTime}
                    fontSize={12}
                  />
                  <YAxis fontSize={12} domain={[0, 100]} />
                  <Tooltip
                    labelFormatter={(v) => formatTime(v as string)}
                    formatter={(v: number) => [v?.toFixed(2), "RSI"]}
                  />
                  <Legend formatter={() => "RSI"} />
                  <Line
                    type="monotone"
                    dataKey="rsi"
                    stroke="#8b5cf6"
                    strokeWidth={2}
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
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
                    dataKey="createdAt"
                    tickFormatter={formatTime}
                    fontSize={12}
                  />
                  <YAxis fontSize={12} />
                  <Tooltip
                    labelFormatter={(v) => formatTime(v as string)}
                    formatter={(v: number, name: string) => {
                      const labels: Record<string, string> = {
                        macd: "MACD",
                        macdSignal: "Signal",
                      };
                      return [v?.toFixed(4), labels[name] || name];
                    }}
                  />
                  <Legend
                    formatter={(value) => {
                      const labels: Record<string, string> = {
                        macd: "MACD",
                        macdSignal: "Signal",
                      };
                      return labels[value] || value;
                    }}
                  />
                  <Bar dataKey="macd" fill="#3b82f6" />
                  <Line
                    type="monotone"
                    dataKey="macdSignal"
                    stroke="#ef4444"
                    strokeWidth={1}
                    dot={false}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* 最新技术信号 */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">最新技术信号</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {filteredData.slice(-4).reverse().map((item) => (
                  <div
                    key={item.id}
                    className="flex items-center justify-between rounded-md border p-3"
                  >
                    <div className="flex items-center gap-3">
                      <span className="text-sm text-muted-foreground">
                        {formatTime(item.createdAt)}
                      </span>
                      <TrendBadge trend={item.trend} />
                      <SignalBadge signal={item.signalStrength} />
                    </div>
                    <div className="text-right text-sm">
                      <span className="font-medium">
                        {item.price?.toFixed(2)}
                      </span>
                      {item.trendConfidence && (
                        <span className="ml-2 text-muted-foreground">
                          置信度: {item.trendConfidence}%
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
