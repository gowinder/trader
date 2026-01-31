import { Link } from "react-router";
import type { Route } from "./+types/dashboard.decisions.$id";
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card";
import { Button } from "~/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "~/components/ui/tabs";
import { cn, formatDateTime, formatUSD, getPnlColorClass } from "~/lib/utils";
import { ArrowLeft, ChevronDown, ChevronUp } from "lucide-react";
import { useState } from "react";
import { db } from "db";
import {
  decisions as decisionsTable,
  technicalSnapshots,
  riskSnapshots,
  sentimentSnapshots,
} from "db/schema";
import { eq } from "drizzle-orm";

export async function loader({ params }: Route.LoaderArgs) {
  const { id } = params;

  // 从数据库获取决策数据
  const [decisionRow] = await db
    .select()
    .from(decisionsTable)
    .where(eq(decisionsTable.id, id))
    .limit(1);

  if (!decisionRow) {
    throw new Response("Decision not found", { status: 404 });
  }

  // 获取技术分析、风险评估、情绪分析
  const [techRow] = await db
    .select()
    .from(technicalSnapshots)
    .where(eq(technicalSnapshots.decisionId, id))
    .limit(1);

  const [riskRow] = await db
    .select()
    .from(riskSnapshots)
    .where(eq(riskSnapshots.decisionId, id))
    .limit(1);

  const [sentimentRow] = await db
    .select()
    .from(sentimentSnapshots)
    .where(eq(sentimentSnapshots.decisionId, id))
    .limit(1);

  return {
    decision: {
      id: decisionRow.id,
      createdAt: decisionRow.createdAt.toISOString(),
      symbol: decisionRow.symbol,
      timeframe: decisionRow.timeframe,
      action: decisionRow.action,
      confidence: decisionRow.confidence,
      leverage: decisionRow.leverage ? parseFloat(decisionRow.leverage) : null,
      positionSizePct: decisionRow.positionSizePct
        ? parseFloat(decisionRow.positionSizePct)
        : null,
      entryPrice: decisionRow.entryPrice
        ? parseFloat(decisionRow.entryPrice)
        : null,
      stopLoss: decisionRow.stopLoss ? parseFloat(decisionRow.stopLoss) : null,
      takeProfit: decisionRow.takeProfit
        ? parseFloat(decisionRow.takeProfit)
        : null,
      reasoning: decisionRow.reasoning,
      llmProvider: decisionRow.llmProvider,
      llmModel: decisionRow.llmModel,
      llmRawOutput: decisionRow.llmRawOutput,
      llmTokensUsed: decisionRow.llmTokensUsed,
    },
    technical: techRow
      ? {
          trend: techRow.trend,
          trendConfidence: techRow.trendConfidence,
          signalStrength: techRow.signalStrength,
          price: techRow.price ? parseFloat(techRow.price) : null,
          rsi: techRow.rsi ? parseFloat(techRow.rsi) : null,
          macd: techRow.macd ? parseFloat(techRow.macd) : null,
          macdSignal: techRow.macdSignal
            ? parseFloat(techRow.macdSignal)
            : null,
          ma7: techRow.ma7 ? parseFloat(techRow.ma7) : null,
          ma25: techRow.ma25 ? parseFloat(techRow.ma25) : null,
          ma99: techRow.ma99 ? parseFloat(techRow.ma99) : null,
          atr: techRow.atr ? parseFloat(techRow.atr) : null,
          bollUpper: techRow.bollUpper ? parseFloat(techRow.bollUpper) : null,
          bollLower: techRow.bollLower ? parseFloat(techRow.bollLower) : null,
          supportLevels: (techRow.supportLevels as number[]) || [],
          resistanceLevels: (techRow.resistanceLevels as number[]) || [],
          volumeTrend: techRow.volumeTrend,
          pattern: techRow.pattern,
          keyObservations: (techRow.keyObservations as string[]) || [],
        }
      : null,
    risk: riskRow
      ? {
          riskLevel: riskRow.riskLevel,
          riskScore: riskRow.riskScore,
          recommendedLeverage: riskRow.recommendedLeverage
            ? parseFloat(riskRow.recommendedLeverage)
            : null,
          recommendedPositionPct: riskRow.recommendedPositionPct
            ? parseFloat(riskRow.recommendedPositionPct)
            : null,
          shouldTrade: riskRow.shouldTrade,
          riskFactors: (riskRow.riskFactors as string[]) || [],
          mitigationSuggestions:
            (riskRow.mitigationSuggestions as string[]) || [],
        }
      : null,
    sentiment: sentimentRow
      ? {
          overallScore: sentimentRow.overallScore
            ? parseFloat(sentimentRow.overallScore)
            : 0,
          newsCount: sentimentRow.newsCount || 0,
          bullishCount: sentimentRow.bullishCount || 0,
          bearishCount: sentimentRow.bearishCount || 0,
          topNews: sentimentRow.topNews || null,
          dataSource: sentimentRow.dataSource,
        }
      : null,
    result: null as {
      status: string;
      realizedPnl: number;
      pnlPercent: number;
      exitPrice: number;
      holdingDuration: string;
    } | null, // TODO: 从 position_history 获取
  };
}

export default function DecisionDetailPage({ loaderData }: Route.ComponentProps) {
  const { decision, technical, risk, sentiment, result } = loaderData;
  const [llmExpanded, setLlmExpanded] = useState(false);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Link to="/dashboard/decisions">
          <Button variant="ghost" size="sm">
            <ArrowLeft className="mr-2 h-4 w-4" />
            返回
          </Button>
        </Link>
        <div>
          <h1 className="text-2xl font-bold">决策详情</h1>
          <p className="text-sm text-muted-foreground">
            {formatDateTime(decision.createdAt)}
          </p>
        </div>
      </div>

      {/* Basic Info */}
      <Card>
        <CardHeader>
          <CardTitle>基本信息</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-6 md:grid-cols-2">
            <div className="space-y-4">
              <div className="flex justify-between">
                <span className="text-muted-foreground">交易对</span>
                <span className="font-medium">{decision.symbol}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">时间周期</span>
                <span className="font-medium">{decision.timeframe}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">动作</span>
                <span
                  className={cn(
                    "rounded px-2 py-1 text-sm font-medium",
                    decision.action.includes("long")
                      ? "bg-profit/20 text-profit"
                      : decision.action.includes("short")
                      ? "bg-loss/20 text-loss"
                      : "bg-muted"
                  )}
                >
                  {formatAction(decision.action)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">置信度</span>
                <span className="font-medium">{decision.confidence}%</span>
              </div>
            </div>
            <div className="space-y-4">
              <div className="flex justify-between">
                <span className="text-muted-foreground">入场价格</span>
                <span className="font-medium tabular-nums">
                  {decision.entryPrice ? formatUSD(decision.entryPrice) : "-"}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">止损</span>
                <span className="font-medium tabular-nums text-destructive">
                  {decision.stopLoss ? formatUSD(decision.stopLoss) : "-"}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">止盈</span>
                <span className="font-medium tabular-nums text-profit">
                  {decision.takeProfit ? formatUSD(decision.takeProfit) : "-"}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">杠杆 / 仓位</span>
                <span className="font-medium">
                  {decision.leverage ?? "-"}x / {decision.positionSizePct ?? "-"}%
                </span>
              </div>
            </div>
          </div>

          <div className="mt-6">
            <p className="text-sm text-muted-foreground">决策理由</p>
            <p className="mt-1">{decision.reasoning}</p>
          </div>
        </CardContent>
      </Card>

      {/* LLM Output */}
      <Card>
        <CardHeader
          className="cursor-pointer"
          onClick={() => setLlmExpanded(!llmExpanded)}
        >
          <div className="flex items-center justify-between">
            <CardTitle>LLM 原始输出</CardTitle>
            <div className="flex items-center gap-4">
              <span className="text-sm text-muted-foreground">
                {decision.llmProvider} / {decision.llmModel} ({decision.llmTokensUsed} tokens)
              </span>
              {llmExpanded ? (
                <ChevronUp className="h-4 w-4" />
              ) : (
                <ChevronDown className="h-4 w-4" />
              )}
            </div>
          </div>
        </CardHeader>
        {llmExpanded && (
          <CardContent>
            <pre className="whitespace-pre-wrap rounded-lg bg-muted p-4 text-sm">
              {decision.llmRawOutput}
            </pre>
          </CardContent>
        )}
      </Card>

      {/* Analysis Tabs */}
      <Tabs defaultValue="technical">
        <TabsList>
          <TabsTrigger value="technical">技术分析</TabsTrigger>
          <TabsTrigger value="risk">风险评估</TabsTrigger>
          <TabsTrigger value="sentiment">情感分析</TabsTrigger>
        </TabsList>

        <TabsContent value="technical" className="mt-4">
          <Card>
            <CardContent className="pt-6">
              {technical ? (
                <>
                  <div className="grid gap-6 md:grid-cols-3">
                    <div className="space-y-4">
                      <h4 className="font-medium">趋势</h4>
                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">趋势方向</span>
                          <span className="text-profit">{technical.trend}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">趋势信心</span>
                          <span>{technical.trendConfidence}%</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">信号强度</span>
                          <span>{technical.signalStrength}</span>
                        </div>
                      </div>
                    </div>

                    <div className="space-y-4">
                      <h4 className="font-medium">指标</h4>
                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">RSI</span>
                          <span className="tabular-nums">{technical.rsi ?? "-"}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">MACD</span>
                          <span className="tabular-nums">{technical.macd ?? "-"}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">ATR</span>
                          <span className="tabular-nums">{technical.atr ?? "-"}</span>
                        </div>
                      </div>
                    </div>

                    <div className="space-y-4">
                      <h4 className="font-medium">支撑阻力</h4>
                      <div className="space-y-2 text-sm">
                        <div>
                          <span className="text-muted-foreground">支撑位: </span>
                          <span className="tabular-nums">
                            {technical.supportLevels.length > 0
                              ? technical.supportLevels.map((l) => formatUSD(l)).join(", ")
                              : "-"}
                          </span>
                        </div>
                        <div>
                          <span className="text-muted-foreground">阻力位: </span>
                          <span className="tabular-nums">
                            {technical.resistanceLevels.length > 0
                              ? technical.resistanceLevels.map((l) => formatUSD(l)).join(", ")
                              : "-"}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="mt-6">
                    <h4 className="font-medium">关键观察</h4>
                    <ul className="mt-2 list-inside list-disc space-y-1 text-sm text-muted-foreground">
                      {technical.keyObservations.map((obs, i) => (
                        <li key={i}>{obs}</li>
                      ))}
                    </ul>
                  </div>
                </>
              ) : (
                <p className="text-muted-foreground">暂无技术分析数据</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="risk" className="mt-4">
          <Card>
            <CardContent className="pt-6">
              {risk ? (
                <div className="grid gap-6 md:grid-cols-2">
                  <div className="space-y-4">
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">风险等级</span>
                      <span
                        className={cn(
                          "rounded px-2 py-1 text-sm font-medium",
                          risk.riskLevel === "low" && "bg-green-500/20 text-green-500",
                          risk.riskLevel === "medium" && "bg-yellow-500/20 text-yellow-500",
                          risk.riskLevel === "high" && "bg-red-500/20 text-red-500"
                        )}
                      >
                        {risk.riskLevel}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">风险评分</span>
                      <span>{risk.riskScore}/100</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">推荐杠杆</span>
                      <span>{risk.recommendedLeverage}x</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">推荐仓位</span>
                      <span>{risk.recommendedPositionPct}%</span>
                    </div>
                  </div>

                  <div className="space-y-4">
                    <div>
                      <h4 className="font-medium">风险因素</h4>
                      <ul className="mt-2 list-inside list-disc space-y-1 text-sm text-muted-foreground">
                        {risk.riskFactors.map((factor, i) => (
                          <li key={i}>{factor}</li>
                        ))}
                      </ul>
                    </div>
                    <div>
                      <h4 className="font-medium">缓解建议</h4>
                      <ul className="mt-2 list-inside list-disc space-y-1 text-sm text-muted-foreground">
                        {risk.mitigationSuggestions.map((sug, i) => (
                          <li key={i}>{sug}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </div>
              ) : (
                <p className="text-muted-foreground">暂无风险评估数据</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="sentiment" className="mt-4">
          <Card>
            <CardContent className="pt-6">
              {sentiment ? (
                <div className="grid gap-6 md:grid-cols-2">
                  <div className="space-y-4">
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">综合评分</span>
                      <span
                        className={cn(
                          "font-medium",
                          sentiment.overallScore > 0 ? "text-profit" : "text-loss"
                        )}
                      >
                        {sentiment.overallScore > 0 ? "+" : ""}
                        {(sentiment.overallScore * 100).toFixed(0)}%
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">新闻数量</span>
                      <span>{sentiment.newsCount}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">看多 / 看空</span>
                      <span>
                        <span className="text-profit">{sentiment.bullishCount}</span>
                        {" / "}
                        <span className="text-loss">{sentiment.bearishCount}</span>
                      </span>
                    </div>
                  </div>

                  <div>
                    <h4 className="font-medium">详情</h4>
                    {sentiment.topNews ? (
                      <pre className="mt-2 text-sm text-muted-foreground whitespace-pre-wrap">
                        {JSON.stringify(sentiment.topNews, null, 2)}
                      </pre>
                    ) : (
                      <p className="mt-2 text-sm text-muted-foreground">暂无详细信息</p>
                    )}
                  </div>
                </div>
              ) : (
                <p className="text-muted-foreground">暂无情绪分析数据</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Result */}
      {result && (
        <Card>
          <CardHeader>
            <CardTitle>执行结果</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid gap-4 md:grid-cols-4">
              <div>
                <p className="text-sm text-muted-foreground">状态</p>
                <p className="font-medium">{result.status === "closed" ? "已平仓" : "持仓中"}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">盈亏</p>
                <p className={cn("text-lg font-bold tabular-nums", getPnlColorClass(result.realizedPnl))}>
                  {formatUSD(result.realizedPnl)} ({result.pnlPercent > 0 ? "+" : ""}{result.pnlPercent}%)
                </p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">出场价格</p>
                <p className="font-medium tabular-nums">{formatUSD(result.exitPrice)}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">持仓时长</p>
                <p className="font-medium">{result.holdingDuration}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function formatAction(action: string): string {
  const map: Record<string, string> = {
    open_long: "开多",
    open_short: "开空",
    close_long: "平多",
    close_short: "平空",
    hold: "持有",
  };
  return map[action] || action;
}
