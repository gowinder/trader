import type { LoaderFunctionArgs } from "react-router";
import { useLoaderData } from "react-router";
import { StatCard } from "~/components/common/StatCard";
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card";
import { cn } from "~/lib/utils";
import { Cpu, Coins, Clock, CheckCircle } from "lucide-react";
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
  id: number;
  timestamp: string;
  provider: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_usd: number;
  latency_ms: number;
  success: number;
  error_message: string;
}

const PROVIDER_COLORS: Record<string, string> = {
  qwen: "#6366f1",
  gemini: "#22c55e",
  codex: "#f59e0b",
  openrouter: "#ef4444",
  opencode: "#8b5cf6",
};

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toString();
}

function formatUSD(n: number): string {
  return `$${n.toFixed(2)}`;
}

export async function loader({ request }: LoaderFunctionArgs) {
  const baseUrl = new URL(request.url).origin;

  // 获取统计数据
  let stats: UsageStats = {
    total_calls: 0,
    total_tokens: 0,
    total_cost_usd: 0,
    today_cost_usd: 0,
    success_rate: 0,
    avg_latency_ms: 0,
    by_provider: {},
  };

  let dailyStats: DailyStats[] = [];
  let records: UsageRecord[] = [];

  try {
    const statsResp = await fetch(`${baseUrl}/api/llm-usage?action=stats`);
    if (statsResp.ok) {
      stats = await statsResp.json();
    }
  } catch (e) {
    console.error("Failed to fetch stats:", e);
  }

  try {
    const dailyResp = await fetch(`${baseUrl}/api/llm-usage?action=daily&days=30`);
    if (dailyResp.ok) {
      dailyStats = await dailyResp.json();
    }
  } catch (e) {
    console.error("Failed to fetch daily stats:", e);
  }

  try {
    const recordsResp = await fetch(`${baseUrl}/api/llm-usage?action=records&limit=50`);
    if (recordsResp.ok) {
      const data = await recordsResp.json();
      records = data.records || [];
    }
  } catch (e) {
    console.error("Failed to fetch records:", e);
  }

  // 处理每日数据用于图表
  const dailyTokensMap = new Map<string, number>();
  const dailyCostMap = new Map<string, Record<string, number>>();

  for (const d of dailyStats) {
    // Token 汇总
    dailyTokensMap.set(d.date, (dailyTokensMap.get(d.date) || 0) + d.tokens);

    // 费用按 provider 汇总
    if (!dailyCostMap.has(d.date)) {
      dailyCostMap.set(d.date, {});
    }
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

  // Provider 占比数据
  const providerPieData = Object.entries(stats.by_provider).map(([name, data]) => ({
    name,
    value: data.calls,
    tokens: data.tokens,
    cost: data.cost_usd,
  }));

  // Provider 费用柱状图数据
  const providerCostData = Object.entries(stats.by_provider).map(([name, data]) => ({
    name,
    cost: data.cost_usd,
  }));

  return {
    stats,
    dailyTokensData,
    dailyCostData,
    providers,
    providerPieData,
    providerCostData,
    records,
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
}

export default function LLMUsagePage() {
  const {
    stats,
    dailyTokensData,
    dailyCostData,
    providers,
    providerPieData,
    providerCostData,
    records,
  } = useLoaderData<LoaderData>();

  return (
    <div className="space-y-6">
      {/* 汇总卡片 */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="总计调用"
          value={formatNumber(stats.total_calls)}
          icon={Cpu}
        />
        <StatCard
          label="总计 Token"
          value={formatNumber(stats.total_tokens)}
          icon={Clock}
        />
        <StatCard
          label="总计费用"
          value={formatUSD(stats.total_cost_usd)}
          icon={Coins}
        />
        <StatCard
          label="今日费用"
          value={formatUSD(stats.today_cost_usd)}
          icon={Coins}
          variant={stats.today_cost_usd > 0 ? "loss" : "default"}
        />
      </div>

      {/* 成功率和延迟 */}
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">成功率</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-4">
              <CheckCircle className={cn(
                "h-12 w-12",
                stats.success_rate >= 95 ? "text-green-500" :
                stats.success_rate >= 80 ? "text-yellow-500" : "text-red-500"
              )} />
              <div>
                <div className="text-3xl font-bold">{stats.success_rate.toFixed(1)}%</div>
                <div className="text-sm text-muted-foreground">请求成功率</div>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">平均延迟</CardTitle>
          </CardHeader>
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
        <CardHeader>
          <CardTitle className="text-base">每日 Token 消耗</CardTitle>
        </CardHeader>
        <CardContent>
          {dailyTokensData.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={dailyTokensData}>
                <XAxis
                  dataKey="date"
                  tickFormatter={(v) => v.slice(5)}
                  fontSize={12}
                />
                <YAxis
                  fontSize={12}
                  tickFormatter={(v) => formatNumber(v)}
                />
                <Tooltip
                  labelFormatter={(v) => `日期: ${v}`}
                  formatter={(v: number) => [formatNumber(v), "Token"]}
                />
                <Line
                  type="monotone"
                  dataKey="tokens"
                  stroke="#3b82f6"
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-[300px] items-center justify-center text-muted-foreground">
              暂无数据
            </div>
          )}
        </CardContent>
      </Card>

      {/* 每日费用曲线（堆叠面积图） */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">每日费用趋势（按 Provider）</CardTitle>
        </CardHeader>
        <CardContent>
          {dailyCostData.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <AreaChart data={dailyCostData}>
                <XAxis
                  dataKey="date"
                  tickFormatter={(v) => v.slice(5)}
                  fontSize={12}
                />
                <YAxis
                  fontSize={12}
                  tickFormatter={(v) => `$${v.toFixed(2)}`}
                />
                <Tooltip
                  labelFormatter={(v) => `日期: ${v}`}
                  formatter={(v: number, name: string) => [formatUSD(v), name]}
                />
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
            <div className="flex h-[300px] items-center justify-center text-muted-foreground">
              暂无数据
            </div>
          )}
        </CardContent>
      </Card>

      {/* Provider 占比和费用 */}
      <div className="grid gap-4 lg:grid-cols-2">
        {/* Provider 调用占比（饼图） */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Provider 调用占比</CardTitle>
          </CardHeader>
          <CardContent>
            {providerPieData.length > 0 ? (
              <ResponsiveContainer width="100%" height={250}>
                <PieChart>
                  <Pie
                    data={providerPieData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={80}
                    paddingAngle={5}
                    dataKey="value"
                    label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                  >
                    {providerPieData.map((entry, index) => (
                      <Cell
                        key={`cell-${index}`}
                        fill={PROVIDER_COLORS[entry.name] || "#666"}
                      />
                    ))}
                  </Pie>
                  <Tooltip
                    formatter={(v: number, name: string, props: any) => [
                      `${v} 次调用, ${formatNumber(props.payload.tokens)} tokens`,
                      props.payload.name,
                    ]}
                  />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-[250px] items-center justify-center text-muted-foreground">
                暂无数据
              </div>
            )}
          </CardContent>
        </Card>

        {/* Provider 费用统计（柱状图） */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Provider 费用统计</CardTitle>
          </CardHeader>
          <CardContent>
            {providerCostData.length > 0 ? (
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={providerCostData} layout="vertical">
                  <XAxis
                    type="number"
                    fontSize={12}
                    tickFormatter={(v) => `$${v.toFixed(2)}`}
                  />
                  <YAxis type="category" dataKey="name" fontSize={12} width={80} />
                  <Tooltip formatter={(v: number) => [formatUSD(v), "费用"]} />
                  <Bar dataKey="cost" radius={[0, 4, 4, 0]}>
                    {providerCostData.map((entry, index) => (
                      <Cell
                        key={`cell-${index}`}
                        fill={PROVIDER_COLORS[entry.name] || "#666"}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-[250px] items-center justify-center text-muted-foreground">
                暂无数据
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* 历史记录表格 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">最近调用记录</CardTitle>
        </CardHeader>
        <CardContent>
          {records.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b">
                    <th className="text-left py-2 px-3 font-medium">时间</th>
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
                    <tr key={record.id} className="border-b last:border-0">
                      <td className="py-2 px-3 text-muted-foreground">
                        {new Date(record.timestamp).toLocaleString("zh-CN", {
                          month: "2-digit",
                          day: "2-digit",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </td>
                      <td className="py-2 px-3">
                        <span
                          className="px-2 py-0.5 rounded text-xs font-medium text-white"
                          style={{ backgroundColor: PROVIDER_COLORS[record.provider] || "#666" }}
                        >
                          {record.provider}
                        </span>
                      </td>
                      <td className="py-2 px-3 font-mono text-xs">
                        {record.model.length > 20
                          ? record.model.slice(0, 20) + "..."
                          : record.model}
                      </td>
                      <td className="py-2 px-3 text-right">{formatNumber(record.input_tokens)}</td>
                      <td className="py-2 px-3 text-right">{formatNumber(record.output_tokens)}</td>
                      <td className="py-2 px-3 text-right">{formatUSD(record.cost_usd)}</td>
                      <td className="py-2 px-3 text-center">
                        {record.success ? (
                          <span className="text-green-500">✓</span>
                        ) : (
                          <span className="text-red-500" title={record.error_message}>✗</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="flex h-[200px] items-center justify-center text-muted-foreground">
              暂无调用记录
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
