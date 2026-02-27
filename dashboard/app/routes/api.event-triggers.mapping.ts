import type { LoaderFunctionArgs } from "react-router";

// 底层策略 → 事件映射（与 Python 端 src/ai_trader/events/config.py 同步）
const STRATEGY_EVENT_DEFAULTS: Record<string, string[]> = {
  trend_following: ["price_surge", "macd_cross", "market_state_change", "position_pnl"],
  mean_reversion: ["price_surge", "rsi_extreme", "bollinger_break", "market_state_change", "position_pnl"],
  breakout: ["price_surge", "volume_spike", "bollinger_break", "market_state_change", "position_pnl"],
};

// 预设 → 启用的底层策略（与 Python 端 src/ai_trader/strategies/presets.py 同步）
const PRESET_DEFINITIONS: {
  name: string;
  displayName: string;
  enabledStrategies: string[];
}[] = [
  { name: "steady_trend", displayName: "稳健趋势", enabledStrategies: ["trend_following"] },
  { name: "aggressive_trend", displayName: "激进趋势", enabledStrategies: ["trend_following", "breakout"] },
  { name: "range_harvest", displayName: "震荡收割", enabledStrategies: ["mean_reversion", "trend_following"] },
  { name: "breakout_hunter", displayName: "突破猎手", enabledStrategies: ["breakout", "trend_following"] },
  { name: "mild_scalping", displayName: "温和剥头皮", enabledStrategies: ["mean_reversion", "trend_following"] },
  { name: "aggressive_scalping", displayName: "激进剥头皮", enabledStrategies: ["mean_reversion", "trend_following", "breakout"] },
  { name: "balanced_conservative", displayName: "均衡保守", enabledStrategies: ["trend_following", "mean_reversion", "breakout"] },
];

const ALL_EVENT_TYPES = [
  "price_surge",
  "volume_spike",
  "rsi_extreme",
  "macd_cross",
  "bollinger_break",
  "market_state_change",
  "position_pnl",
];

// 计算每个预设关注的事件（其 enabledStrategies 的事件并集）
function computePresetMapping() {
  const mapping: Record<string, { displayName: string; events: string[] }> = {};
  for (const preset of PRESET_DEFINITIONS) {
    const events = new Set<string>();
    for (const strategy of preset.enabledStrategies) {
      for (const event of STRATEGY_EVENT_DEFAULTS[strategy] || []) {
        events.add(event);
      }
    }
    mapping[preset.name] = {
      displayName: preset.displayName,
      events: Array.from(events),
    };
  }
  return mapping;
}

export async function loader(_args: LoaderFunctionArgs) {
  return Response.json({
    presetMapping: computePresetMapping(),
    allEventTypes: ALL_EVENT_TYPES,
  });
}
