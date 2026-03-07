import { useState, useCallback } from "react";
import type { Route } from "./+types/dashboard.strategy";

export async function loader(_args: Route.LoaderArgs) {
  try {
    const { loader: presetsLoader } = await import("./api.strategy-presets");
    const res = await (presetsLoader as any)();
    if (res instanceof Response && res.ok) {
      return await res.json();
    }
    return { presets: [], activePresetId: null, activatedAt: null, isLocked: false };
  } catch {
    return { presets: [], activePresetId: null, activatedAt: null, isLocked: false };
  }
}

interface PresetConfig {
  enabled_strategies: string[];
  strategy_weights: Record<string, number>;
  ai_weight: number;
  quant_weight: number;
  sentiment_weight: number;
  timeframes: string[];
  min_trade_interval_seconds: number;
  stop_loss_atr_multiplier: number;
  take_profit_atr_multiplier: number;
  max_position_pct: number;
  enable_pyramid: boolean;
  max_pyramid_times: number;
  enable_sentiment: boolean;
  min_profit_threshold: number;
  use_market_order_only: boolean;
}

interface Preset {
  id: number;
  name: string;
  displayName: string;
  description: string;
  category: string;
  riskLevel: string;
  configJson: PresetConfig;
  isSystem: boolean;
  isModified: boolean;
  sourcePresetId: number | null;
  stats: {
    totalTrades: number;
    totalPnl: number;
    winRate: number;
  };
}

const RISK_COLORS: Record<string, { bg: string; text: string; label: string }> = {
  lowest: { bg: "bg-green-500/20", text: "text-green-400", label: "最低" },
  low: { bg: "bg-emerald-500/20", text: "text-emerald-400", label: "低" },
  medium_low: { bg: "bg-yellow-500/20", text: "text-yellow-400", label: "中低" },
  medium: { bg: "bg-orange-500/20", text: "text-orange-400", label: "中" },
  medium_high: { bg: "bg-red-500/20", text: "text-red-400", label: "中高" },
};

const CATEGORY_LABELS: Record<string, string> = {
  trend: "趋势",
  range: "震荡",
  breakout: "突破",
  scalping: "剥头皮",
  balanced: "均衡",
};

const ALL_STRATEGIES = ["trend_following", "mean_reversion", "breakout"];
const STRATEGY_LABELS: Record<string, string> = {
  trend_following: "趋势跟踪",
  mean_reversion: "均值回归",
  breakout: "突破",
};

const ALL_TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"];

function formatInterval(seconds: number): string {
  if (seconds >= 3600) return `${seconds / 3600}小时`;
  return `${seconds / 60}分钟`;
}

function RiskBadge({ level }: { level: string }) {
  const risk = RISK_COLORS[level] || RISK_COLORS.medium;
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${risk.bg} ${risk.text}`}>
      {risk.label}
    </span>
  );
}

// Validation
function validateConfig(config: PresetConfig): string[] {
  const errors: string[] = [];
  if (!config.enabled_strategies || config.enabled_strategies.length === 0) {
    errors.push("至少选择一个策略");
  }
  if (config.ai_weight < 0 || config.ai_weight > 1) errors.push("AI权重需在0-1之间");
  if (config.quant_weight < 0 || config.quant_weight > 1) errors.push("量化权重需在0-1之间");
  if (config.min_trade_interval_seconds < 60) errors.push("交易间隔至少60秒");
  if (config.stop_loss_atr_multiplier < 0.5) errors.push("止损ATR倍数至少0.5");
  if (config.take_profit_atr_multiplier < 0.5) errors.push("止盈ATR倍数至少0.5");
  if (config.max_position_pct < 1 || config.max_position_pct > 100) errors.push("最大仓位需在1-100之间");
  if (config.timeframes.length === 0) errors.push("至少选择一个时间周期");
  const totalWeight = Object.values(config.strategy_weights).reduce((a, b) => a + b, 0);
  if (config.enabled_strategies.length > 0 && totalWeight <= 0) errors.push("策略权重之和需大于0");
  return errors;
}

function deepEqual(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

// Number input component
function NumInput({
  label, value, onChange, min, max, step = 1, suffix,
}: {
  label: string; value: number; onChange: (v: number) => void;
  min?: number; max?: number; step?: number; suffix?: string;
}) {
  return (
    <div>
      <label className="text-xs text-muted-foreground block mb-1">{label}</label>
      <div className="flex items-center gap-1">
        <input
          type="number"
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          min={min} max={max} step={step}
          className="w-full rounded border border-border bg-background px-2 py-1 text-sm"
        />
        {suffix && <span className="text-xs text-muted-foreground whitespace-nowrap">{suffix}</span>}
      </div>
    </div>
  );
}

// Slider + number input for weights (0-1)
function WeightInput({
  label, value, onChange,
}: {
  label: string; value: number; onChange: (v: number) => void;
}) {
  return (
    <div>
      <label className="text-xs text-muted-foreground block mb-1">{label}</label>
      <div className="flex items-center gap-2">
        <input
          type="range" min={0} max={1} step={0.05} value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          className="flex-1 h-1.5 rounded-full appearance-none bg-muted accent-primary"
        />
        <span className="text-sm font-medium w-12 text-right">{Math.round(value * 100)}%</span>
      </div>
    </div>
  );
}

// Toggle switch
function Toggle({
  label, checked, onChange,
}: {
  label: string; checked: boolean; onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex items-center justify-between cursor-pointer">
      <span className="text-xs text-muted-foreground">{label}</span>
      <button
        type="button"
        onClick={() => onChange(!checked)}
        className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
          checked ? "bg-primary" : "bg-muted"
        }`}
      >
        <span className={`inline-block h-3.5 w-3.5 rounded-full bg-white transition-transform ${
          checked ? "translate-x-4.5" : "translate-x-0.5"
        }`} />
      </button>
    </label>
  );
}

export default function StrategyPage({ loaderData }: Route.ComponentProps) {
  const { presets: initialPresets, activePresetId, activatedAt, isLocked: initialLocked } = loaderData as {
    presets: Preset[];
    activePresetId: number | null;
    activatedAt: string | null;
    isLocked: boolean;
  };
  const [presets, setPresets] = useState<Preset[]>(initialPresets);
  const [confirmPreset, setConfirmPreset] = useState<Preset | null>(null);
  const [activating, setActivating] = useState(false);
  const [currentActiveId, setCurrentActiveId] = useState(activePresetId);
  const [locked, setLocked] = useState(initialLocked);
  const [lockWithActivate, setLockWithActivate] = useState(false);
  const [togglingLock, setTogglingLock] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [suggesting, setSuggesting] = useState(false);
  const [suggestion, setSuggestion] = useState<{
    recommended_preset: string;
    recommended_display_name: string;
    reason: string;
    market_state: string;
    current_strategy_analysis: string;
    current_strategy_score: number;
  } | null>(null);

  // Edit state
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editConfig, setEditConfig] = useState<PresetConfig | null>(null);
  const [originalConfig, setOriginalConfig] = useState<PresetConfig | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveAsName, setSaveAsName] = useState("");
  const [showSaveAsDialog, setShowSaveAsDialog] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState<number | null>(null);
  const [showOverwriteConfirm, setShowOverwriteConfirm] = useState(false);

  const activePreset = presets.find((p) => p.id === currentActiveId);
  const isDirty = editConfig && originalConfig && !deepEqual(editConfig, originalConfig);
  const validationErrors = editConfig ? validateConfig(editConfig) : [];
  const canSave = isDirty && validationErrors.length === 0;

  const startEdit = useCallback((preset: Preset) => {
    setEditingId(preset.id);
    const config = { ...preset.configJson };
    // Ensure all fields have defaults
    config.sentiment_weight = config.sentiment_weight ?? 0;
    config.max_pyramid_times = config.max_pyramid_times ?? 0;
    config.use_market_order_only = config.use_market_order_only ?? false;
    setEditConfig({ ...config });
    setOriginalConfig({ ...config });
    setShowAdvanced(false);
  }, []);

  const cancelEdit = useCallback(() => {
    setEditingId(null);
    setEditConfig(null);
    setOriginalConfig(null);
    setShowAdvanced(false);
  }, []);

  const updateConfig = useCallback(<K extends keyof PresetConfig>(key: K, value: PresetConfig[K]) => {
    setEditConfig((prev) => prev ? { ...prev, [key]: value } : prev);
  }, []);

  // Reload presets from API
  const reloadPresets = useCallback(async () => {
    try {
      const res = await fetch("/api/strategy-presets");
      if (res.ok) {
        const data = await res.json();
        setPresets(data.presets);
      }
    } catch {
      // ignore
    }
  }, []);

  // Overwrite save
  const handleSave = useCallback(async () => {
    if (!editingId || !editConfig) return;
    const preset = presets.find((p) => p.id === editingId);
    if (!preset) return;
    // System preset: confirm first
    if (preset.isSystem && !showOverwriteConfirm) {
      setShowOverwriteConfirm(true);
      return;
    }
    setShowOverwriteConfirm(false);
    setSaving(true);
    try {
      const res = await fetch("/api/strategy-presets/update", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ presetId: editingId, config: editConfig }),
      });
      if (res.ok) {
        cancelEdit();
        await reloadPresets();
      } else {
        const data = await res.json().catch(() => ({}));
        setError(data.error || "保存失败");
      }
    } catch {
      setError("网络错误");
    } finally {
      setSaving(false);
    }
  }, [editingId, editConfig, presets, showOverwriteConfirm, cancelEdit, reloadPresets]);

  // Save as new preset
  const handleSaveAs = useCallback(async () => {
    if (!editingId || !editConfig || !saveAsName.trim()) return;
    setSaving(true);
    try {
      const res = await fetch("/api/strategy-presets/save-as", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sourcePresetId: editingId,
          config: editConfig,
          displayName: saveAsName.trim(),
        }),
      });
      if (res.ok) {
        setShowSaveAsDialog(false);
        cancelEdit();
        await reloadPresets();
      } else {
        const data = await res.json().catch(() => ({}));
        setError(data.error || "另存失败");
      }
    } catch {
      setError("网络错误");
    } finally {
      setSaving(false);
    }
  }, [editingId, editConfig, saveAsName, cancelEdit, reloadPresets]);

  // Open save-as dialog with auto-generated name
  const openSaveAsDialog = useCallback(() => {
    const preset = presets.find((p) => p.id === editingId);
    if (!preset) return;
    const now = new Date();
    const dateSuffix = `${String(now.getMonth() + 1).padStart(2, "0")}${String(now.getDate()).padStart(2, "0")}`;
    setSaveAsName(`${preset.displayName}-${dateSuffix}`);
    setShowSaveAsDialog(true);
  }, [editingId, presets]);

  // Reset preset
  const handleReset = useCallback(async (presetId: number) => {
    setSaving(true);
    try {
      const res = await fetch("/api/strategy-presets/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ presetId }),
      });
      if (res.ok) {
        cancelEdit();
        await reloadPresets();
      } else {
        const data = await res.json().catch(() => ({}));
        setError(data.error || "重置失败");
      }
    } catch {
      setError("网络错误");
    } finally {
      setSaving(false);
    }
  }, [cancelEdit, reloadPresets]);

  // Delete preset
  const handleDelete = useCallback(async (presetId: number) => {
    setSaving(true);
    try {
      const res = await fetch("/api/strategy-presets/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ presetId }),
      });
      if (res.ok) {
        setShowDeleteConfirm(null);
        cancelEdit();
        await reloadPresets();
      } else {
        const data = await res.json().catch(() => ({}));
        setError(data.error || "删除失败");
      }
    } catch {
      setError("网络错误");
    } finally {
      setSaving(false);
    }
  }, [cancelEdit, reloadPresets]);

  const handleToggleLock = async () => {
    setTogglingLock(true);
    setError(null);
    try {
      const res = await fetch("/api/strategy-presets/lock", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ isLocked: !locked }),
      });
      if (res.ok) {
        setLocked(!locked);
      } else {
        const data = await res.json().catch(() => ({}));
        setError(data.error || "操作失败");
      }
    } catch {
      setError("网络错误");
    } finally {
      setTogglingLock(false);
    }
  };

  const handleSuggest = async () => {
    setSuggesting(true);
    setError(null);
    setSuggestion(null);
    try {
      const triggerRes = await fetch("/api/strategy-presets/suggest", { method: "POST" });
      if (!triggerRes.ok) {
        const data = await triggerRes.json().catch(() => ({}));
        setError(data.error || "触发策略建议失败");
        setSuggesting(false);
        return;
      }
      const { taskId } = await triggerRes.json();
      for (let i = 0; i < 60; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        const pollRes = await fetch(`/api/strategy-presets/suggest?taskId=${taskId}`);
        if (!pollRes.ok) continue;
        const result = await pollRes.json();
        if (result.status === "completed") { setSuggestion(result); setSuggesting(false); return; }
        if (result.status === "error") { setError(result.error || "策略建议生成失败"); setSuggesting(false); return; }
      }
      setError("策略建议超时，请重试");
    } catch {
      setError("网络错误");
    } finally {
      setSuggesting(false);
    }
  };

  const handleActivatePreset = (presetName: string) => {
    const target = presets.find((p) => p.name === presetName);
    if (target) { setConfirmPreset(target); setLockWithActivate(false); }
  };

  const handleActivate = async (preset: Preset) => {
    setActivating(true);
    setError(null);
    try {
      const res = await fetch("/api/strategy-presets/activate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ presetId: preset.id, isLocked: lockWithActivate }),
      });
      if (res.ok) {
        setCurrentActiveId(preset.id);
        setLocked(lockWithActivate);
        setConfirmPreset(null);
        setLockWithActivate(false);
      } else if (res.status === 423) {
        setError("当前策略已锁定，请先解锁再切换");
        setConfirmPreset(null);
      } else {
        const data = await res.json().catch(() => ({}));
        setError(data.error || "激活失败");
      }
    } catch {
      setError("网络错误");
    } finally {
      setActivating(false);
    }
  };

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold">策略选择</h1>

      {error && (
        <div className="rounded-lg border border-red-500/50 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          {error}
          <button onClick={() => setError(null)} className="ml-2 underline text-xs">关闭</button>
        </div>
      )}

      {/* Current active strategy */}
      {activePreset && (
        <div className={`rounded-lg border p-6 ${locked ? "border-yellow-500/50 bg-yellow-500/5" : "border-border bg-card"}`}>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <div className="h-3 w-3 rounded-full bg-green-500 animate-pulse" />
              <h2 className="text-lg font-semibold">当前策略: {activePreset.displayName}</h2>
              <RiskBadge level={activePreset.riskLevel} />
              {locked && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-yellow-500/20 text-yellow-400">
                  <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M5 9V7a5 5 0 0110 0v2a2 2 0 012 2v5a2 2 0 01-2 2H5a2 2 0 01-2-2v-5a2 2 0 012-2zm8-2v2H7V7a3 3 0 016 0z" clipRule="evenodd" /></svg>
                  已锁定
                </span>
              )}
            </div>
            <div className="flex items-center gap-3">
              {activatedAt && (
                <span className="text-sm text-muted-foreground">
                  运行自 {new Date(activatedAt).toLocaleString("zh-CN")}
                </span>
              )}
              <button
                type="button"
                onClick={handleToggleLock}
                disabled={togglingLock}
                className={`relative inline-flex h-7 w-12 items-center rounded-full transition-colors disabled:opacity-50 ${
                  locked ? "bg-yellow-500" : "bg-muted"
                }`}
                title={locked ? "点击解锁，允许自动切换策略" : "点击锁定，阻止自动切换策略"}
              >
                <span className={`inline-flex h-5 w-5 items-center justify-center rounded-full bg-white transition-transform ${
                  locked ? "translate-x-6" : "translate-x-1"
                }`}>
                  {locked ? (
                    <svg className="w-3 h-3 text-yellow-600" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M5 9V7a5 5 0 0110 0v2a2 2 0 012 2v5a2 2 0 01-2 2H5a2 2 0 01-2-2v-5a2 2 0 012-2zm8-2v2H7V7a3 3 0 016 0z" clipRule="evenodd" /></svg>
                  ) : (
                    <svg className="w-3 h-3 text-gray-400" fill="currentColor" viewBox="0 0 20 20"><path d="M10 2a5 5 0 00-5 5v2a2 2 0 00-2 2v5a2 2 0 002 2h10a2 2 0 002-2v-5a2 2 0 00-2-2H7V7a3 3 0 015.905-.75 1 1 0 001.937-.5A5.002 5.002 0 0010 2z" /></svg>
                  )}
                </span>
              </button>
            </div>
          </div>
          {locked && (
            <p className="text-xs text-yellow-400/80 mb-4">
              策略已锁定，LLM 和事件驱动将无法自动切换策略。手动解锁后恢复。
            </p>
          )}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <div>
              <span className="text-muted-foreground">交易频率</span>
              <p className="font-medium">{formatInterval(activePreset.configJson.min_trade_interval_seconds)}</p>
            </div>
            <div>
              <span className="text-muted-foreground">止损/止盈</span>
              <p className="font-medium">ATR×{activePreset.configJson.stop_loss_atr_multiplier} / ATR×{activePreset.configJson.take_profit_atr_multiplier}</p>
            </div>
            <div>
              <span className="text-muted-foreground">最大仓位</span>
              <p className="font-medium">{activePreset.configJson.max_position_pct}%</p>
            </div>
            <div>
              <span className="text-muted-foreground">AI/量化权重</span>
              <p className="font-medium">{Math.round(activePreset.configJson.ai_weight * 100)}% / {Math.round(activePreset.configJson.quant_weight * 100)}%</p>
            </div>
          </div>
        </div>
      )}

      {/* Strategy suggestion */}
      <div className="space-y-3">
        <button
          onClick={handleSuggest}
          disabled={suggesting}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-md bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-colors disabled:opacity-50"
        >
          {suggesting ? (
            <>
              <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              AI 分析中...
            </>
          ) : (
            <>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
              </svg>
              获取策略建议
            </>
          )}
        </button>

        {suggestion && (
          <div className="rounded-lg border border-blue-500/50 bg-blue-500/5 p-5">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <svg className="w-5 h-5 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                </svg>
                <h3 className="font-semibold text-blue-400">AI 策略建议</h3>
              </div>
              <button onClick={() => setSuggestion(null)} className="text-muted-foreground hover:text-foreground text-sm">关闭</button>
            </div>
            <div className="space-y-3 text-sm">
              {activePreset && (
                <div className="rounded-md border border-border bg-muted/30 p-3">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-muted-foreground">当前策略: {activePreset.displayName}</span>
                    <span className={`font-semibold ${
                      suggestion.current_strategy_score >= 7 ? "text-green-400" :
                      suggestion.current_strategy_score >= 4 ? "text-yellow-400" : "text-red-400"
                    }`}>
                      适配度: {suggestion.current_strategy_score}/10
                    </span>
                  </div>
                  <p className="text-muted-foreground text-xs">{suggestion.current_strategy_analysis}</p>
                </div>
              )}
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground">推荐策略:</span>
                <span className="font-semibold text-lg">{suggestion.recommended_display_name}</span>
                <span className="text-xs px-2 py-0.5 rounded bg-blue-500/20 text-blue-400">{suggestion.market_state}</span>
              </div>
              <p className="text-muted-foreground">{suggestion.reason}</p>
              {suggestion.recommended_preset !== presets.find((p) => p.id === currentActiveId)?.name && (
                <button
                  onClick={() => handleActivatePreset(suggestion.recommended_preset)}
                  disabled={locked}
                  className={`mt-2 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                    locked ? "bg-muted text-muted-foreground cursor-not-allowed" : "bg-blue-600 text-white hover:bg-blue-700"
                  }`}
                >
                  {locked ? "策略已锁定" : "切换到此策略"}
                </button>
              )}
              {suggestion.recommended_preset === presets.find((p) => p.id === currentActiveId)?.name && (
                <p className="text-green-400 text-xs mt-1">当前策略已是推荐策略</p>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Preset cards grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {presets.map((preset) => {
          const isActive = preset.id === currentActiveId;
          const isEditing = preset.id === editingId;
          const config = isEditing && editConfig ? editConfig : preset.configJson;
          return (
            <div
              key={preset.id}
              className={`rounded-lg border p-5 transition-colors ${
                isActive ? "border-primary bg-primary/5" :
                isEditing ? "border-blue-500 bg-blue-500/5" :
                "border-border bg-card hover:border-muted-foreground/50"
              }`}
            >
              {/* Header */}
              <div className="flex items-start justify-between mb-3">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <h3 className="font-semibold text-base">{preset.displayName}</h3>
                    <RiskBadge level={preset.riskLevel} />
                    <span className="text-xs px-2 py-0.5 rounded bg-muted text-muted-foreground">
                      {CATEGORY_LABELS[preset.category] || preset.category}
                    </span>
                    {!preset.isSystem && (
                      <span className="text-xs px-2 py-0.5 rounded bg-purple-500/20 text-purple-400">自定义</span>
                    )}
                    {preset.isSystem && preset.isModified && (
                      <span className="text-xs px-2 py-0.5 rounded bg-amber-500/20 text-amber-400">已修改</span>
                    )}
                  </div>
                  <p className="text-sm text-muted-foreground">{preset.description}</p>
                </div>
                <div className="flex items-center gap-2">
                  {isActive && (
                    <span className="text-xs px-2 py-1 rounded bg-primary/20 text-primary font-medium">运行中</span>
                  )}
                  {!isEditing && (
                    <button
                      onClick={() => startEdit(preset)}
                      className="text-xs px-2 py-1 rounded border border-border hover:bg-muted transition-colors"
                    >
                      编辑
                    </button>
                  )}
                </div>
              </div>

              {/* Core params - always visible */}
              {isEditing ? (
                <div className="space-y-4">
                  {/* Core params editing */}
                  <div className="grid grid-cols-2 gap-3">
                    <WeightInput label="AI 权重" value={config.ai_weight} onChange={(v) => updateConfig("ai_weight", v)} />
                    <WeightInput label="量化权重" value={config.quant_weight} onChange={(v) => updateConfig("quant_weight", v)} />
                    <NumInput label="止损 ATR 倍数" value={config.stop_loss_atr_multiplier} onChange={(v) => updateConfig("stop_loss_atr_multiplier", v)} min={0.5} step={0.1} />
                    <NumInput label="止盈 ATR 倍数" value={config.take_profit_atr_multiplier} onChange={(v) => updateConfig("take_profit_atr_multiplier", v)} min={0.5} step={0.1} />
                    <NumInput label="交易间隔" value={config.min_trade_interval_seconds} onChange={(v) => updateConfig("min_trade_interval_seconds", v)} min={60} step={60} suffix="秒" />
                    <NumInput label="最大仓位" value={config.max_position_pct} onChange={(v) => updateConfig("max_position_pct", v)} min={1} max={100} step={1} suffix="%" />
                  </div>

                  {/* Advanced params toggle */}
                  <button
                    type="button"
                    onClick={() => setShowAdvanced(!showAdvanced)}
                    className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
                  >
                    <svg className={`w-3 h-3 transition-transform ${showAdvanced ? "rotate-90" : ""}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                    </svg>
                    高级参数
                  </button>

                  {showAdvanced && (
                    <div className="space-y-4 border-t border-border pt-3">
                      {/* Strategy selection */}
                      <div>
                        <label className="text-xs text-muted-foreground block mb-2">启用策略</label>
                        <div className="flex gap-3">
                          {ALL_STRATEGIES.map((s) => (
                            <label key={s} className="flex items-center gap-1.5 text-sm cursor-pointer">
                              <input
                                type="checkbox"
                                checked={config.enabled_strategies.includes(s)}
                                onChange={(e) => {
                                  const newStrategies = e.target.checked
                                    ? [...config.enabled_strategies, s]
                                    : config.enabled_strategies.filter((x) => x !== s);
                                  updateConfig("enabled_strategies", newStrategies);
                                  // Update weights
                                  const newWeights = { ...config.strategy_weights };
                                  if (e.target.checked && !(s in newWeights)) {
                                    newWeights[s] = 0.5;
                                  } else if (!e.target.checked) {
                                    delete newWeights[s];
                                  }
                                  updateConfig("strategy_weights", newWeights);
                                }}
                                className="rounded border-border"
                              />
                              {STRATEGY_LABELS[s] || s}
                            </label>
                          ))}
                        </div>
                      </div>

                      {/* Strategy weights */}
                      {config.enabled_strategies.length > 0 && (
                        <div className="grid grid-cols-2 gap-3">
                          {config.enabled_strategies.map((s) => (
                            <NumInput
                              key={s}
                              label={`${STRATEGY_LABELS[s] || s} 权重`}
                              value={config.strategy_weights[s] ?? 0}
                              onChange={(v) => updateConfig("strategy_weights", { ...config.strategy_weights, [s]: v })}
                              min={0} max={1} step={0.1}
                            />
                          ))}
                        </div>
                      )}

                      {/* Timeframes */}
                      <div>
                        <label className="text-xs text-muted-foreground block mb-2">时间周期</label>
                        <div className="flex gap-2 flex-wrap">
                          {ALL_TIMEFRAMES.map((tf) => (
                            <label key={tf} className="flex items-center gap-1.5 text-sm cursor-pointer">
                              <input
                                type="checkbox"
                                checked={config.timeframes.includes(tf)}
                                onChange={(e) => {
                                  const newTf = e.target.checked
                                    ? [...config.timeframes, tf]
                                    : config.timeframes.filter((x) => x !== tf);
                                  updateConfig("timeframes", newTf);
                                }}
                                className="rounded border-border"
                              />
                              {tf}
                            </label>
                          ))}
                        </div>
                      </div>

                      {/* Boolean toggles */}
                      <div className="grid grid-cols-2 gap-3">
                        <Toggle label="允许加仓" checked={config.enable_pyramid} onChange={(v) => updateConfig("enable_pyramid", v)} />
                        <Toggle label="情感分析" checked={config.enable_sentiment} onChange={(v) => updateConfig("enable_sentiment", v)} />
                        <Toggle label="仅市价单" checked={config.use_market_order_only} onChange={(v) => updateConfig("use_market_order_only", v)} />
                      </div>

                      {config.enable_pyramid && (
                        <NumInput label="最大加仓次数" value={config.max_pyramid_times} onChange={(v) => updateConfig("max_pyramid_times", v)} min={0} max={10} />
                      )}
                      {config.enable_sentiment && (
                        <WeightInput label="情感权重" value={config.sentiment_weight} onChange={(v) => updateConfig("sentiment_weight", v)} />
                      )}
                      <NumInput label="最小盈利阈值" value={config.min_profit_threshold} onChange={(v) => updateConfig("min_profit_threshold", v)} min={0} step={0.01} suffix="%" />
                    </div>
                  )}

                  {/* Validation errors */}
                  {validationErrors.length > 0 && (
                    <div className="text-xs text-red-400 space-y-0.5">
                      {validationErrors.map((e, i) => <p key={i}>{e}</p>)}
                    </div>
                  )}

                  {/* Action bar */}
                  <div className="flex gap-2 border-t border-border pt-3">
                    <button
                      onClick={cancelEdit}
                      className="px-3 py-1.5 rounded text-sm border border-border hover:bg-muted transition-colors"
                    >
                      取消
                    </button>
                    <button
                      onClick={handleSave}
                      disabled={!canSave || saving}
                      className="px-3 py-1.5 rounded text-sm bg-primary text-primary-foreground font-medium hover:bg-primary/90 disabled:opacity-50 transition-colors"
                    >
                      {saving ? "保存中..." : "保存"}
                    </button>
                    <button
                      onClick={openSaveAsDialog}
                      disabled={saving || validationErrors.length > 0}
                      className="px-3 py-1.5 rounded text-sm border border-blue-500 text-blue-400 hover:bg-blue-500/10 disabled:opacity-50 transition-colors"
                    >
                      另存为
                    </button>
                    {preset.isSystem && preset.isModified && (
                      <button
                        onClick={() => handleReset(preset.id)}
                        disabled={saving}
                        className="px-3 py-1.5 rounded text-sm border border-amber-500 text-amber-400 hover:bg-amber-500/10 disabled:opacity-50 transition-colors ml-auto"
                      >
                        重置默认
                      </button>
                    )}
                    {!preset.isSystem && (
                      <button
                        onClick={() => setShowDeleteConfirm(preset.id)}
                        disabled={saving || isActive}
                        className="px-3 py-1.5 rounded text-sm border border-red-500 text-red-400 hover:bg-red-500/10 disabled:opacity-50 transition-colors ml-auto"
                        title={isActive ? "不能删除当前激活的策略" : ""}
                      >
                        删除
                      </button>
                    )}
                  </div>
                </div>
              ) : (
                <>
                  {/* Read-only params */}
                  <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm mb-3">
                    <div>
                      <span className="text-muted-foreground text-xs">交易间隔</span>
                      <p className="font-medium">{formatInterval(config.min_trade_interval_seconds)}</p>
                    </div>
                    <div>
                      <span className="text-muted-foreground text-xs">最大仓位</span>
                      <p className="font-medium">{config.max_position_pct}%</p>
                    </div>
                    <div>
                      <span className="text-muted-foreground text-xs">止损/止盈</span>
                      <p className="font-medium">ATR×{config.stop_loss_atr_multiplier}/{config.take_profit_atr_multiplier}</p>
                    </div>
                    <div>
                      <span className="text-muted-foreground text-xs">AI/量化</span>
                      <p className="font-medium">{Math.round(config.ai_weight * 100)}%/{Math.round(config.quant_weight * 100)}%</p>
                    </div>
                  </div>

                  {/* Stats */}
                  <div className="flex gap-4 text-xs text-muted-foreground mb-3 border-t border-border pt-2">
                    <span>交易: {preset.stats.totalTrades}笔</span>
                    <span className={preset.stats.totalPnl >= 0 ? "text-green-400" : "text-red-400"}>
                      收益: {preset.stats.totalPnl >= 0 ? "+" : ""}{preset.stats.totalPnl}
                    </span>
                    <span>胜率: {preset.stats.winRate}%</span>
                  </div>

                  {/* Action buttons row */}
                  <div className="flex gap-2">
                    {!isActive && (
                      <button
                        onClick={() => { setConfirmPreset(preset); setLockWithActivate(false); }}
                        disabled={locked}
                        className={`flex-1 py-2 rounded-md text-sm font-medium transition-colors ${
                          locked ? "bg-muted text-muted-foreground cursor-not-allowed" : "bg-primary/10 text-primary hover:bg-primary/20"
                        }`}
                        title={locked ? "当前策略已锁定，请先解锁" : ""}
                      >
                        {locked ? "策略已锁定" : "激活此策略"}
                      </button>
                    )}
                    {preset.isSystem && preset.isModified && !isEditing && (
                      <button
                        onClick={() => handleReset(preset.id)}
                        className="px-3 py-2 rounded-md text-xs border border-amber-500 text-amber-400 hover:bg-amber-500/10 transition-colors"
                      >
                        重置
                      </button>
                    )}
                    {!preset.isSystem && !isActive && !isEditing && (
                      <button
                        onClick={() => setShowDeleteConfirm(preset.id)}
                        className="px-3 py-2 rounded-md text-xs border border-red-500 text-red-400 hover:bg-red-500/10 transition-colors"
                      >
                        删除
                      </button>
                    )}
                  </div>
                </>
              )}
            </div>
          );
        })}
      </div>

      {/* Activate confirmation dialog */}
      {confirmPreset && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-card border border-border rounded-lg p-6 max-w-md w-full mx-4">
            <h3 className="text-lg font-semibold mb-4">确认切换策略</h3>
            <div className="space-y-2 text-sm mb-4">
              <p>
                <span className="text-muted-foreground">当前: </span>
                <span className="font-medium">{activePreset?.displayName || "无"}</span>
              </p>
              <p>
                <span className="text-muted-foreground">切换为: </span>
                <span className="font-medium">{confirmPreset.displayName}</span>{" "}
                <RiskBadge level={confirmPreset.riskLevel} />
              </p>
            </div>
            <label className="flex items-center gap-2 text-sm mb-4 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={lockWithActivate}
                onChange={(e) => setLockWithActivate(e.target.checked)}
                className="rounded border-border"
              />
              <span>同时锁定此策略（阻止自动切换）</span>
            </label>
            <p className="text-xs text-muted-foreground mb-6">
              已有持仓不受影响，新策略将在下个分析周期生效。
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => { setConfirmPreset(null); setLockWithActivate(false); }}
                className="flex-1 py-2 rounded-md border border-border text-sm hover:bg-muted transition-colors"
              >
                取消
              </button>
              <button
                onClick={() => handleActivate(confirmPreset)}
                disabled={activating}
                className="flex-1 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
              >
                {activating ? "切换中..." : "确认切换"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Overwrite confirm dialog */}
      {showOverwriteConfirm && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-card border border-border rounded-lg p-6 max-w-sm w-full mx-4">
            <h3 className="text-lg font-semibold mb-3">确认覆盖保存</h3>
            <p className="text-sm text-muted-foreground mb-4">
              将覆盖系统默认配置。修改后可通过"重置默认"按钮恢复。
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setShowOverwriteConfirm(false)}
                className="flex-1 py-2 rounded-md border border-border text-sm hover:bg-muted transition-colors"
              >
                取消
              </button>
              <button
                onClick={handleSave}
                disabled={saving}
                className="flex-1 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
              >
                {saving ? "保存中..." : "确认保存"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Save-as dialog */}
      {showSaveAsDialog && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-card border border-border rounded-lg p-6 max-w-sm w-full mx-4">
            <h3 className="text-lg font-semibold mb-3">另存为新策略</h3>
            <label className="text-sm text-muted-foreground block mb-1">策略名称</label>
            <input
              type="text"
              value={saveAsName}
              onChange={(e) => setSaveAsName(e.target.value)}
              className="w-full rounded border border-border bg-background px-3 py-2 text-sm mb-4"
            />
            <div className="flex gap-3">
              <button
                onClick={() => setShowSaveAsDialog(false)}
                className="flex-1 py-2 rounded-md border border-border text-sm hover:bg-muted transition-colors"
              >
                取消
              </button>
              <button
                onClick={handleSaveAs}
                disabled={saving || !saveAsName.trim()}
                className="flex-1 py-2 rounded-md bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-colors disabled:opacity-50"
              >
                {saving ? "保存中..." : "确认另存"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete confirm dialog */}
      {showDeleteConfirm !== null && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-card border border-border rounded-lg p-6 max-w-sm w-full mx-4">
            <h3 className="text-lg font-semibold mb-3">确认删除</h3>
            <p className="text-sm text-muted-foreground mb-4">
              确定要删除这个自定义策略吗？此操作不可恢复。
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setShowDeleteConfirm(null)}
                className="flex-1 py-2 rounded-md border border-border text-sm hover:bg-muted transition-colors"
              >
                取消
              </button>
              <button
                onClick={() => handleDelete(showDeleteConfirm)}
                disabled={saving}
                className="flex-1 py-2 rounded-md bg-red-600 text-white text-sm font-medium hover:bg-red-700 transition-colors disabled:opacity-50"
              >
                {saving ? "删除中..." : "确认删除"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
