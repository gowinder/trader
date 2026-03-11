import { useEffect, useState, useMemo, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card";
import { Button } from "~/components/ui/button";
import { Switch } from "~/components/ui/switch";
import { Coins, Search, Save, RefreshCw, ChevronDown, RotateCcw, ArrowUpDown, Star, Sparkles, CheckCheck } from "lucide-react";

// --- Data Structures ---

interface SymbolConfig {
  symbol: string;
  preset_name: string;
  preset_display_name: string;
  config_overrides: Record<string, number>;
  preset_config: Record<string, any>;
}

interface PresetOption {
  name: string;
  displayName: string;
  description: string;
  category: string;
  riskLevel: string;
  config: Record<string, any>;
}

interface TunableParam {
  key: string;
  label: string;
  min: number;
  max: number;
  step: number;
}

const TUNABLE_PARAMS: { weights: TunableParam[]; risk: TunableParam[] } = {
  weights: [
    { key: "ai_weight", label: "AI 权重", min: 0, max: 1, step: 0.05 },
    { key: "quant_weight", label: "量化权重", min: 0, max: 1, step: 0.05 },
    { key: "sentiment_weight", label: "情绪权重", min: 0, max: 1, step: 0.05 },
  ],
  risk: [
    { key: "stop_loss_atr_multiplier", label: "止损 ATR 倍数", min: 0.5, max: 10, step: 0.5 },
    { key: "take_profit_atr_multiplier", label: "止盈 ATR 倍数", min: 1, max: 20, step: 0.5 },
    { key: "max_position_pct", label: "最大仓位 %", min: 1, max: 50, step: 1 },
  ],
};

const STRATEGY_KEYS = [
  "trend_following_enabled",
  "mean_reversion_enabled",
  "breakout_enabled",
  "scalping_enabled",
  "momentum_enabled",
];

const STRATEGY_LABELS: Record<string, string> = {
  trend_following_enabled: "趋势跟随",
  mean_reversion_enabled: "均值回归",
  breakout_enabled: "突破",
  scalping_enabled: "剥头皮",
  momentum_enabled: "动量",
};

// 推荐交易对：主流 + 高流动性山寨币
const RECOMMENDED_SYMBOLS = [
  "BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT",
  "BNB/USDT:USDT", "XRP/USDT:USDT", "ADA/USDT:USDT",
  "DOGE/USDT:USDT", "AVAX/USDT:USDT", "DOT/USDT:USDT",
  "LINK/USDT:USDT", "NEAR/USDT:USDT", "SUI/USDT:USDT",
  "ARB/USDT:USDT", "OP/USDT:USDT", "APT/USDT:USDT",
  "FIL/USDT:USDT", "ATOM/USDT:USDT", "UNI/USDT:USDT",
  "RENDER/USDT:USDT", "INJ/USDT:USDT",
];

type SortMode = "alpha" | "enabled_first" | "recommended_first" | "volume_desc";

// --- Component ---

export default function SymbolsPage() {
  const [availableSymbols, setAvailableSymbols] = useState<string[]>([]);
  const [configuredSymbols, setConfiguredSymbols] = useState<Map<string, SymbolConfig>>(new Map());
  const [presets, setPresets] = useState<PresetOption[]>([]);
  const [expandedSymbols, setExpandedSymbols] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState("");
  const [sortMode, setSortMode] = useState<SortMode>("enabled_first");
  const [volumes, setVolumes] = useState<Record<string, number>>({});
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [batchSuggesting, setBatchSuggesting] = useState(false);
  const [symbolSuggestions, setSymbolSuggestions] = useState<Record<string, { recommended_preset: string; recommended_display_name: string; reason: string; market_state: string }>>({});

  // Track original configured state for dirty detection
  const [originalConfigured, setOriginalConfigured] = useState<Map<string, SymbolConfig>>(new Map());

  const fetchData = useCallback(async () => {
    try {
      const [symbolsRes, presetsRes] = await Promise.all([
        fetch("/api/symbols"),
        fetch("/api/presets-list"),
      ]);
      const symbolsJson = await symbolsRes.json();
      const presetsJson = await presetsRes.json();

      setAvailableSymbols(symbolsJson.available || []);
      setVolumes(symbolsJson.volumes || {});
      setPresets(presetsJson.presets || []);

      const cfgMap = new Map<string, SymbolConfig>();
      for (const cfg of symbolsJson.configured || []) {
        cfgMap.set(cfg.symbol, cfg);
      }
      setConfiguredSymbols(cfgMap);
      setOriginalConfigured(new Map(cfgMap));
    } catch {
      // use defaults
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Merge available + configured symbols
  const allSymbols = useMemo(() => {
    const set = new Set([...availableSymbols, ...configuredSymbols.keys()]);
    return Array.from(set).sort();
  }, [availableSymbols, configuredSymbols]);

  const filteredSymbols = useMemo(() => {
    let list = allSymbols;
    if (search.trim()) {
      const q = search.toUpperCase();
      list = list.filter((s) => s.toUpperCase().includes(q));
    }
    // Apply sorting
    return [...list].sort((a, b) => {
      if (sortMode === "enabled_first") {
        const aEnabled = configuredSymbols.has(a) ? 0 : 1;
        const bEnabled = configuredSymbols.has(b) ? 0 : 1;
        if (aEnabled !== bEnabled) return aEnabled - bEnabled;
      } else if (sortMode === "recommended_first") {
        const aRec = RECOMMENDED_SYMBOLS.includes(a) ? 0 : 1;
        const bRec = RECOMMENDED_SYMBOLS.includes(b) ? 0 : 1;
        if (aRec !== bRec) return aRec - bRec;
      } else if (sortMode === "volume_desc") {
        const aVol = volumes[a] ?? 0;
        const bVol = volumes[b] ?? 0;
        if (aVol !== bVol) return bVol - aVol;
      }
      return a.localeCompare(b);
    });
  }, [allSymbols, search, sortMode, configuredSymbols, volumes]);

  const hasChanges = useMemo(() => {
    if (originalConfigured.size !== configuredSymbols.size) return true;
    for (const [symbol, cfg] of configuredSymbols) {
      const orig = originalConfigured.get(symbol);
      if (!orig) return true;
      if (cfg.preset_name !== orig.preset_name) return true;
      const oKeys = Object.keys(orig.config_overrides);
      const cKeys = Object.keys(cfg.config_overrides);
      if (oKeys.length !== cKeys.length) return true;
      for (const k of cKeys) {
        if (cfg.config_overrides[k] !== orig.config_overrides[k]) return true;
      }
    }
    for (const symbol of originalConfigured.keys()) {
      if (!configuredSymbols.has(symbol)) return true;
    }
    return false;
  }, [originalConfigured, configuredSymbols]);

  const toggleSymbol = (symbol: string) => {
    setConfiguredSymbols((prev) => {
      const next = new Map(prev);
      if (next.has(symbol)) {
        next.delete(symbol);
        setExpandedSymbols((es) => {
          const ns = new Set(es);
          ns.delete(symbol);
          return ns;
        });
      } else {
        // Enable: need to select preset, expand the row
        // Use first preset as default
        if (presets.length > 0) {
          const preset = presets[0];
          next.set(symbol, {
            symbol,
            preset_name: preset.name,
            preset_display_name: preset.displayName,
            config_overrides: {},
            preset_config: { ...preset.config },
          });
        }
        setExpandedSymbols((es) => new Set(es).add(symbol));
      }
      return next;
    });
  };

  const toggleExpand = (symbol: string) => {
    setExpandedSymbols((prev) => {
      const next = new Set(prev);
      if (next.has(symbol)) {
        next.delete(symbol);
      } else {
        next.add(symbol);
      }
      return next;
    });
  };

  const changePreset = (symbol: string, presetName: string) => {
    const preset = presets.find((p) => p.name === presetName);
    if (!preset) return;
    setConfiguredSymbols((prev) => {
      const next = new Map(prev);
      const existing = next.get(symbol);
      if (existing) {
        next.set(symbol, {
          ...existing,
          preset_name: preset.name,
          preset_display_name: preset.displayName,
          config_overrides: {},
          preset_config: { ...preset.config },
        });
      }
      return next;
    });
  };

  const updateParam = (symbol: string, key: string, value: number) => {
    setConfiguredSymbols((prev) => {
      const next = new Map(prev);
      const cfg = next.get(symbol);
      if (!cfg) return prev;

      const defaultVal = cfg.preset_config[key];
      const newOverrides = { ...cfg.config_overrides };

      if (defaultVal !== undefined && Math.abs(value - defaultVal) < 1e-9) {
        delete newOverrides[key];
      } else {
        newOverrides[key] = value;
      }

      next.set(symbol, { ...cfg, config_overrides: newOverrides });
      return next;
    });
  };

  const enableRecommended = () => {
    if (presets.length === 0) return;
    setConfiguredSymbols((prev) => {
      const next = new Map(prev);
      const defaultPreset = presets[0];
      for (const symbol of RECOMMENDED_SYMBOLS) {
        if (!next.has(symbol) && allSymbols.includes(symbol)) {
          next.set(symbol, {
            symbol,
            preset_name: defaultPreset.name,
            preset_display_name: defaultPreset.displayName,
            config_overrides: {},
            preset_config: { ...defaultPreset.config },
          });
        }
      }
      return next;
    });
  };

  const handleBatchSuggest = async () => {
    const enabledSymbols = Array.from(configuredSymbols.keys());
    if (enabledSymbols.length === 0) return;
    setBatchSuggesting(true);
    setSymbolSuggestions({});
    try {
      const triggerRes = await fetch("/api/symbol-strategy-suggest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbols: enabledSymbols }),
      });
      if (!triggerRes.ok) {
        const data = await triggerRes.json().catch(() => ({}));
        setMessage({ type: "error", text: data.error || "触发策略建议失败" });
        return;
      }
      const { taskId } = await triggerRes.json();
      for (let i = 0; i < 60; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        const pollRes = await fetch(`/api/symbol-strategy-suggest?taskId=${taskId}`);
        if (!pollRes.ok) continue;
        const result = await pollRes.json();
        if (result.status === "completed" && result.suggestions) {
          setSymbolSuggestions(result.suggestions);
          setMessage({ type: "success", text: `AI 已为 ${Object.keys(result.suggestions).length} 个交易对生成策略建议` });
          return;
        }
        if (result.status === "error") {
          setMessage({ type: "error", text: result.error || "策略建议生成失败" });
          return;
        }
      }
      setMessage({ type: "error", text: "策略建议超时，请重试" });
    } catch {
      setMessage({ type: "error", text: "网络错误" });
    } finally {
      setBatchSuggesting(false);
    }
  };

  const handleBatchAdopt = () => {
    if (Object.keys(symbolSuggestions).length === 0) return;
    setConfiguredSymbols((prev) => {
      const next = new Map(prev);
      for (const [symbol, suggestion] of Object.entries(symbolSuggestions)) {
        const existing = next.get(symbol);
        if (!existing) continue;
        const preset = presets.find((p) => p.name === suggestion.recommended_preset);
        if (preset) {
          next.set(symbol, {
            ...existing,
            preset_name: preset.name,
            preset_display_name: preset.displayName,
            config_overrides: {},
            preset_config: { ...preset.config },
          });
        }
      }
      return next;
    });
    setSymbolSuggestions({});
    setMessage({ type: "success", text: "已批量采纳 AI 策略建议，请点击保存生效" });
  };

  const resetOverrides = (symbol: string) => {
    setConfiguredSymbols((prev) => {
      const next = new Map(prev);
      const cfg = next.get(symbol);
      if (!cfg) return prev;
      next.set(symbol, { ...cfg, config_overrides: {} });
      return next;
    });
  };

  const saveSymbols = async () => {
    setSaving(true);
    setMessage(null);
    try {
      const savePayload = {
        configured: Array.from(configuredSymbols.values()).map((cfg) => ({
          symbol: cfg.symbol,
          preset_name: cfg.preset_name,
          config_overrides: cfg.config_overrides,
        })),
      };
      const res = await fetch("/api/symbols", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(savePayload),
      });
      if (res.ok) {
        setOriginalConfigured(new Map(configuredSymbols));
        setMessage({ type: "success", text: "交易对配置已保存，将在下一个决策周期生效" });
      } else {
        const err = await res.json();
        setMessage({ type: "error", text: err.error || "保存失败" });
      }
    } catch {
      setMessage({ type: "error", text: "保存失败" });
    } finally {
      setSaving(false);
    }
  };

  const getEffectiveValue = (cfg: SymbolConfig, key: string): number => {
    if (key in cfg.config_overrides) return cfg.config_overrides[key];
    return cfg.preset_config[key] ?? 0;
  };

  const isParamModified = (cfg: SymbolConfig, key: string): boolean => {
    return key in cfg.config_overrides;
  };

  const hasOverrides = (cfg: SymbolConfig): boolean => {
    return Object.keys(cfg.config_overrides).length > 0;
  };

  if (loading) {
    return <div className="p-8 text-center text-muted-foreground">加载中...</div>;
  }

  return (
    <div className="space-y-6 pb-20">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Coins className="h-6 w-6" />
          交易对管理
        </h1>
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">
            已启用 {configuredSymbols.size} / {allSymbols.length} 个
          </span>
        </div>
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
              交易对列表
              {availableSymbols.length === 0 && (
                <span className="text-xs text-yellow-500 font-normal">
                  (交易所可用列表尚未加载，请等待 Trader 启动)
                </span>
              )}
            </span>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={saveSymbols}
                disabled={saving || !hasChanges}
              >
                {saving ? (
                  <>
                    <RefreshCw className="mr-1 h-3 w-3 animate-spin" />
                    保存中...
                  </>
                ) : (
                  <>
                    <Save className="mr-1 h-3 w-3" />
                    保存
                  </>
                )}
              </Button>
            </div>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              placeholder="搜索交易对..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full rounded-md border border-input bg-background px-9 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
            {search && (
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-muted-foreground">
                {filteredSymbols.length} 个结果
              </span>
            )}
          </div>

          {/* Toolbar: sort + recommended */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <ArrowUpDown className="h-3.5 w-3.5 text-muted-foreground" />
              {(["enabled_first", "recommended_first", "volume_desc", "alpha"] as SortMode[]).map((mode) => {
                const labels: Record<SortMode, string> = {
                  enabled_first: "已启用优先",
                  recommended_first: "推荐优先",
                  volume_desc: "成交量",
                  alpha: "字母",
                };
                return (
                  <button
                    key={mode}
                    onClick={() => setSortMode(mode)}
                    className={`text-xs px-2 py-1 rounded transition-colors ${
                      sortMode === mode
                        ? "bg-primary/15 text-primary"
                        : "text-muted-foreground hover:text-foreground hover:bg-muted"
                    }`}
                  >
                    {labels[mode]}
                  </button>
                );
              })}
            </div>
            <div className="flex items-center gap-2">
              {Object.keys(symbolSuggestions).length > 0 && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleBatchAdopt}
                  className="border-blue-500/50 text-blue-400 hover:bg-blue-500/10"
                >
                  <CheckCheck className="mr-1 h-3 w-3" />
                  批量采纳 ({Object.keys(symbolSuggestions).length})
                </Button>
              )}
              <Button
                variant="outline"
                size="sm"
                onClick={handleBatchSuggest}
                disabled={batchSuggesting || configuredSymbols.size === 0}
              >
                {batchSuggesting ? (
                  <>
                    <RefreshCw className="mr-1 h-3 w-3 animate-spin" />
                    AI 分析中...
                  </>
                ) : (
                  <>
                    <Sparkles className="mr-1 h-3 w-3" />
                    批量建议
                  </>
                )}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={enableRecommended}
                disabled={presets.length === 0}
              >
                <Star className="mr-1 h-3 w-3" />
                推荐
              </Button>
            </div>
          </div>

          {/* Symbol list */}
          <div className="flex flex-col gap-2">
            {filteredSymbols.map((symbol) => {
              const cfg = configuredSymbols.get(symbol);
              const isEnabled = !!cfg;
              const isExpanded = expandedSymbols.has(symbol);
              const displayName = symbol.replace(":USDT", "").replace("/USDT", "");
              const baseSymbol = displayName.split("/")[0] || displayName;

              return (
                <div
                  key={symbol}
                  className={`rounded-lg border overflow-hidden transition-colors ${
                    isEnabled
                      ? isExpanded
                        ? "border-primary/50 bg-primary/[0.03]"
                        : "border-primary/30 bg-primary/[0.03]"
                      : "border-border"
                  }`}
                >
                  {/* Symbol header row */}
                  <div
                    className="flex items-center justify-between px-4 py-2.5 cursor-pointer"
                    onClick={() => {
                      if (isEnabled) toggleExpand(symbol);
                    }}
                  >
                    <div className="flex items-center gap-2.5">
                      <span
                        className={`h-2 w-2 rounded-full ${
                          isEnabled ? "bg-green-500" : "bg-muted"
                        }`}
                      />
                      <span
                        className={`font-mono text-sm font-semibold ${
                          isEnabled ? "" : "text-muted-foreground"
                        }`}
                      >
                        {baseSymbol}
                      </span>
                      <span className="text-xs text-muted-foreground">/USDT</span>
                      {volumes[symbol] != null && volumes[symbol] > 0 && (
                        <span className="text-[10px] text-muted-foreground/70 font-mono">
                          {volumes[symbol] >= 1e9
                            ? `${(volumes[symbol] / 1e9).toFixed(1)}B`
                            : volumes[symbol] >= 1e6
                              ? `${(volumes[symbol] / 1e6).toFixed(0)}M`
                              : `${(volumes[symbol] / 1e3).toFixed(0)}K`}
                        </span>
                      )}
                      {cfg && (
                        <span
                          className={`text-[11px] px-2 py-0.5 rounded ${
                            hasOverrides(cfg)
                              ? "bg-yellow-500/15 text-yellow-400"
                              : "bg-primary/15 text-blue-400"
                          }`}
                        >
                          {cfg.preset_display_name}
                          {hasOverrides(cfg) && " \u00b7 已修改"}
                        </span>
                      )}
                      {symbolSuggestions[symbol] && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-500/15 text-blue-300">
                          AI: {symbolSuggestions[symbol].recommended_display_name}
                          {symbolSuggestions[symbol].recommended_preset !== cfg?.preset_name && " →"}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-3">
                      {isEnabled && (
                        <ChevronDown
                          className={`h-3.5 w-3.5 text-muted-foreground transition-transform ${
                            isExpanded ? "rotate-180" : ""
                          }`}
                        />
                      )}
                      <div onClick={(e) => e.stopPropagation()}>
                        <Switch
                          checked={isEnabled}
                          onCheckedChange={() => toggleSymbol(symbol)}
                        />
                      </div>
                    </div>
                  </div>

                  {/* Expanded panel */}
                  {isEnabled && isExpanded && cfg && (
                    <div
                      className="px-4 pb-4 border-t border-border/50"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {/* Preset selector */}
                      <div className="mt-3">
                        <div className="text-[11px] text-muted-foreground uppercase tracking-wider mb-2">
                          策略预设
                        </div>
                        <select
                          value={cfg.preset_name}
                          onChange={(e) => changePreset(symbol, e.target.value)}
                          className="w-full rounded-md border border-input bg-card px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary cursor-pointer"
                        >
                          {presets.map((p) => (
                            <option key={p.name} value={p.name}>
                              {p.displayName} — {p.description}
                            </option>
                          ))}
                        </select>

                        {/* Strategy tags */}
                        <div className="flex flex-wrap gap-1.5 mt-2">
                          {STRATEGY_KEYS.map((sk) => {
                            const active = cfg.preset_config[sk] === true;
                            return (
                              <span
                                key={sk}
                                className={`text-[11px] px-2 py-0.5 rounded ${
                                  active
                                    ? "bg-green-500/15 text-green-400"
                                    : "bg-muted text-muted-foreground"
                                }`}
                              >
                                {STRATEGY_LABELS[sk] || sk}
                              </span>
                            );
                          })}
                        </div>
                      </div>

                      {/* Params grid */}
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-3">
                        {/* Weights */}
                        <div>
                          <div className="text-xs font-semibold text-muted-foreground mb-2 pb-1 border-b border-border/50">
                            权重配置
                          </div>
                          {TUNABLE_PARAMS.weights.map((param) => {
                            const val = getEffectiveValue(cfg, param.key);
                            const modified = isParamModified(cfg, param.key);
                            const defaultVal = cfg.preset_config[param.key] ?? 0;
                            return (
                              <div
                                key={param.key}
                                className="flex items-center justify-between py-1.5"
                              >
                                <span className="text-xs text-muted-foreground">
                                  {param.label}
                                </span>
                                <div className="flex items-center gap-1.5">
                                  <input
                                    type="number"
                                    value={val}
                                    min={param.min}
                                    max={param.max}
                                    step={param.step}
                                    onChange={(e) =>
                                      updateParam(symbol, param.key, parseFloat(e.target.value) || 0)
                                    }
                                    className={`w-[72px] px-2 py-1 rounded border text-right font-mono text-xs bg-card text-foreground focus:outline-none focus:border-primary ${
                                      modified
                                        ? "border-yellow-500 bg-yellow-500/5"
                                        : "border-input"
                                    }`}
                                  />
                                  <span
                                    className={`text-[10px] w-16 ${
                                      modified ? "text-yellow-500" : "text-muted-foreground/50"
                                    }`}
                                  >
                                    默认 {Number(defaultVal).toFixed(2)}
                                  </span>
                                </div>
                              </div>
                            );
                          })}
                        </div>

                        {/* Risk */}
                        <div>
                          <div className="text-xs font-semibold text-muted-foreground mb-2 pb-1 border-b border-border/50">
                            风控参数
                          </div>
                          {TUNABLE_PARAMS.risk.map((param) => {
                            const val = getEffectiveValue(cfg, param.key);
                            const modified = isParamModified(cfg, param.key);
                            const defaultVal = cfg.preset_config[param.key] ?? 0;
                            return (
                              <div
                                key={param.key}
                                className="flex items-center justify-between py-1.5"
                              >
                                <span className="text-xs text-muted-foreground">
                                  {param.label}
                                </span>
                                <div className="flex items-center gap-1.5">
                                  <input
                                    type="number"
                                    value={val}
                                    min={param.min}
                                    max={param.max}
                                    step={param.step}
                                    onChange={(e) =>
                                      updateParam(symbol, param.key, parseFloat(e.target.value) || 0)
                                    }
                                    className={`w-[72px] px-2 py-1 rounded border text-right font-mono text-xs bg-card text-foreground focus:outline-none focus:border-primary ${
                                      modified
                                        ? "border-yellow-500 bg-yellow-500/5"
                                        : "border-input"
                                    }`}
                                  />
                                  <span
                                    className={`text-[10px] w-16 ${
                                      modified ? "text-yellow-500" : "text-muted-foreground/50"
                                    }`}
                                  >
                                    默认 {Number(defaultVal).toFixed(2)}
                                  </span>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>

                      {/* Panel footer */}
                      <div className="flex justify-end mt-4 pt-3 border-t border-border/50">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => resetOverrides(symbol)}
                          disabled={!hasOverrides(cfg)}
                        >
                          <RotateCcw className="mr-1 h-3 w-3" />
                          重置为预设默认
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {filteredSymbols.length === 0 && (
            <div className="text-center text-sm text-muted-foreground py-8">
              没有匹配的交易对
            </div>
          )}
        </CardContent>
      </Card>

      {/* Fixed save bar */}
      {hasChanges && (
        <div className="fixed bottom-0 left-0 right-0 bg-card border-t border-border px-8 py-3 flex justify-end items-center gap-3 z-50">
          <span className="text-xs text-muted-foreground">
            {configuredSymbols.size} 个交易对已配置策略
          </span>
          <Button onClick={saveSymbols} disabled={saving}>
            {saving ? (
              <>
                <RefreshCw className="mr-1 h-3 w-3 animate-spin" />
                保存中...
              </>
            ) : (
              <>
                <Save className="mr-1 h-3 w-3" />
                保存所有更改
              </>
            )}
          </Button>
        </div>
      )}
    </div>
  );
}
