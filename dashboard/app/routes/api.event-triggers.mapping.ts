import type { LoaderFunctionArgs } from "react-router";

// 注意：此映射必须与 Python 端 src/ai_trader/events/config.py 中的
// STRATEGY_EVENT_DEFAULTS 保持同步。修改任一端时需同步更新另一端。
const STRATEGY_EVENT_DEFAULTS: Record<string, string[]> = {
  trend_following: ["price_surge", "macd_cross", "market_state_change", "position_pnl"],
  mean_reversion: ["price_surge", "rsi_extreme", "bollinger_break", "market_state_change", "position_pnl"],
  breakout: ["price_surge", "volume_spike", "bollinger_break", "market_state_change", "position_pnl"],
};

const ALL_EVENT_TYPES = [
  "price_surge",
  "volume_spike",
  "rsi_extreme",
  "macd_cross",
  "bollinger_break",
  "market_state_change",
  "position_pnl",
];

export async function loader(_args: LoaderFunctionArgs) {
  return Response.json({
    mapping: STRATEGY_EVENT_DEFAULTS,
    allEventTypes: ALL_EVENT_TYPES,
  });
}
