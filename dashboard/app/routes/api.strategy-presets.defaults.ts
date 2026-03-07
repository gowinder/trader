import type { LoaderFunctionArgs } from "react-router";

// System preset defaults (must match presets.py)
const SYSTEM_DEFAULTS: Record<string, object> = {
  steady_trend: {
    enabled_strategies: ["trend_following"],
    strategy_weights: { trend_following: 1.0 },
    ai_weight: 0.6, quant_weight: 0.4, sentiment_weight: 0.2,
    timeframes: ["1h", "4h"],
    min_trade_interval_seconds: 21600,
    stop_loss_atr_multiplier: 3.0, take_profit_atr_multiplier: 8.0,
    max_position_pct: 15.0,
    enable_pyramid: false, max_pyramid_times: 0,
    enable_sentiment: true, min_profit_threshold: 0, use_market_order_only: false,
  },
  aggressive_trend: {
    enabled_strategies: ["trend_following", "breakout"],
    strategy_weights: { trend_following: 0.7, breakout: 0.3 },
    ai_weight: 0.4, quant_weight: 0.6, sentiment_weight: 0,
    timeframes: ["15m", "1h"],
    min_trade_interval_seconds: 7200,
    stop_loss_atr_multiplier: 2.0, take_profit_atr_multiplier: 5.0,
    max_position_pct: 30.0,
    enable_pyramid: true, max_pyramid_times: 2,
    enable_sentiment: false, min_profit_threshold: 0, use_market_order_only: false,
  },
  range_harvest: {
    enabled_strategies: ["mean_reversion", "trend_following"],
    strategy_weights: { mean_reversion: 0.8, trend_following: 0.2 },
    ai_weight: 0.3, quant_weight: 0.7, sentiment_weight: 0.2,
    timeframes: ["15m", "1h"],
    min_trade_interval_seconds: 7200,
    stop_loss_atr_multiplier: 2.0, take_profit_atr_multiplier: 3.0,
    max_position_pct: 20.0,
    enable_pyramid: false, max_pyramid_times: 0,
    enable_sentiment: true, min_profit_threshold: 0, use_market_order_only: false,
  },
  breakout_hunter: {
    enabled_strategies: ["breakout", "trend_following"],
    strategy_weights: { breakout: 0.8, trend_following: 0.2 },
    ai_weight: 0.4, quant_weight: 0.6, sentiment_weight: 0.2,
    timeframes: ["1h", "4h"],
    min_trade_interval_seconds: 14400,
    stop_loss_atr_multiplier: 2.5, take_profit_atr_multiplier: 6.0,
    max_position_pct: 25.0,
    enable_pyramid: true, max_pyramid_times: 1,
    enable_sentiment: true, min_profit_threshold: 0, use_market_order_only: false,
  },
  mild_scalping: {
    enabled_strategies: ["mean_reversion", "trend_following"],
    strategy_weights: { mean_reversion: 0.6, trend_following: 0.4 },
    ai_weight: 0.25, quant_weight: 0.75, sentiment_weight: 0,
    timeframes: ["5m", "15m"],
    min_trade_interval_seconds: 900,
    stop_loss_atr_multiplier: 1.5, take_profit_atr_multiplier: 2.0,
    max_position_pct: 10.0,
    enable_pyramid: false, max_pyramid_times: 0,
    enable_sentiment: false, min_profit_threshold: 0.15, use_market_order_only: false,
  },
  aggressive_scalping: {
    enabled_strategies: ["mean_reversion", "trend_following", "breakout"],
    strategy_weights: { mean_reversion: 0.5, trend_following: 0.3, breakout: 0.2 },
    ai_weight: 0.1, quant_weight: 0.9, sentiment_weight: 0,
    timeframes: ["1m", "5m"],
    min_trade_interval_seconds: 300,
    stop_loss_atr_multiplier: 1.0, take_profit_atr_multiplier: 1.5,
    max_position_pct: 8.0,
    enable_pyramid: false, max_pyramid_times: 0,
    enable_sentiment: false, min_profit_threshold: 0.1, use_market_order_only: true,
  },
  balanced_conservative: {
    enabled_strategies: ["trend_following", "mean_reversion", "breakout"],
    strategy_weights: { trend_following: 0.5, mean_reversion: 0.3, breakout: 0.2 },
    ai_weight: 0.7, quant_weight: 0.3, sentiment_weight: 0.2,
    timeframes: ["4h", "1d"],
    min_trade_interval_seconds: 43200,
    stop_loss_atr_multiplier: 4.0, take_profit_atr_multiplier: 6.0,
    max_position_pct: 10.0,
    enable_pyramid: false, max_pyramid_times: 0,
    enable_sentiment: true, min_profit_threshold: 0, use_market_order_only: false,
  },
};

// GET: return all system preset default configs
export async function loader(_args: LoaderFunctionArgs) {
  return Response.json({ defaults: SYSTEM_DEFAULTS });
}
