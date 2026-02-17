import { useState, useCallback, useEffect } from "react";
import type { LoaderFunctionArgs } from "react-router";
import { useLoaderData } from "react-router";
import { StatCard } from "~/components/common/StatCard";
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card";
import { Button } from "~/components/ui/button";
import { cn } from "~/lib/utils";
import { Cpu, Coins, Clock, CheckCircle, X, ChevronUp, ChevronDown, Save, Plus, Trash2 } from "lucide-react";
import {
  AreaChart,
  Area,
  LineChart,
  Line,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

interface UsageStats {
  total_calls: number;
  total_tokens: number;
  total_cost_usd: number;
  today_cost_usd: number;
  success_rate: number;
  avg_latency_ms: number;
  by_provider: Record<string, { calls: number; tokens: number; cost_usd: number }>;
}

interface DailyStats {
  date: string;
  provider: string;
  calls: number;
  tokens: number;
  cost_usd: number;
}

interface UsageRecord {
  id: string;
  timestamp: string;
  provider: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_usd: number;
  latency_ms: number;
  success: boolean;
  error_message: string | null;
  usage_type: string;
}

interface ProviderItem {
  providerId: number;
  model: string;
}

interface ProviderPoolItem {
  id: number;
  name: string;
  displayName: string;
  models: string[];
  isEnabled: boolean;
}

interface TimeSeriesPoint {
  time: string;
  calls: number;
  tokens: number;
  cost_usd: number;
}

interface UsageTypeData {
  usage_type: string;
  calls: number;
  tokens: number;
  cost_usd: number;
}

const PROVIDER_COLORS: Record<string, string> = {
  qwen: "#6366f1",
  gemini: "#22c55e",
  codex: "#f59e0b",
  openrouter: "#ef4444",
  opencode: "#8b5cf6",
  deepseek: "#06b6d4",
  glm: "#f97316",
};

const USAGE_TYPE_COLORS: Record<string, string> = {
  decision: "#ef4444",
  advisory: "#8b5cf6",
  analysis: "#3b82f6",
  optimization: "#22c55e",
  legacy: "#6b7280",
  unknown: "#9ca3af",
  other: "#f59e0b",
};

const USAGE_TYPE_LABELS: Record<string, string> = {
  decision: "交易决策",
  advisory: "顾问建议",
  analysis: "市场分析",
  optimization: "风险优化",
  legacy: "历史数据",
  unknown: "未分类",
  other: "其他",
};

const TIME_RANGES = [
  { label: "1h", hours: 1 },
  { label: "6h", hours: 6 },
  { label: "12h", hours: 12 },
  { label: "24h", hours: 24 },
  { label: "3d", hours: 72 },
  { label: "7d", hours: 168 },
  { label: "15d", hours: 360 },
  { label: "1m", hours: 720 },
  { label: "3m", hours: 2160 },
  { label: "6m", hours: 4320 },
  { label: "1y", hours: 8760 },
] as const;

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toString();
}

function formatUSD(n: number): string {
  return `$${n.toFixed(4)}`;
}

export async function loader({ request }: LoaderFunctionArgs) {
  const baseUrl = new URL(request.url).origin;
  const { loader: llmUsageLoader } = await import("./api.llm-usage");
  const { loader: providersLoader } = await import("./api.llm-config.providers");
  const { loader: routingLoader } = await import("./api.llm-config.routing");

  let stats: UsageStats = {
    total_calls: 0, total_tokens: 0, total_cost_usd: 0, today_cost_usd: 0,
    success_rate: 0, avg_latency_ms: 0, by_provider: {},
  };
  let dailyStats: DailyStats[] = [];
  let records: UsageRecord[] = [];

  try {
    const statsResp = await llmUsageLoader({ request: new Request(`${baseUrl}/api/llm-usage?action=stats`) } as any);
    if (statsResp instanceof Response && statsResp.ok) stats = await statsResp.json();
  } catch (e) { console.error("Failed to fetch stats:", e); }

  try {
    const dailyResp = await llmUsageLoader({ request: new Request(`${baseUrl}/api/llm-usage?action=daily&days=30`) } as any);
    if (dailyResp instanceof Response && dailyResp.ok) dailyStats = await dailyResp.json();
  } catch (e) { console.error("Failed to fetch daily stats:", e); }

  try {
    const recordsResp = await llmUsageLoader({ request: new Request(`${baseUrl}/api/llm-usage?action=records&limit=50`) } as any);
    if (recordsResp instanceof Response && recordsResp.ok) {
      const data = await recordsResp.json();
      records = data.records || [];
    }
  } catch (e) { console.error("Failed to fetch records:", e); }

  // 处理每日数据用于图表
  const dailyTokensMap = new Map<string, number>();
  const dailyCostMap = new Map<string, Record<string, number>>();

  for (const d of dailyStats) {
    dailyTokensMap.set(d.date, (dailyTokensMap.get(d.date) || 0) + d.tokens);
    if (!dailyCostMap.has(d.date)) dailyCostMap.set(d.date, {});
    const costByProvider = dailyCostMap.get(d.date)!;
    costByProvider[d.provider] = (costByProvider[d.provider] || 0) + d.cost_usd;
  }

  const dailyTokensData = Array.from(dailyTokensMap.entries())
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([date, tokens]) => ({ date, tokens }));

  const providers = Object.keys(stats.by_provider);
  const dailyCostData = Array.from(dailyCostMap.entries())
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([date, costs]) => ({ date, ...costs }));

  const providerPieData = Object.entries(stats.by_provider).map(([name, data]) => ({
    name, value: data.calls, tokens: data.tokens, cost: data.cost_usd,
  }));

  const providerCostData = Object.entries(stats.by_provider).map(([name, data]) => ({
    name, cost: data.cost_usd,
  }));

  // 获取 provider pool 和 main routing 配置
  let providerPool: ProviderPoolItem[] = [];
  let providerConfig: ProviderItem[] = [];
  let mainStrategy = "priority";

  try {
    const poolResp = await providersLoader({ request: new Request(`${baseUrl}/api/llm-config/providers`) } as any);
    if (poolResp instanceof Response && poolResp.ok) {
      const poolData = await poolResp.json();
      if (poolData.providers) {
        providerPool = poolData.providers.map((p: ProviderPoolItem) => ({
          id: p.id, name: p.name, displayName: p.displayName, models: p.models, isEnabled: p.isEnabled,
        }));
      }
    }
  } catch (e) { console.error("Failed to fetch provider pool:", e); }

  try {
    const routingResp = await routingLoader({ request: new Request(`${baseUrl}/api/llm-config/routing?scope=main`) } as any);
    if (routingResp instanceof Response && routingResp.ok) {
      const routingData = await routingResp.json();
      if (routingData.routing?.length > 0) {
        providerConfig = routingData.routing.map((r: { providerId: number; model: string }) => ({
          providerId: r.providerId, model: r.model,
        }));
      }
      if (routingData.strategy) mainStrategy = routingData.strategy;
    }
  } catch (e) { console.error("Failed to fetch routing config:", e); }

  return {
    stats, dailyTokensData, dailyCostData, providers,
    providerPieData, providerCostData, records,
    providerConfig, providerPool, mainStrategy,
  };
}

interface LoaderData {
  stats: UsageStats;
  dailyTokensData: { date: string; tokens: number }[];
  dailyCostData: Record<string, unknown>[];
  providers: string[];
  providerPieData: { name: string; value: number; tokens: number; cost: number }[];
  providerCostData: { name: string; cost: number }[];
  records: UsageRecord[];
  providerConfig: ProviderItem[];
  providerPool: ProviderPoolItem[];
  mainStrategy: string;
}

// ============== 时间范围曲线图组件 ==============
function TimeSeriesChart() {
  const [range, setRange] = useState(24);
  const [data, setData] = useState<TimeSeriesPoint[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchData = useCallback(async (hours: number) => {
    setLoading(true);
    try {
      const resp = await fetch(`/api/llm-usage?action=timeseries&hours=${hours}`);
      if (resp.ok) setData(await resp.json());
    } catch { /* ignore */ }
    setLoading(false);
  }, []);

  useEffect(() => { fetchData(range); }, [range, fetchData]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between text-base">
          <span>LLM 调用趋势</span>
          <div className="flex flex-wrap gap-1">
            {TIME_RANGES.map((tr) => (
              <button
                key={tr.hours}
                onClick={() => setRange(tr.hours)}
                className={cn(
                  "px-2 py-0.5 rounded text-xs font-medium transition-colors",
                  range === tr.hours
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted text-muted-foreground hover:bg-muted/80"
                )}
              >
                {tr.label}
              </button>
            ))}
          </div>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="flex h-[300px] items-center justify-center text-muted-foreground">加载中...</div>
        ) : data.length > 0 ? (
          <div className="space-y-6">
            {/* 调用次数曲线 */}
            <div>
              <div className="text-sm font-medium text-muted-foreground mb-2">调用次数</div>
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={data}>
                  <XAxis dataKey="time" fontSize={11} angle={-30} textAnchor="end" height={50} />
                  <YAxis fontSize={12} />
                  <Tooltip labelFormatter={(v) => `${v}`} formatter={(v: number) => [v, "次调用"]} />
                  <Line type="monotone" dataKey="calls" stroke="#3b82f6" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
            {/* Token 消耗曲线 */}
            <div>
              <div className="text-sm font-medium text-muted-foreground mb-2">Token 消耗</div>
              <ResponsiveContainer width="100%" height={200}>
                <AreaChart data={data}>
                  <XAxis dataKey="time" fontSize={11} angle={-30} textAnchor="end" height={50} />
                  <YAxis fontSize={12} tickFormatter={(v) => formatNumber(v)} />
                  <Tooltip labelFormatter={(v) => `${v}`} formatter={(v: number) => [formatNumber(v), "tokens"]} />
                  <Area type="monotone" dataKey="tokens" stroke="#8b5cf6" fill="#8b5cf6" fillOpacity={0.3} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
            {/* 费用曲线 */}
            <div>
              <div className="text-sm font-medium text-muted-foreground mb-2">费用 (USD)</div>
              <ResponsiveContainer width="100%" height={200}>
                <AreaChart data={data}>
                  <XAxis dataKey="time" fontSize={11} angle={-30} textAnchor="end" height={50} />
                  <YAxis fontSize={12} tickFormatter={(v) => `$${v.toFixed(4)}`} />
                  <Tooltip labelFormatter={(v) => `${v}`} formatter={(v: number) => [formatUSD(v), "费用"]} />
                  <Area type="monotone" dataKey="cost_usd" stroke="#22c55e" fill="#22c55e" fillOpacity={0.3} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
        ) : (
          <div className="flex h-[300px] items-center justify-center text-muted-foreground">暂无数据</div>
        )}
      </CardContent>
    </Card>
  );
}

// ============== 使用类型分布图组件 ==============
function UsageTypeChart() {
  const [data, setData] = useState<UsageTypeData[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const resp = await fetch("/api/llm-usage?action=usage_types");
        if (resp.ok) setData(await resp.json());
      } catch { /* ignore */ }
      setLoading(false);
    })();
  }, []);

  if (loading) return null;
  if (data.length === 0) return null;

  const totalCalls = data.reduce((s, d) => s + d.calls, 0);
  const totalTokens = data.reduce((s, d) => s + d.tokens, 0);

  const callsPieData = data.map((d) => ({
    name: USAGE_TYPE_LABELS[d.usage_type] || d.usage_type,
    value: d.calls,
    key: d.usage_type,
  }));

  const tokensPieData = data.map((d) => ({
    name: USAGE_TYPE_LABELS[d.usage_type] || d.usage_type,
    value: d.tokens,
    key: d.usage_type,
  }));

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">使用类型分布（按调用次数）</CardTitle>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={280}>
            <PieChart>
              <Pie
                data={callsPieData}
                cx="50%"
                cy="50%"
                innerRadius={55}
                outerRadius={85}
                paddingAngle={3}
                dataKey="value"
                label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
              >
                {callsPieData.map((entry) => (
                  <Cell key={entry.key} fill={USAGE_TYPE_COLORS[entry.key] || "#666"} />
                ))}
              </Pie>
              <Tooltip formatter={(v: number) => [`${v} 次 (${totalCalls > 0 ? ((v / totalCalls) * 100).toFixed(1) : 0}%)`, "调用次数"]} />
            </PieChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">使用类型分布（按 Token 消耗）</CardTitle>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={280}>
            <PieChart>
              <Pie
                data={tokensPieData}
                cx="50%"
                cy="50%"
                innerRadius={55}
                outerRadius={85}
                paddingAngle={3}
                dataKey="value"
                label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
              >
                {tokensPieData.map((entry) => (
                  <Cell key={entry.key} fill={USAGE_TYPE_COLORS[entry.key] || "#666"} />
                ))}
              </Pie>
              <Tooltip formatter={(v: number) => [`${formatNumber(v)} tokens (${totalTokens > 0 ? ((v / totalTokens) * 100).toFixed(1) : 0}%)`, "Token"]} />
            </PieChart>
          </ResponsiveContainer>
          {/* 明细列表 */}
          <div className="mt-4 space-y-1.5">
            {data.map((d) => (
              <div key={d.usage_type} className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-2">
                  <div className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: USAGE_TYPE_COLORS[d.usage_type] || "#666" }} />
                  <span>{USAGE_TYPE_LABELS[d.usage_type] || d.usage_type}</span>
                </div>
                <div className="flex gap-4 text-muted-foreground">
                  <span>{d.calls} 次</span>
                  <span>{formatNumber(d.tokens)} tok</span>
                  <span>{formatUSD(d.cost_usd)}</span>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// ============== 主页面 ==============
export default function LLMUsagePage() {
  const {
    stats, dailyTokensData, dailyCostData, providers,
    providerPieData, providerCostData, records,
    providerConfig, providerPool, mainStrategy: initialStrategy,
  } = useLoaderData<LoaderData>();

  const [selectedRecord, setSelectedRecord] = useState<UsageRecord | null>(null);
  const [providerList, setProviderList] = useState<ProviderItem[]>(providerConfig);
  const [strategy, setStrategy] = useState(initialStrategy);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");

  const enabledProviders = providerPool.filter((p) => p.isEnabled);

  const moveProvider = useCallback((index: number, direction: -1 | 1) => {
    const newIndex = index + direction;
    if (newIndex < 0 || newIndex >= providerList.length) return;
    const newList = [...providerList];
    [newList[index], newList[newIndex]] = [newList[newIndex], newList[index]];
    setProviderList(newList);
  }, [providerList]);

  const addProvider = useCallback(() => {
    if (enabledProviders.length === 0) return;
    const first = enabledProviders[0];
    setProviderList((prev) => [...prev, { providerId: first.id, model: first.models[0] || "" }]);
  }, [enabledProviders]);

  const removeProvider = useCallback((index: number) => {
    setProviderList((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const updateProviderItem = useCallback((index: number, patch: Partial<ProviderItem>) => {
    setProviderList((prev) => prev.map((item, i) => (i === index ? { ...item, ...patch } : item)));
  }, []);

  const saveProviderConfig = useCallback(async () => {
    setSaving(true);
    setSaveMsg("");
    try {
      const resp = await fetch("/api/llm-config/routing", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scope: "main", strategy,
          items: providerList.map((r, i) => ({ providerId: r.providerId, model: r.model, priority: i + 1 })),
        }),
      });
      if (resp.ok) { setSaveMsg("已保存"); setTimeout(() => setSaveMsg(""), 3000); }
      else { const data = await resp.json(); setSaveMsg(`失败: ${data.error}`); }
    } catch { setSaveMsg("保存失败"); }
    finally { setSaving(false); }
  }, [providerList, strategy]);

  return (
    <div className="space-y-6">
      {/* 汇总卡片 */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard label="总计调用" value={formatNumber(stats.total_calls)} icon={Cpu} />
        <StatCard label="总计 Token" value={formatNumber(stats.total_tokens)} icon={Clock} />
        <StatCard label="总计费用" value={formatUSD(stats.total_cost_usd)} icon={Coins} />
        <StatCard label="今日费用" value={formatUSD(stats.today_cost_usd)} icon={Coins} variant={stats.today_cost_usd > 0 ? "loss" : "default"} />
      </div>

      {/* LLM 调用趋势（多时间范围曲线图） */}
      <TimeSeriesChart />

      {/* 使用类型分布图 */}
      <UsageTypeChart />

      {/* Provider 调用优先级配置 */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between text-base">
            <span>模型调用优先级</span>
            <div className="flex items-center gap-2">
              {saveMsg && (
                <span className={cn("text-xs", saveMsg === "已保存" ? "text-green-500" : "text-red-500")}>{saveMsg}</span>
              )}
              <Button size="sm" onClick={saveProviderConfig} disabled={saving}>
                <Save className="mr-1 h-4 w-4" />
                {saving ? "保存中..." : "保存"}
              </Button>
            </div>
          </CardTitle>
          <p className="text-xs text-muted-foreground">
            按优先级排列，排在前面的模型优先调用，失败后自动回退到下一个
          </p>
        </CardHeader>
        <CardContent>
          <div className="mb-4">
            <label className="block text-sm text-muted-foreground mb-1">调度策略</label>
            <select
              value={strategy}
              onChange={(e) => setStrategy(e.target.value)}
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
            >
              <option value="priority">优先级 (priority)</option>
              <option value="cost_first">成本优先 (cost_first)</option>
              <option value="round_robin">轮询 (round_robin)</option>
            </select>
          </div>

          <div className="space-y-2 mb-4">
            {providerList.length === 0 && (
              <p className="text-sm text-muted-foreground py-4 text-center">暂无调度项，请点击下方添加</p>
            )}
            {providerList.map((p, i) => {
              const prov = providerPool.find((pp) => pp.id === p.providerId);
              return (
                <div key={`prov-${i}`} className="flex items-center gap-2 rounded-lg border p-3">
                  <span className="w-6 text-center text-sm font-medium text-muted-foreground">{i + 1}</span>
                  <select
                    value={p.providerId}
                    onChange={(e) => {
                      const newId = Number(e.target.value);
                      const np = providerPool.find((pp) => pp.id === newId);
                      updateProviderItem(i, { providerId: newId, model: np?.models[0] || "" });
                    }}
                    className="rounded-md border border-border bg-background px-2 py-1.5 text-sm flex-1 min-w-0"
                  >
                    {enabledProviders.map((ep) => (
                      <option key={ep.id} value={ep.id}>{ep.displayName}</option>
                    ))}
                  </select>
                  <select
                    value={p.model}
                    onChange={(e) => updateProviderItem(i, { model: e.target.value })}
                    className="rounded-md border border-border bg-background px-2 py-1.5 text-sm flex-1 min-w-0"
                  >
                    {(prov?.models || []).map((m) => (
                      <option key={m} value={m}>{m}</option>
                    ))}
                  </select>
                  <div className="flex gap-1">
                    <Button variant="ghost" size="sm" className="h-8 w-8 p-0" disabled={i === 0} onClick={() => moveProvider(i, -1)}>
                      <ChevronUp className="h-4 w-4" />
                    </Button>
                    <Button variant="ghost" size="sm" className="h-8 w-8 p-0" disabled={i === providerList.length - 1} onClick={() => moveProvider(i, 1)}>
                      <ChevronDown className="h-4 w-4" />
                    </Button>
                    <Button variant="ghost" size="sm" className="h-8 w-8 p-0 text-red-400 hover:text-red-300" onClick={() => removeProvider(i)}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
          <Button variant="outline" size="sm" onClick={addProvider} disabled={enabledProviders.length === 0}>
            <Plus className="mr-1 h-4 w-4" /> 添加
          </Button>
        </CardContent>
      </Card>

      {/* 成功率和延迟 */}
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader><CardTitle className="text-base">成功率</CardTitle></CardHeader>
          <CardContent>
            <div className="flex items-center gap-4">
              <CheckCircle className={cn(
                "h-12 w-12",
                stats.success_rate >= 95 ? "text-green-500" : stats.success_rate >= 80 ? "text-yellow-500" : "text-red-500"
              )} />
              <div>
                <div className="text-3xl font-bold">{stats.success_rate.toFixed(1)}%</div>
                <div className="text-sm text-muted-foreground">请求成功率</div>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-base">平均延迟</CardTitle></CardHeader>
          <CardContent>
            <div className="flex items-center gap-4">
              <Clock className="h-12 w-12 text-blue-500" />
              <div>
                <div className="text-3xl font-bold">{stats.avg_latency_ms.toFixed(0)} ms</div>
                <div className="text-sm text-muted-foreground">平均响应时间</div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* 每日 Token 消耗曲线 */}
      <Card>
        <CardHeader><CardTitle className="text-base">每日 Token 消耗</CardTitle></CardHeader>
        <CardContent>
          {dailyTokensData.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={dailyTokensData}>
                <XAxis dataKey="date" tickFormatter={(v) => v.slice(5)} fontSize={12} />
                <YAxis fontSize={12} tickFormatter={(v) => formatNumber(v)} />
                <Tooltip labelFormatter={(v) => `日期: ${v}`} formatter={(v: number) => [formatNumber(v), "Token"]} />
                <Line type="monotone" dataKey="tokens" stroke="#3b82f6" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-[300px] items-center justify-center text-muted-foreground">暂无数据</div>
          )}
        </CardContent>
      </Card>

      {/* 每日费用曲线（堆叠面积图） */}
      <Card>
        <CardHeader><CardTitle className="text-base">每日费用趋势（按 Provider）</CardTitle></CardHeader>
        <CardContent>
          {dailyCostData.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <AreaChart data={dailyCostData}>
                <XAxis dataKey="date" tickFormatter={(v) => v.slice(5)} fontSize={12} />
                <YAxis fontSize={12} tickFormatter={(v) => `$${v.toFixed(2)}`} />
                <Tooltip labelFormatter={(v) => `日期: ${v}`} formatter={(v: number, name: string) => [formatUSD(v), name]} />
                <Legend />
                {providers.map((provider) => (
                  <Area
                    key={provider}
                    type="monotone"
                    dataKey={provider}
                    stackId="1"
                    stroke={PROVIDER_COLORS[provider] || "#666"}
                    fill={PROVIDER_COLORS[provider] || "#666"}
                    fillOpacity={0.6}
                  />
                ))}
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-[300px] items-center justify-center text-muted-foreground">暂无数据</div>
          )}
        </CardContent>
      </Card>

      {/* Provider 占比和费用 */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle className="text-base">Provider 调用占比</CardTitle></CardHeader>
          <CardContent>
            {providerPieData.length > 0 ? (
              <ResponsiveContainer width="100%" height={250}>
                <PieChart>
                  <Pie
                    data={providerPieData} cx="50%" cy="50%"
                    innerRadius={60} outerRadius={80} paddingAngle={5} dataKey="value"
                    label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                  >
                    {providerPieData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={PROVIDER_COLORS[entry.name] || "#666"} />
                    ))}
                  </Pie>
                  <Tooltip
                    formatter={(v: number, _name: string, props: any) => [
                      `${v} 次调用, ${formatNumber(props.payload.tokens)} tokens`,
                      props.payload.name,
                    ]}
                  />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-[250px] items-center justify-center text-muted-foreground">暂无数据</div>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-base">Provider 费用统计</CardTitle></CardHeader>
          <CardContent>
            {providerCostData.length > 0 ? (
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={providerCostData} layout="vertical">
                  <XAxis type="number" fontSize={12} tickFormatter={(v) => `$${v.toFixed(2)}`} />
                  <YAxis type="category" dataKey="name" fontSize={12} width={80} />
                  <Tooltip formatter={(v: number) => [formatUSD(v), "费用"]} />
                  <Bar dataKey="cost" radius={[0, 4, 4, 0]}>
                    {providerCostData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={PROVIDER_COLORS[entry.name] || "#666"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-[250px] items-center justify-center text-muted-foreground">暂无数据</div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* 历史记录表格 */}
      <Card>
        <CardHeader><CardTitle className="text-base">最近调用记录</CardTitle></CardHeader>
        <CardContent>
          {records.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b">
                    <th className="text-left py-2 px-3 font-medium">时间</th>
                    <th className="text-left py-2 px-3 font-medium">类型</th>
                    <th className="text-left py-2 px-3 font-medium">Provider</th>
                    <th className="text-left py-2 px-3 font-medium">Model</th>
                    <th className="text-right py-2 px-3 font-medium">Input</th>
                    <th className="text-right py-2 px-3 font-medium">Output</th>
                    <th className="text-right py-2 px-3 font-medium">费用</th>
                    <th className="text-center py-2 px-3 font-medium">状态</th>
                  </tr>
                </thead>
                <tbody>
                  {records.map((record) => (
                    <tr
                      key={record.id}
                      className="border-b last:border-0 cursor-pointer hover:bg-muted/50 transition-colors"
                      onClick={() => setSelectedRecord(record)}
                    >
                      <td className="py-2 px-3 text-muted-foreground">
                        {new Date(record.timestamp).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })}
                      </td>
                      <td className="py-2 px-3">
                        <span
                          className="px-1.5 py-0.5 rounded text-xs font-medium"
                          style={{ backgroundColor: (USAGE_TYPE_COLORS[record.usage_type] || "#666") + "20", color: USAGE_TYPE_COLORS[record.usage_type] || "#666" }}
                        >
                          {USAGE_TYPE_LABELS[record.usage_type] || record.usage_type}
                        </span>
                      </td>
                      <td className="py-2 px-3">
                        <span className="px-2 py-0.5 rounded text-xs font-medium text-white" style={{ backgroundColor: PROVIDER_COLORS[record.provider] || "#666" }}>
                          {record.provider}
                        </span>
                      </td>
                      <td className="py-2 px-3 font-mono text-xs">
                        {record.model.length > 20 ? record.model.slice(0, 20) + "..." : record.model}
                      </td>
                      <td className="py-2 px-3 text-right">{formatNumber(record.input_tokens)}</td>
                      <td className="py-2 px-3 text-right">{formatNumber(record.output_tokens)}</td>
                      <td className="py-2 px-3 text-right">{formatUSD(record.cost_usd)}</td>
                      <td className="py-2 px-3 text-center">
                        {record.success ? (
                          <span className="text-green-500">✓</span>
                        ) : (
                          <span className="text-red-500" title={record.error_message ?? undefined}>✗</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="flex h-[200px] items-center justify-center text-muted-foreground">暂无调用记录</div>
          )}
        </CardContent>
      </Card>

      {/* 明细弹窗 */}
      {selectedRecord && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setSelectedRecord(null)}>
          <div className="relative w-full max-w-lg rounded-lg border bg-background p-6 shadow-lg" onClick={(e) => e.stopPropagation()}>
            <button className="absolute right-4 top-4 text-muted-foreground hover:text-foreground" onClick={() => setSelectedRecord(null)}>
              <X className="h-5 w-5" />
            </button>
            <h3 className="mb-4 text-lg font-semibold">调用详情</h3>
            <div className="space-y-3 text-sm">
              <div className="flex justify-between border-b pb-2">
                <span className="text-muted-foreground">时间</span>
                <span>{new Date(selectedRecord.timestamp).toLocaleString("zh-CN")}</span>
              </div>
              <div className="flex justify-between border-b pb-2">
                <span className="text-muted-foreground">类型</span>
                <span
                  className="rounded px-1.5 py-0.5 text-xs font-medium"
                  style={{ backgroundColor: (USAGE_TYPE_COLORS[selectedRecord.usage_type] || "#666") + "20", color: USAGE_TYPE_COLORS[selectedRecord.usage_type] || "#666" }}
                >
                  {USAGE_TYPE_LABELS[selectedRecord.usage_type] || selectedRecord.usage_type}
                </span>
              </div>
              <div className="flex justify-between border-b pb-2">
                <span className="text-muted-foreground">Provider</span>
                <span className="rounded px-2 py-0.5 text-xs font-medium text-white" style={{ backgroundColor: PROVIDER_COLORS[selectedRecord.provider] || "#666" }}>
                  {selectedRecord.provider}
                </span>
              </div>
              <div className="flex justify-between border-b pb-2">
                <span className="text-muted-foreground">Model</span>
                <span className="font-mono text-xs">{selectedRecord.model}</span>
              </div>
              <div className="flex justify-between border-b pb-2">
                <span className="text-muted-foreground">Input Tokens</span>
                <span className="tabular-nums">{formatNumber(selectedRecord.input_tokens)}</span>
              </div>
              <div className="flex justify-between border-b pb-2">
                <span className="text-muted-foreground">Output Tokens</span>
                <span className="tabular-nums">{formatNumber(selectedRecord.output_tokens)}</span>
              </div>
              <div className="flex justify-between border-b pb-2">
                <span className="text-muted-foreground">Total Tokens</span>
                <span className="tabular-nums font-medium">{formatNumber(selectedRecord.total_tokens)}</span>
              </div>
              <div className="flex justify-between border-b pb-2">
                <span className="text-muted-foreground">费用</span>
                <span className="font-medium">{formatUSD(selectedRecord.cost_usd)}</span>
              </div>
              <div className="flex justify-between border-b pb-2">
                <span className="text-muted-foreground">延迟</span>
                <span className="tabular-nums">{selectedRecord.latency_ms.toFixed(0)} ms</span>
              </div>
              <div className="flex justify-between border-b pb-2">
                <span className="text-muted-foreground">状态</span>
                <span className={selectedRecord.success ? "text-green-500" : "text-red-500"}>
                  {selectedRecord.success ? "成功" : "失败"}
                </span>
              </div>
              {selectedRecord.error_message && (
                <div className="border-b pb-2">
                  <div className="text-muted-foreground mb-1">错误信息</div>
                  <div className="rounded bg-red-500/10 p-2 text-xs text-red-500 break-all">{selectedRecord.error_message}</div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
