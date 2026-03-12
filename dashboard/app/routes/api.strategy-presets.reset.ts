import postgres from "postgres";
import { createClient } from "redis";

function getDb() {
  const dbUrl = process.env.DATABASE_URL;
  if (!dbUrl) return null;
  return postgres(dbUrl);
}

async function getRedisClient() {
  const redisUrl = process.env.REDIS_URL || "redis://localhost:6379";
  const client = createClient({ url: redisUrl });
  await client.connect();
  return client;
}

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

// POST: reset a system preset to its default config
export async function action({ request }: { request: Request }) {
  if (request.method !== "POST") {
    return Response.json({ error: "Method not allowed" }, { status: 405 });
  }

  const sql = getDb();
  if (!sql) {
    return Response.json({ error: "Database not configured" }, { status: 500 });
  }

  try {
    const body = await request.json();
    const { presetId } = body;

    if (!presetId) {
      return Response.json({ error: "presetId is required" }, { status: 400 });
    }

    // Check global strategy lock
    const lockCheck = await sql`
      SELECT COALESCE(is_locked, false) as is_locked
      FROM active_strategy WHERE deactivated_at IS NULL
      ORDER BY activated_at DESC LIMIT 1
    `;
    if (lockCheck.length > 0 && lockCheck[0].is_locked) {
      return Response.json({ error: "策略已锁定，请先解锁再修改" }, { status: 423 });
    }

    // Verify it's a modified system preset
    const preset = await sql`
      SELECT id, name, is_system, COALESCE(is_modified, false) as is_modified
      FROM strategy_presets WHERE id = ${presetId}
    `;
    if (preset.length === 0) {
      return Response.json({ error: "Preset not found" }, { status: 404 });
    }
    if (!preset[0].is_system) {
      return Response.json({ error: "Can only reset system presets" }, { status: 400 });
    }
    if (!preset[0].is_modified) {
      return Response.json({ error: "Preset is not modified" }, { status: 400 });
    }

    const defaultConfig = SYSTEM_DEFAULTS[preset[0].name];
    if (!defaultConfig) {
      return Response.json({ error: "Default config not found" }, { status: 500 });
    }

    // Reset config and clear modified flag
    await sql`
      UPDATE strategy_presets
      SET config_json = ${JSON.stringify(defaultConfig)}, is_modified = false, updated_at = NOW()
      WHERE id = ${presetId}
    `;

    // If active, notify backend
    const active = await sql`
      SELECT preset_id FROM active_strategy
      WHERE deactivated_at IS NULL AND preset_id = ${presetId}
      LIMIT 1
    `;
    if (active.length > 0) {
      try {
        const redisClient = await getRedisClient();
        const payload = JSON.stringify({
          preset_id: presetId,
          name: preset[0].name,
          config: defaultConfig,
        });
        await redisClient.set("strategy:active_preset", payload);
        await redisClient.publish("strategy:preset:updated", payload);
        await redisClient.disconnect();
      } catch (redisErr) {
        console.error("Redis update failed (non-fatal):", redisErr);
      }
    }

    return Response.json({ success: true, presetId, config: defaultConfig });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    console.error("Failed to reset preset:", message);
    return Response.json({ error: message }, { status: 500 });
  }
}
