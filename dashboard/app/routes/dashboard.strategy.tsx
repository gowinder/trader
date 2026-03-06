import { useState } from "react";
import type { Route } from "./+types/dashboard.strategy";

export async function loader({ request }: Route.LoaderArgs) {
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
  timeframes: string[];
  min_trade_interval_seconds: number;
  stop_loss_atr_multiplier: number;
  take_profit_atr_multiplier: number;
  max_position_pct: number;
  enable_pyramid: boolean;
  enable_sentiment: boolean;
  min_profit_threshold: number;
}

interface Preset {
  id: number;
  name: string;
  displayName: string;
  description: string;
  category: string;
  riskLevel: string;
  configJson: PresetConfig;
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

export default function StrategyPage({ loaderData }: Route.ComponentProps) {
  const { presets, activePresetId, activatedAt, isLocked: initialLocked } = loaderData as {
    presets: Preset[];
    activePresetId: number | null;
    activatedAt: string | null;
    isLocked: boolean;
  };
  const [confirmPreset, setConfirmPreset] = useState<Preset | null>(null);
  const [activating, setActivating] = useState(false);
  const [currentActiveId, setCurrentActiveId] = useState(activePresetId);
  const [locked, setLocked] = useState(initialLocked);
  const [lockWithActivate, setLockWithActivate] = useState(false);
  const [togglingLock, setTogglingLock] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const activePreset = presets.find((p) => p.id === currentActiveId);

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
    } catch (err) {
      console.error("Failed to toggle lock:", err);
      setError("网络错误");
    } finally {
      setTogglingLock(false);
    }
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
    } catch (err) {
      console.error("Failed to activate preset:", err);
      setError("网络错误");
    } finally {
      setActivating(false);
    }
  };

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold">策略选择</h1>

      {/* 错误提示 */}
      {error && (
        <div className="rounded-lg border border-red-500/50 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          {error}
          <button onClick={() => setError(null)} className="ml-2 underline text-xs">关闭</button>
        </div>
      )}

      {/* 当前活跃策略 */}
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
              {/* 锁定开关 */}
              <button
                type="button"
                onClick={handleToggleLock}
                disabled={togglingLock}
                className={`relative inline-flex h-7 w-12 items-center rounded-full transition-colors disabled:opacity-50 ${
                  locked ? "bg-yellow-500" : "bg-muted"
                }`}
                title={locked ? "点击解锁，允许自动切换策略" : "点击锁定，阻止自动切换策略"}
              >
                <span
                  className={`inline-flex h-5 w-5 items-center justify-center rounded-full bg-white transition-transform ${
                    locked ? "translate-x-6" : "translate-x-1"
                  }`}
                >
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

      {/* 策略模板网格 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {presets.map((preset) => {
          const isActive = preset.id === currentActiveId;
          const config = preset.configJson;
          return (
            <div
              key={preset.id}
              className={`rounded-lg border p-5 transition-colors ${
                isActive
                  ? "border-primary bg-primary/5"
                  : "border-border bg-card hover:border-muted-foreground/50"
              }`}
            >
              <div className="flex items-start justify-between mb-3">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <h3 className="font-semibold text-base">{preset.displayName}</h3>
                    <RiskBadge level={preset.riskLevel} />
                    <span className="text-xs px-2 py-0.5 rounded bg-muted text-muted-foreground">
                      {CATEGORY_LABELS[preset.category] || preset.category}
                    </span>
                  </div>
                  <p className="text-sm text-muted-foreground">{preset.description}</p>
                </div>
                {isActive && (
                  <span className="text-xs px-2 py-1 rounded bg-primary/20 text-primary font-medium">
                    运行中
                  </span>
                )}
              </div>

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

              {/* 历史表现 */}
              <div className="flex gap-4 text-xs text-muted-foreground mb-3 border-t border-border pt-2">
                <span>交易: {preset.stats.totalTrades}笔</span>
                <span className={preset.stats.totalPnl >= 0 ? "text-green-400" : "text-red-400"}>
                  收益: {preset.stats.totalPnl >= 0 ? "+" : ""}{preset.stats.totalPnl}
                </span>
                <span>胜率: {preset.stats.winRate}%</span>
              </div>

              {!isActive && (
                <button
                  onClick={() => { setConfirmPreset(preset); setLockWithActivate(false); }}
                  disabled={locked}
                  className={`w-full py-2 rounded-md text-sm font-medium transition-colors ${
                    locked
                      ? "bg-muted text-muted-foreground cursor-not-allowed"
                      : "bg-primary/10 text-primary hover:bg-primary/20"
                  }`}
                  title={locked ? "当前策略已锁定，请先解锁" : ""}
                >
                  {locked ? "策略已锁定" : "激活此策略"}
                </button>
              )}
            </div>
          );
        })}
      </div>

      {/* 确认弹窗 */}
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
                <span className="font-medium">{confirmPreset.displayName}</span>
                {" "}
                <RiskBadge level={confirmPreset.riskLevel} />
              </p>
            </div>

            {/* 锁定 checkbox */}
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
    </div>
  );
}
