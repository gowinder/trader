import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card";
import { Button } from "~/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select";
import { Label } from "~/components/ui/label";
import { Settings, Play, Clock, Calendar } from "lucide-react";

interface BacktestConfig {
  id?: string;
  enabled: boolean;
  scheduleType: "manual" | "daily" | "weekly";
  scheduleHour: number;
  scheduleDayOfWeek: number | null;
  symbols: string[];
  timeframe: string;
  lookbackDays: number;
  initialCapital: number;
  enableFilters: boolean;
  strategies: string[];
  updatedAt?: string;
}

const SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"];
const TIMEFRAMES = ["15m", "1h", "4h", "1d"];

export default function BacktestSettingsPage() {
  const [config, setConfig] = useState<BacktestConfig>({
    enabled: false,
    scheduleType: "manual",
    scheduleHour: 0,
    scheduleDayOfWeek: null,
    symbols: ["BTCUSDT"],
    timeframe: "1h",
    lookbackDays: 30,
    initialCapital: 10000,
    enableFilters: true,
    strategies: ["trend_following"],
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // 加载配置
  useEffect(() => {
    fetch("/api/backtest-config")
      .then((res) => res.json())
      .then((data) => {
        setConfig(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  // 保存配置
  const saveConfig = async () => {
    setSaving(true);
    try {
      await fetch("/api/backtest-config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      });
    } finally {
      setSaving(false);
    }
  };

  // 立即运行回测
  const runNow = async () => {
    const endDate = new Date().toISOString().split("T")[0];
    const startDate = new Date(Date.now() - config.lookbackDays * 24 * 60 * 60 * 1000)
      .toISOString()
      .split("T")[0];

    for (const symbol of config.symbols) {
      await fetch("/api/backtest-trigger", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol,
          startDate,
          endDate,
          interval: config.timeframe,
          capital: config.initialCapital,
        }),
      });
    }
  };

  if (loading) {
    return <div className="p-8 text-center text-muted-foreground">加载中...</div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Settings className="h-6 w-6" />
          回测设置
        </h1>
        <div className="flex gap-2">
          <Button variant="outline" onClick={runNow}>
            <Play className="mr-2 h-4 w-4" />
            立即运行
          </Button>
          <Button onClick={saveConfig} disabled={saving}>
            {saving ? "保存中..." : "保存配置"}
          </Button>
        </div>
      </div>

      {/* 调度配置 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Clock className="h-4 w-4" />
            调度配置
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-4">
            <Label>启用自动回测</Label>
            <input
              type="checkbox"
              checked={config.enabled}
              onChange={(e) => setConfig({ ...config, enabled: e.target.checked })}
              className="h-4 w-4"
            />
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            <div>
              <Label>调度类型</Label>
              <Select
                value={config.scheduleType}
                onValueChange={(v) =>
                  setConfig({ ...config, scheduleType: v as BacktestConfig["scheduleType"] })
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="manual">手动</SelectItem>
                  <SelectItem value="daily">每日</SelectItem>
                  <SelectItem value="weekly">每周</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {config.scheduleType !== "manual" && (
              <div>
                <Label>执行时间 (小时)</Label>
                <Select
                  value={String(config.scheduleHour)}
                  onValueChange={(v) => setConfig({ ...config, scheduleHour: parseInt(v) })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {Array.from({ length: 24 }, (_, i) => (
                      <SelectItem key={i} value={String(i)}>
                        {String(i).padStart(2, "0")}:00
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            {config.scheduleType === "weekly" && (
              <div>
                <Label>执行日</Label>
                <Select
                  value={String(config.scheduleDayOfWeek ?? 0)}
                  onValueChange={(v) => setConfig({ ...config, scheduleDayOfWeek: parseInt(v) })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="0">周日</SelectItem>
                    <SelectItem value="1">周一</SelectItem>
                    <SelectItem value="2">周二</SelectItem>
                    <SelectItem value="3">周三</SelectItem>
                    <SelectItem value="4">周四</SelectItem>
                    <SelectItem value="5">周五</SelectItem>
                    <SelectItem value="6">周六</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* 回测参数 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Calendar className="h-4 w-4" />
            回测参数
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <div>
              <Label>交易对</Label>
              <Select
                value={config.symbols[0]}
                onValueChange={(v) => setConfig({ ...config, symbols: [v] })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {SYMBOLS.map((s) => (
                    <SelectItem key={s} value={s}>
                      {s}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div>
              <Label>时间周期</Label>
              <Select
                value={config.timeframe}
                onValueChange={(v) => setConfig({ ...config, timeframe: v })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TIMEFRAMES.map((tf) => (
                    <SelectItem key={tf} value={tf}>
                      {tf}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div>
              <Label>回测天数</Label>
              <Select
                value={String(config.lookbackDays)}
                onValueChange={(v) => setConfig({ ...config, lookbackDays: parseInt(v) })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="7">7 天</SelectItem>
                  <SelectItem value="14">14 天</SelectItem>
                  <SelectItem value="30">30 天</SelectItem>
                  <SelectItem value="60">60 天</SelectItem>
                  <SelectItem value="90">90 天</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div>
              <Label>初始资金 (USDT)</Label>
              <Select
                value={String(config.initialCapital)}
                onValueChange={(v) => setConfig({ ...config, initialCapital: parseInt(v) })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="1000">1,000</SelectItem>
                  <SelectItem value="5000">5,000</SelectItem>
                  <SelectItem value="10000">10,000</SelectItem>
                  <SelectItem value="50000">50,000</SelectItem>
                  <SelectItem value="100000">100,000</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <Label>启用信号过滤</Label>
            <input
              type="checkbox"
              checked={config.enableFilters}
              onChange={(e) => setConfig({ ...config, enableFilters: e.target.checked })}
              className="h-4 w-4"
            />
          </div>
        </CardContent>
      </Card>

      {/* 配置信息 */}
      {config.updatedAt && (
        <div className="text-sm text-muted-foreground">
          最后更新: {new Date(config.updatedAt).toLocaleString("zh-CN")}
        </div>
      )}
    </div>
  );
}
