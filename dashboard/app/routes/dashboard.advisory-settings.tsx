import { useState, useEffect } from "react";

interface TriggerConfig {
  interval_minutes: number;
  price_volatility_enabled: boolean;
  price_volatility_threshold: number;
  consecutive_loss_enabled: boolean;
  consecutive_loss_threshold: number;
  unrealized_pnl_enabled: boolean;
  unrealized_pnl_threshold: number;
  sentiment_shift_enabled: boolean;
  cooldown_minutes: number;
}

interface LlmConfig {
  provider: string;
  model: string;
  base_url: string;
}

const DEFAULT_TRIGGER: TriggerConfig = {
  interval_minutes: 60,
  price_volatility_enabled: true,
  price_volatility_threshold: 5.0,
  consecutive_loss_enabled: true,
  consecutive_loss_threshold: 3,
  unrealized_pnl_enabled: true,
  unrealized_pnl_threshold: -5.0,
  sentiment_shift_enabled: true,
  cooldown_minutes: 30,
};

const DEFAULT_LLM: LlmConfig = {
  provider: "openrouter",
  model: "deepseek/deepseek-chat",
  base_url: "",
};

export default function AdvisorySettingsPage() {
  const [triggerConfig, setTriggerConfig] = useState<TriggerConfig>(DEFAULT_TRIGGER);
  const [llmConfig, setLlmConfig] = useState<LlmConfig>(DEFAULT_LLM);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<{ type: "success" | "error"; message: string } | null>(null);

  useEffect(() => {
    fetch("/api/advisory-settings")
      .then((res) => res.json())
      .then((data) => {
        if (data.triggerConfig) setTriggerConfig(data.triggerConfig);
        if (data.llmConfig) setLlmConfig(data.llmConfig);
      })
      .catch((err) => console.error("Failed to load settings:", err))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(null), 3000);
      return () => clearTimeout(timer);
    }
  }, [toast]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await fetch("/api/advisory-settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ triggerConfig, llmConfig }),
      });
      if (res.ok) {
        setToast({ type: "success", message: "设置已保存" });
      } else {
        const data = await res.json();
        setToast({ type: "error", message: data.error || "保存失败" });
      }
    } catch {
      setToast({ type: "error", message: "网络错误，保存失败" });
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="p-6 flex items-center justify-center">
        <div className="animate-spin h-8 w-8 border-2 border-primary border-t-transparent rounded-full" />
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold">建议设置</h1>

      {/* Toast */}
      {toast && (
        <div
          className={`fixed top-4 right-4 z-50 px-4 py-3 rounded-lg shadow-lg text-sm font-medium ${
            toast.type === "success"
              ? "bg-green-500/20 text-green-400 border border-green-500/30"
              : "bg-red-500/20 text-red-400 border border-red-500/30"
          }`}
        >
          {toast.message}
        </div>
      )}

      {/* Trigger Configuration */}
      <div className="rounded-lg border border-border bg-card p-6">
        <h2 className="text-lg font-semibold mb-4">触发器配置</h2>
        <div className="space-y-6">
          {/* Scheduled Interval */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-muted-foreground mb-1">定时分析间隔 (分钟)</label>
              <input
                type="number"
                min={5}
                max={240}
                value={triggerConfig.interval_minutes}
                onChange={(e) =>
                  setTriggerConfig({ ...triggerConfig, interval_minutes: Number(e.target.value) })
                }
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              />
              <p className="text-xs text-muted-foreground mt-1">范围: 5 - 240 分钟</p>
            </div>
            <div>
              <label className="block text-sm text-muted-foreground mb-1">全局冷却时间 (分钟)</label>
              <input
                type="number"
                min={0}
                value={triggerConfig.cooldown_minutes}
                onChange={(e) =>
                  setTriggerConfig({ ...triggerConfig, cooldown_minutes: Number(e.target.value) })
                }
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              />
              <p className="text-xs text-muted-foreground mt-1">同一交易对建议的最小间隔</p>
            </div>
          </div>

          {/* Trigger Types */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Price Volatility */}
            <div className="rounded-md border border-border p-4">
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm font-medium">价格波动触发</span>
                <button
                  type="button"
                  onClick={() =>
                    setTriggerConfig({
                      ...triggerConfig,
                      price_volatility_enabled: !triggerConfig.price_volatility_enabled,
                    })
                  }
                  className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
                    triggerConfig.price_volatility_enabled ? "bg-primary" : "bg-muted"
                  }`}
                >
                  <span
                    className={`inline-block h-3.5 w-3.5 rounded-full bg-white transition-transform ${
                      triggerConfig.price_volatility_enabled ? "translate-x-4.5" : "translate-x-0.5"
                    }`}
                  />
                </button>
              </div>
              <label className="block text-xs text-muted-foreground mb-1">阈值 (%)</label>
              <input
                type="number"
                step={0.1}
                min={0}
                value={triggerConfig.price_volatility_threshold}
                onChange={(e) =>
                  setTriggerConfig({
                    ...triggerConfig,
                    price_volatility_threshold: Number(e.target.value),
                  })
                }
                disabled={!triggerConfig.price_volatility_enabled}
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50"
              />
            </div>

            {/* Consecutive Loss */}
            <div className="rounded-md border border-border p-4">
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm font-medium">连续亏损触发</span>
                <button
                  type="button"
                  onClick={() =>
                    setTriggerConfig({
                      ...triggerConfig,
                      consecutive_loss_enabled: !triggerConfig.consecutive_loss_enabled,
                    })
                  }
                  className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
                    triggerConfig.consecutive_loss_enabled ? "bg-primary" : "bg-muted"
                  }`}
                >
                  <span
                    className={`inline-block h-3.5 w-3.5 rounded-full bg-white transition-transform ${
                      triggerConfig.consecutive_loss_enabled ? "translate-x-4.5" : "translate-x-0.5"
                    }`}
                  />
                </button>
              </div>
              <label className="block text-xs text-muted-foreground mb-1">连续亏损次数</label>
              <input
                type="number"
                min={1}
                step={1}
                value={triggerConfig.consecutive_loss_threshold}
                onChange={(e) =>
                  setTriggerConfig({
                    ...triggerConfig,
                    consecutive_loss_threshold: Number(e.target.value),
                  })
                }
                disabled={!triggerConfig.consecutive_loss_enabled}
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50"
              />
            </div>

            {/* Unrealized PnL */}
            <div className="rounded-md border border-border p-4">
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm font-medium">未实现盈亏触发</span>
                <button
                  type="button"
                  onClick={() =>
                    setTriggerConfig({
                      ...triggerConfig,
                      unrealized_pnl_enabled: !triggerConfig.unrealized_pnl_enabled,
                    })
                  }
                  className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
                    triggerConfig.unrealized_pnl_enabled ? "bg-primary" : "bg-muted"
                  }`}
                >
                  <span
                    className={`inline-block h-3.5 w-3.5 rounded-full bg-white transition-transform ${
                      triggerConfig.unrealized_pnl_enabled ? "translate-x-4.5" : "translate-x-0.5"
                    }`}
                  />
                </button>
              </div>
              <label className="block text-xs text-muted-foreground mb-1">阈值 (%)</label>
              <input
                type="number"
                step={0.5}
                value={triggerConfig.unrealized_pnl_threshold}
                onChange={(e) =>
                  setTriggerConfig({
                    ...triggerConfig,
                    unrealized_pnl_threshold: Number(e.target.value),
                  })
                }
                disabled={!triggerConfig.unrealized_pnl_enabled}
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50"
              />
              <p className="text-xs text-muted-foreground mt-1">负值表示亏损触发</p>
            </div>

            {/* Sentiment Shift */}
            <div className="rounded-md border border-border p-4">
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm font-medium">情绪突变触发</span>
                <button
                  type="button"
                  onClick={() =>
                    setTriggerConfig({
                      ...triggerConfig,
                      sentiment_shift_enabled: !triggerConfig.sentiment_shift_enabled,
                    })
                  }
                  className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
                    triggerConfig.sentiment_shift_enabled ? "bg-primary" : "bg-muted"
                  }`}
                >
                  <span
                    className={`inline-block h-3.5 w-3.5 rounded-full bg-white transition-transform ${
                      triggerConfig.sentiment_shift_enabled ? "translate-x-4.5" : "translate-x-0.5"
                    }`}
                  />
                </button>
              </div>
              <p className="text-xs text-muted-foreground">基于新闻情绪的剧烈变化自动触发分析</p>
            </div>
          </div>
        </div>
      </div>

      {/* LLM Configuration */}
      <div className="rounded-lg border border-border bg-card p-6">
        <h2 className="text-lg font-semibold mb-4">LLM 配置</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="block text-sm text-muted-foreground mb-1">Provider</label>
            <input
              type="text"
              value={llmConfig.provider}
              onChange={(e) => setLlmConfig({ ...llmConfig, provider: e.target.value })}
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              placeholder="openrouter"
            />
          </div>
          <div>
            <label className="block text-sm text-muted-foreground mb-1">Model</label>
            <input
              type="text"
              value={llmConfig.model}
              onChange={(e) => setLlmConfig({ ...llmConfig, model: e.target.value })}
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              placeholder="deepseek/deepseek-chat"
            />
          </div>
          <div>
            <label className="block text-sm text-muted-foreground mb-1">Base URL (可选)</label>
            <input
              type="text"
              value={llmConfig.base_url}
              onChange={(e) => setLlmConfig({ ...llmConfig, base_url: e.target.value })}
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              placeholder="留空使用默认"
            />
          </div>
        </div>
      </div>

      {/* Telegram Status */}
      <div className="rounded-lg border border-border bg-card p-6">
        <h2 className="text-lg font-semibold mb-4">Telegram 通知</h2>
        <div className="flex items-center gap-3">
          <div className="h-3 w-3 rounded-full bg-yellow-500" />
          <span className="text-sm text-muted-foreground">
            Telegram 配置通过环境变量 (.env) 管理，请在服务端设置 TELEGRAM_BOT_TOKEN 和 TELEGRAM_CHAT_ID
          </span>
        </div>
      </div>

      {/* Save Button */}
      <div className="flex justify-end">
        <button
          onClick={handleSave}
          disabled={saving}
          className="px-6 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
        >
          {saving ? "保存中..." : "保存设置"}
        </button>
      </div>
    </div>
  );
}
