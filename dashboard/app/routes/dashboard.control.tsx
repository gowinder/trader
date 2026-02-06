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
import { Play, Pause, RefreshCw, Settings, Zap } from "lucide-react";

interface TradingConfig {
  enabled: boolean;
  decisionInterval: number;
  lastTrigger?: string;
}

const INTERVAL_OPTIONS = [
  { value: "1", label: "1 分钟" },
  { value: "5", label: "5 分钟" },
  { value: "10", label: "10 分钟" },
  { value: "15", label: "15 分钟" },
  { value: "30", label: "30 分钟" },
  { value: "60", label: "1 小时" },
];

export default function ControlPage() {
  const [config, setConfig] = useState<TradingConfig>({
    enabled: true,
    decisionInterval: 1,
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [triggering, setTriggering] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  useEffect(() => {
    fetch("/api/trading-config")
      .then((res) => res.json())
      .then((data) => {
        if (data.decisionInterval) {
          setConfig(data);
        }
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const saveConfig = async () => {
    setSaving(true);
    setMessage(null);
    try {
      const res = await fetch("/api/trading-config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      });
      if (res.ok) {
        setMessage({ type: "success", text: "配置已保存" });
      } else {
        setMessage({ type: "error", text: "保存失败" });
      }
    } catch {
      setMessage({ type: "error", text: "保存失败" });
    } finally {
      setSaving(false);
    }
  };

  const triggerAnalysis = async () => {
    setTriggering(true);
    setMessage(null);
    try {
      const res = await fetch("/api/trading-trigger", {
        method: "POST",
      });
      const data = await res.json();
      if (res.ok) {
        setMessage({ type: "success", text: data.message || "已触发交易分析" });
        setConfig((prev) => ({ ...prev, lastTrigger: new Date().toISOString() }));
      } else {
        setMessage({ type: "error", text: data.error || "触发失败" });
      }
    } catch {
      setMessage({ type: "error", text: "触发失败" });
    } finally {
      setTriggering(false);
    }
  };

  const toggleEnabled = async () => {
    const newEnabled = !config.enabled;
    setConfig((prev) => ({ ...prev, enabled: newEnabled }));
    try {
      await fetch("/api/trading-config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...config, enabled: newEnabled }),
      });
      setMessage({
        type: "success",
        text: newEnabled ? "交易已启用" : "交易已暂停",
      });
    } catch {
      setMessage({ type: "error", text: "操作失败" });
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
          交易控制
        </h1>
      </div>

      {message && (
        <div
          className={`p-3 rounded-md ${
            message.type === "success"
              ? "bg-green-500/10 text-green-500 border border-green-500/20"
              : "bg-red-500/10 text-red-500 border border-red-500/20"
          }`}
        >
          {message.text}
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center justify-between">
            <span className="flex items-center gap-2">
              {config.enabled ? (
                <span className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
              ) : (
                <span className="h-2 w-2 rounded-full bg-yellow-500" />
              )}
              交易状态
            </span>
            <Button
              variant={config.enabled ? "destructive" : "default"}
              size="sm"
              onClick={toggleEnabled}
            >
              {config.enabled ? (
                <>
                  <Pause className="mr-2 h-4 w-4" />
                  暂停交易
                </>
              ) : (
                <>
                  <Play className="mr-2 h-4 w-4" />
                  启用交易
                </>
              )}
            </Button>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-sm text-muted-foreground">
            {config.enabled ? "交易系统正在运行" : "交易系统已暂停"}
            {config.lastTrigger && (
              <span className="ml-2">
                · 上次触发: {new Date(config.lastTrigger).toLocaleString("zh-CN")}
              </span>
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <RefreshCw className="h-4 w-4" />
            决策触发频率
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <Label>自动触发间隔</Label>
              <Select
                value={String(config.decisionInterval)}
                onValueChange={(v) =>
                  setConfig({ ...config, decisionInterval: parseInt(v) })
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {INTERVAL_OPTIONS.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground mt-1">
                系统将每隔此时间自动进行一次市场分析和交易决策
              </p>
            </div>
          </div>
          <Button onClick={saveConfig} disabled={saving}>
            {saving ? "保存中..." : "保存配置"}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Zap className="h-4 w-4" />
            手动触发
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            立即执行一次市场分析和交易决策，用于测试或紧急情况。
          </p>
          <Button
            onClick={triggerAnalysis}
            disabled={triggering}
            variant="outline"
            className="w-full md:w-auto"
          >
            {triggering ? (
              <>
                <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                分析中...
              </>
            ) : (
              <>
                <Zap className="mr-2 h-4 w-4" />
                立即触发分析
              </>
            )}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
