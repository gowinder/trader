import { useState, useEffect, useCallback } from "react";
import { Plus, Trash2, ChevronUp, ChevronDown, Save } from "lucide-react";

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

interface ProviderInfo {
  id: number;
  name: string;
  displayName: string;
  models: string[];
  isEnabled: boolean;
}

interface LlmRoutingItem {
  providerId: number;
  model: string;
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

export default function AdvisorySettingsPage() {
  const [triggerConfig, setTriggerConfig] = useState<TriggerConfig>(DEFAULT_TRIGGER);
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [advisoryRouting, setAdvisoryRouting] = useState<LlmRoutingItem[]>([]);
  const [autoExecute, setAutoExecute] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savingRouting, setSavingRouting] = useState(false);
  const [toast, setToast] = useState<{ type: "success" | "error"; message: string } | null>(null);

  const showToast = useCallback((type: "success" | "error", message: string) => {
    setToast({ type, message });
  }, []);

  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(null), 3000);
      return () => clearTimeout(timer);
    }
  }, [toast]);

  useEffect(() => {
    Promise.all([
      fetch("/api/advisory-settings").then((r) => r.json()),
      fetch("/api/llm-config/providers").then((r) => r.json()),
      fetch("/api/llm-config/routing?scope=advisory").then((r) => r.json()),
    ])
      .then(([settingsData, provData, routingData]) => {
        if (settingsData.triggerConfig) setTriggerConfig(settingsData.triggerConfig);
        if (settingsData.autoExecute !== undefined) setAutoExecute(settingsData.autoExecute);
        if (provData.providers) {
          setProviders(
            provData.providers.map((p: ProviderInfo) => ({
              id: p.id,
              name: p.name,
              displayName: p.displayName,
              models: p.models,
              isEnabled: p.isEnabled,
            }))
          );
        }
        if (routingData.routing?.length > 0) {
          setAdvisoryRouting(
            routingData.routing.map((r: { providerId: number; model: string }) => ({
              providerId: r.providerId,
              model: r.model,
            }))
          );
        }
      })
      .catch((err) => console.error("Failed to load settings:", err))
      .finally(() => setLoading(false));
  }, []);

  const enabledProviders = providers.filter((p) => p.isEnabled);

  const handleSaveTrigger = async () => {
    setSaving(true);
    try {
      const res = await fetch("/api/advisory-settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ triggerConfig }),
      });
      if (res.ok) showToast("success", "触发器配置已保存");
      else showToast("error", "保存失败");
    } catch {
      showToast("error", "网络错误");
    } finally {
      setSaving(false);
    }
  };

  const handleSaveRouting = async () => {
    setSavingRouting(true);
    try {
      const res = await fetch("/api/llm-config/routing", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scope: "advisory",
          items: advisoryRouting.map((r, i) => ({
            providerId: r.providerId,
            model: r.model,
            priority: i + 1,
          })),
        }),
      });
      if (res.ok) showToast("success", "Advisory LLM 调度已保存");
      else showToast("error", "保存失败");
    } catch {
      showToast("error", "网络错误");
    } finally {
      setSavingRouting(false);
    }
  };

  const addRoutingItem = () => {
    if (enabledProviders.length === 0) return;
    const first = enabledProviders[0];
    setAdvisoryRouting((prev) => [
      ...prev,
      { providerId: first.id, model: first.models[0] || "" },
    ]);
  };

  const removeRoutingItem = (index: number) => {
    setAdvisoryRouting((prev) => prev.filter((_, i) => i !== index));
  };

  const moveRoutingItem = (index: number, dir: -1 | 1) => {
    setAdvisoryRouting((prev) => {
      const arr = [...prev];
      const target = index + dir;
      if (target < 0 || target >= arr.length) return arr;
      [arr[index], arr[target]] = [arr[target], arr[index]];
      return arr;
    });
  };

  const updateRoutingItem = (index: number, patch: Partial<LlmRoutingItem>) => {
    setAdvisoryRouting((prev) =>
      prev.map((r, i) => (i === index ? { ...r, ...patch } : r))
    );
  };

  if (loading) {
    return (
      <div className="p-6 flex items-center justify-center">
        <div className="animate-spin h-8 w-8 border-2 border-primary border-t-transparent rounded-full" />
      </div>
    );
  }

  const inputCls =
    "w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary";
  const selectCls =
    "rounded-md border border-border bg-background px-2 py-1 text-sm flex-1 min-w-0";

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

      {/* Auto Execute */}
      <div className="rounded-lg border border-border bg-card p-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold">自动执行建议</h2>
            <p className="text-sm text-muted-foreground mt-1">
              开启后，AI 生成的交易建议将自动执行，无需手动确认。请谨慎使用。
            </p>
          </div>
          <button
            type="button"
            onClick={async () => {
              const next = !autoExecute;
              setAutoExecute(next);
              try {
                const res = await fetch("/api/advisory-settings", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ autoExecute: next }),
                });
                if (res.ok) {
                  showToast("success", next ? "自动执行已开启" : "自动执行已关闭");
                } else {
                  setAutoExecute(!next);
                  showToast("error", "保存失败");
                }
              } catch {
                setAutoExecute(!next);
                showToast("error", "保存失败");
              }
            }}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
              autoExecute ? "bg-primary" : "bg-muted"
            }`}
          >
            <span
              className={`inline-block h-4 w-4 rounded-full bg-white transition-transform ${
                autoExecute ? "translate-x-6" : "translate-x-1"
              }`}
            />
          </button>
        </div>
      </div>

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
                className={inputCls}
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
                className={inputCls}
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
                className={inputCls + " disabled:opacity-50"}
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
                className={inputCls + " disabled:opacity-50"}
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
                className={inputCls + " disabled:opacity-50"}
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

        <div className="flex justify-end mt-4">
          <button
            onClick={handleSaveTrigger}
            disabled={saving}
            className="inline-flex items-center gap-1 px-4 py-1.5 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-50"
          >
            <Save className="h-3.5 w-3.5" /> {saving ? "保存中..." : "保存触发器"}
          </button>
        </div>
      </div>

      {/* Advisory LLM Routing */}
      <div className="rounded-lg border border-border bg-card p-6">
        <h2 className="text-lg font-semibold mb-2">Advisory LLM 调度</h2>
        <p className="text-xs text-muted-foreground mb-4">
          按优先级排列，排在前面的优先调用，失败后自动回退到下一个
        </p>

        <div className="space-y-2 mb-4">
          {advisoryRouting.length === 0 && (
            <p className="text-sm text-muted-foreground py-4 text-center">暂无调度项，请点击下方添加</p>
          )}
          {advisoryRouting.map((item, idx) => {
            const prov = providers.find((p) => p.id === item.providerId);
            return (
              <div
                key={`adv-${idx}`}
                className="flex items-center gap-2 rounded-md border border-border p-2"
              >
                <span className="text-xs text-muted-foreground w-6 text-center">{idx + 1}</span>

                <select
                  value={item.providerId}
                  onChange={(e) => {
                    const newId = Number(e.target.value);
                    const np = providers.find((p) => p.id === newId);
                    updateRoutingItem(idx, {
                      providerId: newId,
                      model: np?.models[0] || "",
                    });
                  }}
                  className={selectCls}
                >
                  {enabledProviders.map((ep) => (
                    <option key={ep.id} value={ep.id}>
                      {ep.displayName}
                    </option>
                  ))}
                </select>

                <select
                  value={item.model}
                  onChange={(e) => updateRoutingItem(idx, { model: e.target.value })}
                  className={selectCls}
                >
                  {(prov?.models || []).map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>

                <button
                  type="button"
                  onClick={() => moveRoutingItem(idx, -1)}
                  disabled={idx === 0}
                  className="p-1 text-muted-foreground hover:text-foreground disabled:opacity-30"
                >
                  <ChevronUp className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  onClick={() => moveRoutingItem(idx, 1)}
                  disabled={idx === advisoryRouting.length - 1}
                  className="p-1 text-muted-foreground hover:text-foreground disabled:opacity-30"
                >
                  <ChevronDown className="h-4 w-4" />
                </button>

                <button
                  type="button"
                  onClick={() => removeRoutingItem(idx)}
                  className="p-1 text-red-400 hover:text-red-300"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            );
          })}
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={addRoutingItem}
            disabled={enabledProviders.length === 0}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-md border border-border text-sm hover:bg-accent disabled:opacity-50"
          >
            <Plus className="h-3.5 w-3.5" /> 添加
          </button>
          <button
            type="button"
            onClick={handleSaveRouting}
            disabled={savingRouting}
            className="inline-flex items-center gap-1 px-4 py-1.5 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-50"
          >
            <Save className="h-3.5 w-3.5" /> {savingRouting ? "保存中..." : "保存调度"}
          </button>
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
    </div>
  );
}
