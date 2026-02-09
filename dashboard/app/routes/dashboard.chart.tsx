import { useState } from "react";
import type { Route } from "./+types/dashboard.chart";
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card";
import {
  Tooltip as UiTooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "~/components/ui/tooltip";
import { cn } from "~/lib/utils";
import { HelpCircle } from "lucide-react";
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

// 指标元信息：中文名、说明、Wikipedia 链接
const INDICATOR_META: Record<
  string,
  { label: string; tip: string; url: string }
> = {
  price: {
    label: "价格",
    tip: "当前交易对的实时价格",
    url: "",
  },
  ma7: {
    label: "MA7",
    tip: "7 周期简单移动平均线，反映短期趋势",
    url: "https://zh.wikipedia.org/wiki/%E7%A7%BB%E5%8B%95%E5%B9%B3%E5%9D%87",
  },
  ma25: {
    label: "MA25",
    tip: "25 周期简单移动平均线，反映中期趋势",
    url: "https://zh.wikipedia.org/wiki/%E7%A7%BB%E5%8B%95%E5%B9%B3%E5%9D%87",
  },
  ma99: {
    label: "MA99",
    tip: "99 周期简单移动平均线，反映长期趋势",
    url: "https://zh.wikipedia.org/wiki/%E7%A7%BB%E5%8B%95%E5%B9%B3%E5%9D%87",
  },
  rsi: {
    label: "RSI",
    tip: "相对强弱指数 (0-100)：>70 超买，<30 超卖",
    url: "https://zh.wikipedia.org/wiki/%E7%9B%B8%E5%B0%8D%E5%BC%B7%E5%BC%B1%E6%8C%87%E6%95%B8",
  },
  macd: {
    label: "MACD",
    tip: "移动平均收敛散度，正值看多，负值看空",
    url: "https://zh.wikipedia.org/wiki/MACD",
  },
  macdSignal: {
    label: "Signal",
    tip: "MACD 信号线，MACD 上穿信号线为金叉(买入)，下穿为死叉(卖出)",
    url: "https://zh.wikipedia.org/wiki/MACD",
  },
};

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

/** 图例项：悬停显示说明，点击跳转 Wikipedia */
function IndicatorLegendItem({
  dataKey,
  color,
}: {
  dataKey: string;
  color: string;
}) {
  const meta = INDICATOR_META[dataKey];
  const label = meta?.label || dataKey;
  const tip = meta?.tip;
  const url = meta?.url;

  const inner = (
    <span
      className={cn(
        "inline-flex items-center gap-1 text-xs",
        url && "cursor-pointer hover:underline"
      )}
      style={{ color }}
      onClick={
        url
          ? (e) => {
              e.stopPropagation();
              window.open(url, "_blank", "noopener");
            }
          : undefined
      }
    >
      <span
        className="inline-block h-2.5 w-2.5 rounded-sm"
        style={{ backgroundColor: color }}
      />
      {label}
    </span>
  );

  if (!tip) return inner;

  return (
    <TooltipProvider delayDuration={150}>
      <UiTooltip>
        <TooltipTrigger asChild>{inner}</TooltipTrigger>
        <TooltipContent side="top">
          <p className="max-w-xs text-xs">
            {tip}
            {url && (
              <span className="ml-1 text-muted-foreground">（点击查看详情）</span>
            )}
          </p>
        </TooltipContent>
      </UiTooltip>
    </TooltipProvider>
  );
}

/** 自定义图例渲染器 */
function renderIndicatorLegend(props: any) {
  const { payload } = props;
  if (!payload) return null;
  return (
    <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1 pt-1">
      {payload.map((entry: any) => (
        <IndicatorLegendItem
          key={entry.dataKey}
          dataKey={entry.dataKey}
          color={entry.color}
        />
      ))}
    </div>
  );
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
              <CardTitle className="flex items-center gap-2 text-base">
                价格与均线
                <ChartTip tip="显示价格走势与 MA7/MA25/MA99 移动平均线，均线交叉可作为趋势判断信号" />
              </CardTitle>
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
                      const meta = INDICATOR_META[name];
                      return [v?.toFixed(2), meta?.label || name];
                    }}
                  />
                  <Legend content={renderIndicatorLegend} />
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
              <CardTitle className="flex items-center gap-2 text-base">
                RSI 指标
                <ChartTip tip="相对强弱指数 (0-100)：>70 超买区域可能回调，<30 超卖区域可能反弹，50 为多空分界" />
              </CardTitle>
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
                  <Legend content={renderIndicatorLegend} />
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
              <CardTitle className="flex items-center gap-2 text-base">
                MACD 指标
                <ChartTip tip="移动平均收敛散度：柱状图为 MACD 值，红线为信号线，金叉(MACD上穿信号线)买入，死叉卖出" />
              </CardTitle>
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
                      const meta = INDICATOR_META[name];
                      return [v?.toFixed(4), meta?.label || name];
                    }}
                  />
                  <Legend content={renderIndicatorLegend} />
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
              <CardTitle className="flex items-center gap-2 text-base">
                最新技术信号
                <ChartTip tip="最近几次 AI 分析的综合技术信号，包括趋势方向、信号强度和置信度" />
              </CardTitle>
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

function ChartTip({ tip }: { tip: string }) {
  return (
    <TooltipProvider delayDuration={200}>
      <UiTooltip>
        <TooltipTrigger asChild>
          <HelpCircle className="h-4 w-4 text-muted-foreground cursor-help" />
        </TooltipTrigger>
        <TooltipContent>
          <p className="max-w-xs">{tip}</p>
        </TooltipContent>
      </UiTooltip>
    </TooltipProvider>
  );
}
