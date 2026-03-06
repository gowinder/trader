import postgres from "postgres";

function getDb() {
  const dbUrl = process.env.DATABASE_URL;
  if (!dbUrl) return null;
  return postgres(dbUrl);
}

// 系统预设模板 - 与 Python 后端 presets.py 保持一致
const SYSTEM_PRESETS = [
  {
    name: "steady_trend",
    display_name: "稳健趋势",
    description: "跟随明确趋势，低频交易，严格风控",
    category: "trend",
    risk_level: "low",
    config_json: {
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
  },
  {
    name: "aggressive_trend",
    display_name: "激进趋势",
    description: "强趋势市场积极跟进，允许加仓放大收益",
    category: "trend",
    risk_level: "medium_high",
    config_json: {
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
  },
  {
    name: "range_harvest",
    display_name: "震荡收割",
    description: "区间震荡市场高抛低吸，均值回归为主",
    category: "range",
    risk_level: "medium",
    config_json: {
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
  },
  {
    name: "breakout_hunter",
    display_name: "突破猎手",
    description: "捕捉盘整后的突破行情，配合趋势确认",
    category: "breakout",
    risk_level: "medium",
    config_json: {
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
  },
  {
    name: "mild_scalping",
    display_name: "温和剥头皮",
    description: "中频小利润交易，均值回归主导，适合震荡和趋势市",
    category: "scalping",
    risk_level: "medium_low",
    config_json: {
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
  },
  {
    name: "aggressive_scalping",
    display_name: "激进剥头皮",
    description: "高频快进快出，几乎纯量化驱动，薄利多销",
    category: "scalping",
    risk_level: "medium",
    config_json: {
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
  },
  {
    name: "balanced_conservative",
    display_name: "均衡保守",
    description: "AI主导决策，低仓位低频率，适合不确定市场",
    category: "balanced",
    risk_level: "lowest",
    config_json: {
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
  },
];

async function ensureSystemPresets(sql: postgres.Sql) {
  const count = await sql`SELECT COUNT(*) as cnt FROM strategy_presets`;
  if (Number(count[0].cnt) > 0) return;

  for (const preset of SYSTEM_PRESETS) {
    await sql`
      INSERT INTO strategy_presets (name, display_name, description, category, risk_level, config_json, is_system)
      VALUES (${preset.name}, ${preset.display_name}, ${preset.description},
              ${preset.category}, ${preset.risk_level}, ${JSON.stringify(preset.config_json)}, true)
      ON CONFLICT (name) DO NOTHING
    `;
  }

  // 激活默认策略 (steady_trend)
  const defaultPreset = await sql`SELECT id FROM strategy_presets WHERE name = 'steady_trend'`;
  if (defaultPreset.length > 0) {
    const activeCount = await sql`SELECT COUNT(*) as cnt FROM active_strategy WHERE deactivated_at IS NULL`;
    if (Number(activeCount[0].cnt) === 0) {
      await sql`INSERT INTO active_strategy (preset_id) VALUES (${defaultPreset[0].id})`;
    }
  }
}

export async function loader() {
  const sql = getDb();
  if (!sql) {
    return Response.json({ presets: [], activePresetId: null, activatedAt: null, isLocked: false });
  }

  try {
    // 确保系统预设已初始化
    await ensureSystemPresets(sql);

    // 获取所有预设
    const presets = await sql`
      SELECT id, name, display_name, description, category, risk_level, config_json, is_system
      FROM strategy_presets
      ORDER BY id
    `;

    // 获取当前活跃策略
    const activeRows = await sql`
      SELECT preset_id, activated_at, COALESCE(is_locked, false) as is_locked
      FROM active_strategy
      WHERE deactivated_at IS NULL
      ORDER BY activated_at DESC
      LIMIT 1
    `;

    const activePresetId = activeRows.length > 0 ? Number(activeRows[0].preset_id) : null;
    const activatedAt = activeRows.length > 0 ? activeRows[0].activated_at : null;
    const isLocked = activeRows.length > 0 ? activeRows[0].is_locked === true : false;

    // 为每个预设获取统计数据
    const presetsWithStats = await Promise.all(
      presets.map(async (p) => {
        const presetId = Number(p.id);

        // 获取该预设所有激活时段
        const activations = await sql`
          SELECT activated_at, deactivated_at
          FROM active_strategy
          WHERE preset_id = ${presetId}
          ORDER BY activated_at
        `;

        let totalTrades = 0;
        let totalPnl = 0;
        let wins = 0;

        for (const act of activations) {
          const start = act.activated_at;
          const end = act.deactivated_at || new Date();

          const stats = await sql`
            SELECT
              COUNT(*) as trade_count,
              COALESCE(SUM(realized_pnl), 0) as total_pnl,
              COUNT(*) FILTER (WHERE realized_pnl > 0) as win_count
            FROM position_history
            WHERE exit_time BETWEEN ${start} AND ${end}
          `;

          if (stats.length > 0) {
            totalTrades += Number(stats[0].trade_count);
            totalPnl += Number(stats[0].total_pnl);
            wins += Number(stats[0].win_count);
          }
        }

        const winRate = totalTrades > 0 ? Math.round((wins / totalTrades) * 1000) / 10 : 0;

        return {
          id: presetId,
          name: p.name,
          displayName: p.display_name,
          description: p.description,
          category: p.category,
          riskLevel: p.risk_level,
          configJson: typeof p.config_json === "string" ? JSON.parse(p.config_json) : p.config_json,
          isSystem: p.is_system,
          stats: {
            totalTrades,
            totalPnl: Math.round(totalPnl * 100) / 100,
            winRate,
          },
        };
      })
    );

    return Response.json({
      presets: presetsWithStats,
      activePresetId,
      activatedAt,
      isLocked,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    console.error("Failed to load strategy presets:", message);
    return Response.json({ presets: [], activePresetId: null, activatedAt: null, isLocked: false });
  }
}
