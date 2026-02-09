import { useState } from "react";
import type { Route } from "./+types/dashboard.strategy";

export async function loader(_args: Route.LoaderArgs) {
  const res = await fetch(
    `${process.env.INTERNAL_API_URL || "http://localhost:5173"}/api/strategy-presets`
  );
  if (!res.ok) {
    return { presets: [], activePresetId: null, activatedAt: null };
  }
  return await res.json();
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
  const { presets, activePresetId, activatedAt } = loaderData as {
    presets: Preset[];
    activePresetId: number | null;
    activatedAt: string | null;
  };
  const [confirmPreset, setConfirmPreset] = useState<Preset | null>(null);
  const [activating, setActivating] = useState(false);
  const [currentActiveId, setCurrentActiveId] = useState(activePresetId);

  const activePreset = presets.find((p) => p.id === currentActiveId);

  const handleActivate = async (preset: Preset) => {
    setActivating(true);
    try {
      const res = await fetch("/api/strategy-presets/activate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ presetId: preset.id }),
      });
      if (res.ok) {
        setCurrentActiveId(preset.id);
        setConfirmPreset(null);
      }
    } catch (err) {
      console.error("Failed to activate preset:", err);
    } finally {
      setActivating(false);
    }
  };

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold">策略选择</h1>

      {/* 当前活跃策略 */}
      {activePreset && (
        <div className="rounded-lg border border-border bg-card p-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <div className="h-3 w-3 rounded-full bg-green-500 animate-pulse" />
              <h2 className="text-lg font-semibold">当前策略: {activePreset.displayName}</h2>
              <RiskBadge level={activePreset.riskLevel} />
            </div>
            {activatedAt && (
              <span className="text-sm text-muted-foreground">
                运行自 {new Date(activatedAt).toLocaleString("zh-CN")}
              </span>
            )}
          </div>
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
                  onClick={() => setConfirmPreset(preset)}
                  className="w-full py-2 rounded-md bg-primary/10 text-primary hover:bg-primary/20 text-sm font-medium transition-colors"
                >
                  激活此策略
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
            <p className="text-xs text-muted-foreground mb-6">
              已有持仓不受影响，新策略将在下个分析周期生效。
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setConfirmPreset(null)}
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
