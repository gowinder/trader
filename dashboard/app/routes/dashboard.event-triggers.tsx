import { useState, useEffect, useCallback, useRef } from "react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "~/components/ui/tabs";
import { Card, CardContent } from "~/components/ui/card";
import { Button } from "~/components/ui/button";
import { Input } from "~/components/ui/input";
import { Label } from "~/components/ui/label";
import { Switch } from "~/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select";
import { ChevronLeft, ChevronRight, Check } from "lucide-react";

// ==================== 类型定义 ====================

interface TriggerLog {
  id: number;
  symbol: string;
  eventType: string;
  severity: string;
  description: string;
  keyData: Record<string, unknown> | null;
  triggeredAt: string;
  createdAt: string;
}

interface EventConfig {
  enabled: boolean;
  [key: string]: unknown;
}

interface FullConfig {
  enabled: boolean;
  scan_interval_seconds: number;
  global_cooldown_seconds: number;
  per_event_cooldown_seconds: number;
  reset_decision_timer: boolean;
  events: Record<string, EventConfig>;
}

const DEFAULT_CONFIG: FullConfig = {
  enabled: true,
  scan_interval_seconds: 30,
  global_cooldown_seconds: 300,
  per_event_cooldown_seconds: 600,
  reset_decision_timer: true,
  events: {
    price_surge: { enabled: true, atr_multiplier: 1.5, lookback_seconds: 300 },
    volume_spike: { enabled: true, volume_multiplier: 2.5 },
    rsi_extreme: { enabled: true, upper_threshold: 75, lower_threshold: 25 },
    macd_cross: { enabled: true },
    bollinger_break: { enabled: true },
    market_state_change: { enabled: true },
    position_pnl: { enabled: true, profit_threshold_percent: 3.0, loss_threshold_percent: -2.0 },
  },
};

const EVENT_LABELS: Record<string, string> = {
  price_surge: "Price Surge",
  volume_spike: "Volume Spike",
  rsi_extreme: "RSI Extreme",
  macd_cross: "MACD Cross",
  bollinger_break: "Bollinger Break",
  market_state_change: "Market State Change",
  position_pnl: "Position PnL",
};

const EVENT_PARAMS: Record<string, { key: string; label: string }[]> = {
  price_surge: [
    { key: "atr_multiplier", label: "ATR 倍数" },
    { key: "lookback_seconds", label: "回看秒数" },
  ],
  volume_spike: [{ key: "volume_multiplier", label: "成交量倍数" }],
  rsi_extreme: [
    { key: "upper_threshold", label: "上阈值" },
    { key: "lower_threshold", label: "下阈值" },
  ],
  macd_cross: [],
  bollinger_break: [],
  market_state_change: [],
  position_pnl: [
    { key: "profit_threshold_percent", label: "止盈阈值(%)" },
    { key: "loss_threshold_percent", label: "止损阈值(%)" },
  ],
};

const SEVERITY_COLORS: Record<string, string> = {
  high: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
  medium: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400",
  low: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
};

const TIME_RANGES = [
  { label: "过去 1 小时", value: "1h" },
  { label: "过去 6 小时", value: "6h" },
  { label: "过去 24 小时", value: "24h" },
  { label: "过去 7 天", value: "7d" },
  { label: "全部", value: "all" },
];

// ==================== Toast ====================

function Toast({ toast, onClose }: { toast: { type: string; message: string } | null; onClose: () => void }) {
  useEffect(() => {
    if (toast) {
      const t = setTimeout(onClose, 3000);
      return () => clearTimeout(t);
    }
  }, [toast, onClose]);

  if (!toast) return null;
  return (
    <div className={`fixed right-4 top-4 z-50 rounded-md px-4 py-2 text-sm font-medium text-white shadow-lg ${toast.type === "success" ? "bg-green-600" : "bg-red-600"}`}>
      {toast.message}
    </div>
  );
}

// ==================== 触发记录 Tab ====================

function LogsTab() {
  const [logs, setLogs] = useState<TriggerLog[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 筛选 — 使用 "all" 而非空字符串，兼容 Radix UI Select
  const [symbol, setSymbol] = useState("all");
  const [eventType, setEventType] = useState("all");
  const [severity, setSeverity] = useState("all");
  const [timeRange, setTimeRange] = useState("24h");

  const limit = 20;
  const totalPages = Math.ceil(total / limit);

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (symbol !== "all") params.set("symbol", symbol);
      if (eventType !== "all") params.set("type", eventType);
      if (severity !== "all") params.set("severity", severity);
      params.set("page", String(page));
      params.set("limit", String(limit));

      if (timeRange !== "all") {
        const now = new Date();
        const hours: Record<string, number> = { "1h": 1, "6h": 6, "24h": 24, "7d": 168 };
        const from = new Date(now.getTime() - (hours[timeRange] || 24) * 3600000);
        params.set("from", from.toISOString());
      }

      const res = await fetch(`/api/event-triggers/logs?${params}`);
      if (res.ok) {
        const data = await res.json();
        setLogs(data.logs || []);
        setTotal(data.total || 0);
      } else {
        setError("加载失败");
      }
    } catch {
      setError("网络错误");
    } finally {
      setLoading(false);
    }
  }, [symbol, eventType, severity, timeRange, page]);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  // 重置页码当筛选变化
  useEffect(() => {
    setPage(1);
  }, [symbol, eventType, severity, timeRange]);

  return (
    <div className="space-y-4">
      {/* 筛选栏 */}
      <div className="flex flex-wrap gap-3">
        <Select value={symbol} onValueChange={setSymbol}>
          <SelectTrigger className="w-[140px]">
            <SelectValue placeholder="全部币种" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部币种</SelectItem>
            <SelectItem value="BTCUSDT">BTCUSDT</SelectItem>
            <SelectItem value="ETHUSDT">ETHUSDT</SelectItem>
            <SelectItem value="SOLUSDT">SOLUSDT</SelectItem>
          </SelectContent>
        </Select>

        <Select value={eventType} onValueChange={setEventType}>
          <SelectTrigger className="w-[160px]">
            <SelectValue placeholder="全部事件" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部事件</SelectItem>
            {Object.entries(EVENT_LABELS).map(([k, v]) => (
              <SelectItem key={k} value={k}>{v}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={severity} onValueChange={setSeverity}>
          <SelectTrigger className="w-[130px]">
            <SelectValue placeholder="全部级别" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部级别</SelectItem>
            <SelectItem value="high">High</SelectItem>
            <SelectItem value="medium">Medium</SelectItem>
            <SelectItem value="low">Low</SelectItem>
          </SelectContent>
        </Select>

        <Select value={timeRange} onValueChange={setTimeRange}>
          <SelectTrigger className="w-[150px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {TIME_RANGES.map((r) => (
              <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* 错误提示 */}
      {error && (
        <div className="rounded-md bg-red-100 px-4 py-2 text-sm text-red-800 dark:bg-red-900/30 dark:text-red-400">
          {error}
        </div>
      )}

      {/* 表格 */}
      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="px-4 py-3 text-left font-medium">时间</th>
                  <th className="px-4 py-3 text-left font-medium">币种</th>
                  <th className="px-4 py-3 text-left font-medium">事件类型</th>
                  <th className="px-4 py-3 text-left font-medium">严重程度</th>
                  <th className="px-4 py-3 text-left font-medium">描述</th>
                  <th className="px-4 py-3 text-left font-medium">关键数据</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">加载中...</td>
                  </tr>
                ) : logs.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">暂无触发记录</td>
                  </tr>
                ) : (
                  logs.map((log) => (
                    <tr key={log.id} className="border-b hover:bg-muted/30">
                      <td className="whitespace-nowrap px-4 py-3">
                        {new Date(log.triggeredAt).toLocaleString("zh-CN")}
                      </td>
                      <td className="px-4 py-3 font-mono text-xs">{log.symbol}</td>
                      <td className="px-4 py-3">
                        <span className="rounded bg-muted px-2 py-0.5 text-xs">
                          {EVENT_LABELS[log.eventType] || log.eventType}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`rounded px-2 py-0.5 text-xs font-medium ${SEVERITY_COLORS[log.severity] || ""}`}>
                          {log.severity}
                        </span>
                      </td>
                      <td className="max-w-[300px] truncate px-4 py-3" title={log.description}>
                        {log.description}
                      </td>
                      <td className="px-4 py-3">
                        {log.keyData ? (
                          <span className="cursor-help rounded bg-muted px-2 py-0.5 font-mono text-xs" title={JSON.stringify(log.keyData, null, 2)}>
                            JSON
                          </span>
                        ) : (
                          <span className="text-muted-foreground">-</span>
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

      {/* 分页 */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">
            共 {total} 条，第 {page}/{totalPages} 页
          </span>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

// ==================== 事件配置 Tab ====================

function ConfigTab() {
  const [config, setConfig] = useState<FullConfig>(DEFAULT_CONFIG);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<{ type: string; message: string } | null>(null);
  const debounceTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  const showToast = useCallback((type: "success" | "error", message: string) => {
    setToast({ type, message });
  }, []);

  useEffect(() => {
    fetch("/api/event-triggers/config")
      .then((r) => r.json())
      .then((data) => {
        if (data.config) setConfig(data.config);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const saveConfig = useCallback(async (newConfig: FullConfig) => {
    try {
      const res = await fetch("/api/event-triggers/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ config: newConfig }),
      });
      if (res.ok) {
        showToast("success", "已保存");
      } else {
        showToast("error", "保存失败");
      }
    } catch {
      showToast("error", "保存失败");
    }
  }, [showToast]);

  const updateGlobal = useCallback((key: string, value: unknown) => {
    setConfig((prev) => {
      const next = { ...prev, [key]: value };
      saveConfig(next);
      return next;
    });
  }, [saveConfig]);

  const updateGlobalDebounced = useCallback((key: string, value: number) => {
    setConfig((prev) => ({ ...prev, [key]: value }));
    if (debounceTimers.current[key]) clearTimeout(debounceTimers.current[key]);
    debounceTimers.current[key] = setTimeout(() => {
      setConfig((prev) => {
        saveConfig(prev);
        return prev;
      });
    }, 500);
  }, [saveConfig]);

  const updateEvent = useCallback((eventType: string, key: string, value: unknown) => {
    setConfig((prev) => {
      const next = {
        ...prev,
        events: {
          ...prev.events,
          [eventType]: { ...prev.events[eventType], [key]: value },
        },
      };
      if (key === "enabled") {
        saveConfig(next);
      }
      return next;
    });
  }, [saveConfig]);

  const updateEventDebounced = useCallback((eventType: string, key: string, value: number) => {
    const timerKey = `${eventType}.${key}`;
    setConfig((prev) => ({
      ...prev,
      events: {
        ...prev.events,
        [eventType]: { ...prev.events[eventType], [key]: value },
      },
    }));
    if (debounceTimers.current[timerKey]) clearTimeout(debounceTimers.current[timerKey]);
    debounceTimers.current[timerKey] = setTimeout(() => {
      setConfig((prev) => {
        saveConfig(prev);
        return prev;
      });
    }, 500);
  }, [saveConfig]);

  if (loading) {
    return <div className="py-8 text-center text-muted-foreground">加载中...</div>;
  }

  return (
    <div className="space-y-6">
      <Toast toast={toast} onClose={() => setToast(null)} />

      {/* 全局配置 */}
      <Card>
        <CardContent className="space-y-4 p-6">
          <h3 className="text-lg font-semibold">全局设置</h3>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <div className="flex items-center justify-between rounded-md border p-3">
              <Label>事件触发总开关</Label>
              <Switch checked={config.enabled} onCheckedChange={(v) => updateGlobal("enabled", v)} />
            </div>
            <div className="flex items-center justify-between rounded-md border p-3">
              <Label>触发后重置定时器</Label>
              <Switch checked={config.reset_decision_timer} onCheckedChange={(v) => updateGlobal("reset_decision_timer", v)} />
            </div>
            <div className="space-y-1 rounded-md border p-3">
              <Label>扫描间隔(秒)</Label>
              <Input
                type="number"
                value={config.scan_interval_seconds}
                onChange={(e) => updateGlobalDebounced("scan_interval_seconds", Number(e.target.value))}
              />
            </div>
            <div className="space-y-1 rounded-md border p-3">
              <Label>全局冷却(秒)</Label>
              <Input
                type="number"
                value={config.global_cooldown_seconds}
                onChange={(e) => updateGlobalDebounced("global_cooldown_seconds", Number(e.target.value))}
              />
            </div>
            <div className="space-y-1 rounded-md border p-3">
              <Label>单事件冷却(秒)</Label>
              <Input
                type="number"
                value={config.per_event_cooldown_seconds}
                onChange={(e) => updateGlobalDebounced("per_event_cooldown_seconds", Number(e.target.value))}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* 事件卡片 */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Object.entries(EVENT_LABELS).map(([eventType, label]) => {
          const evtConfig = config.events[eventType] || { enabled: true };
          const params = EVENT_PARAMS[eventType] || [];

          return (
            <Card key={eventType}>
              <CardContent className="space-y-3 p-4">
                <div className="flex items-center justify-between">
                  <h4 className="font-medium">{label}</h4>
                  <Switch
                    checked={evtConfig.enabled}
                    onCheckedChange={(v) => updateEvent(eventType, "enabled", v)}
                  />
                </div>
                {params.length > 0 ? (
                  params.map((p) => (
                    <div key={p.key} className="space-y-1">
                      <Label className="text-xs text-muted-foreground">{p.label}</Label>
                      <Input
                        type="number"
                        step="any"
                        value={(evtConfig[p.key] as number) ?? ""}
                        onChange={(e) => updateEventDebounced(eventType, p.key, Number(e.target.value))}
                        disabled={!evtConfig.enabled}
                      />
                    </div>
                  ))
                ) : (
                  <p className="text-xs text-muted-foreground">无额外参数</p>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}

// ==================== 策略映射 Tab ====================

function MappingTab() {
  const [mapping, setMapping] = useState<Record<string, string[]>>({});
  const [allEventTypes, setAllEventTypes] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/event-triggers/mapping")
      .then((r) => r.json())
      .then((data) => {
        setMapping(data.mapping || {});
        setAllEventTypes(data.allEventTypes || []);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <div className="py-8 text-center text-muted-foreground">加载中...</div>;
  }

  const strategies = Object.keys(mapping);

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        映射关系由代码定义（STRATEGY_EVENT_DEFAULTS），展示各策略关注的事件类型
      </p>

      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="px-4 py-3 text-left font-medium">策略</th>
                  {allEventTypes.map((et) => (
                    <th key={et} className="px-3 py-3 text-center font-medium">
                      <span className="text-xs">{EVENT_LABELS[et] || et}</span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {strategies.map((strategy) => (
                  <tr key={strategy} className="border-b hover:bg-muted/30">
                    <td className="whitespace-nowrap px-4 py-3 font-mono text-xs">{strategy}</td>
                    {allEventTypes.map((et) => (
                      <td key={et} className="px-3 py-3 text-center">
                        {mapping[strategy]?.includes(et) ? (
                          <Check className="mx-auto h-4 w-4 text-green-500" />
                        ) : null}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// ==================== 主页面 ====================

export default function EventTriggersPage() {
  return (
    <div className="space-y-6 p-6">
      <h1 className="text-2xl font-bold">事件触发管理</h1>

      <Tabs defaultValue="logs">
        <TabsList>
          <TabsTrigger value="logs">触发记录</TabsTrigger>
          <TabsTrigger value="config">事件配置</TabsTrigger>
          <TabsTrigger value="mapping">策略映射</TabsTrigger>
        </TabsList>

        <TabsContent value="logs">
          <LogsTab />
        </TabsContent>

        <TabsContent value="config">
          <ConfigTab />
        </TabsContent>

        <TabsContent value="mapping">
          <MappingTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
