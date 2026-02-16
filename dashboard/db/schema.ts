import {
  pgTable,
  uuid,
  varchar,
  text,
  timestamp,
  smallint,
  decimal,
  integer,
  boolean,
  jsonb,
  date,
  primaryKey,
  index,
  uniqueIndex,
} from "drizzle-orm/pg-core";
import { relations } from "drizzle-orm";

// ==================== 决策相关 ====================

export const decisions = pgTable(
  "decisions",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),

    // 基础信息
    symbol: varchar("symbol", { length: 20 }).notNull(),
    timeframe: varchar("timeframe", { length: 10 }).notNull(),

    // 决策结果
    action: varchar("action", { length: 20 }).notNull(),
    confidence: smallint("confidence").notNull(),
    leverage: decimal("leverage", { precision: 4, scale: 1 }),
    positionSizePct: decimal("position_size_pct", { precision: 5, scale: 2 }),
    entryPrice: decimal("entry_price", { precision: 20, scale: 8 }),
    stopLoss: decimal("stop_loss", { precision: 20, scale: 8 }),
    takeProfit: decimal("take_profit", { precision: 20, scale: 8 }),
    reasoning: text("reasoning"),
    reasoningZh: text("reasoning_zh"),

    // LLM 原始输出
    llmProvider: varchar("llm_provider", { length: 30 }),
    llmModel: varchar("llm_model", { length: 50 }),
    llmRawOutput: text("llm_raw_output"),
    llmTokensUsed: integer("llm_tokens_used"),

    // 策略预设
    strategyPreset: varchar("strategy_preset", { length: 50 }),

    // 量化策略信号 (用于权重优化反馈闭环)
    marketState: varchar("market_state", { length: 30 }),
    strategySignals: jsonb("strategy_signals"),

    // 决策质量评分 (0-100)
    qualityScore: smallint("quality_score"),

    // 关联
    orderId: uuid("order_id").references(() => orders.id),
  },
  (table) => ({
    symbolTimeIdx: index("idx_decisions_symbol_time").on(table.symbol, table.createdAt),
  })
);

export const technicalSnapshots = pgTable("technical_snapshots", {
  id: uuid("id").primaryKey().defaultRandom(),
  decisionId: uuid("decision_id")
    .notNull()
    .references(() => decisions.id, { onDelete: "cascade" }),

  // 趋势
  trend: varchar("trend", { length: 20 }),
  trendConfidence: smallint("trend_confidence"),
  signalStrength: varchar("signal_strength", { length: 20 }),

  // 指标
  price: decimal("price", { precision: 20, scale: 8 }),
  rsi: decimal("rsi", { precision: 6, scale: 2 }),
  macd: decimal("macd", { precision: 20, scale: 8 }),
  macdSignal: decimal("macd_signal", { precision: 20, scale: 8 }),
  ma7: decimal("ma7", { precision: 20, scale: 8 }),
  ma25: decimal("ma25", { precision: 20, scale: 8 }),
  ma99: decimal("ma99", { precision: 20, scale: 8 }),
  atr: decimal("atr", { precision: 20, scale: 8 }),
  bollUpper: decimal("boll_upper", { precision: 20, scale: 8 }),
  bollLower: decimal("boll_lower", { precision: 20, scale: 8 }),

  // 支撑阻力
  supportLevels: jsonb("support_levels"),
  resistanceLevels: jsonb("resistance_levels"),

  // 其他
  volumeTrend: varchar("volume_trend", { length: 20 }),
  pattern: varchar("pattern", { length: 50 }),
  keyObservations: jsonb("key_observations"),
});

export const riskSnapshots = pgTable("risk_snapshots", {
  id: uuid("id").primaryKey().defaultRandom(),
  decisionId: uuid("decision_id")
    .notNull()
    .references(() => decisions.id, { onDelete: "cascade" }),

  riskLevel: varchar("risk_level", { length: 20 }),
  riskScore: smallint("risk_score"),
  recommendedLeverage: decimal("recommended_leverage", { precision: 4, scale: 1 }),
  recommendedPositionPct: decimal("recommended_position_pct", { precision: 5, scale: 2 }),
  shouldTrade: boolean("should_trade"),
  riskFactors: jsonb("risk_factors"),
  mitigationSuggestions: jsonb("mitigation_suggestions"),
});

export const sentimentSnapshots = pgTable("sentiment_snapshots", {
  id: uuid("id").primaryKey().defaultRandom(),
  decisionId: uuid("decision_id")
    .notNull()
    .references(() => decisions.id, { onDelete: "cascade" }),

  overallScore: decimal("overall_score", { precision: 4, scale: 2 }),
  newsCount: integer("news_count"),
  bullishCount: integer("bullish_count"),
  bearishCount: integer("bearish_count"),
  topNews: jsonb("top_news"),
  dataSource: varchar("data_source", { length: 30 }),
});

// ==================== 订单与仓位 ====================

export const orders = pgTable(
  "orders",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),

    symbol: varchar("symbol", { length: 20 }).notNull(),
    exchangeOrderId: varchar("exchange_order_id", { length: 50 }),
    side: varchar("side", { length: 20 }).notNull(),
    orderType: varchar("order_type", { length: 10 }).notNull(),

    price: decimal("price", { precision: 20, scale: 8 }),
    size: decimal("size", { precision: 20, scale: 8 }).notNull(),
    filledPrice: decimal("filled_price", { precision: 20, scale: 8 }),
    filledSize: decimal("filled_size", { precision: 20, scale: 8 }),
    fee: decimal("fee", { precision: 20, scale: 8 }),

    status: varchar("status", { length: 20 }).notNull(),
    closedAt: timestamp("closed_at", { withTimezone: true }),
  },
  (table) => ({
    symbolTimeIdx: index("idx_orders_symbol_time").on(table.symbol, table.createdAt),
  })
);

export const positionHistory = pgTable(
  "position_history",
  {
    id: uuid("id").primaryKey().defaultRandom(),

    symbol: varchar("symbol", { length: 20 }).notNull(),
    side: varchar("side", { length: 10 }).notNull(),

    // 入场
    entryTime: timestamp("entry_time", { withTimezone: true }).notNull(),
    entryPrice: decimal("entry_price", { precision: 20, scale: 8 }).notNull(),
    entrySize: decimal("entry_size", { precision: 20, scale: 8 }).notNull(),
    leverage: decimal("leverage", { precision: 4, scale: 1 }),

    // 出场
    exitTime: timestamp("exit_time", { withTimezone: true }),
    exitPrice: decimal("exit_price", { precision: 20, scale: 8 }),

    // 盈亏
    realizedPnl: decimal("realized_pnl", { precision: 20, scale: 8 }),
    pnlPercent: decimal("pnl_percent", { precision: 8, scale: 4 }),
    feeTotal: decimal("fee_total", { precision: 20, scale: 8 }),

    // 关联决策
    entryDecisionId: uuid("entry_decision_id").references(() => decisions.id),
    exitDecisionId: uuid("exit_decision_id").references(() => decisions.id),

    status: varchar("status", { length: 20 }).notNull(),
  },
  (table) => ({
    symbolIdx: index("idx_positions_symbol").on(table.symbol, table.entryTime),
  })
);

export const dailyStats = pgTable(
  "daily_stats",
  {
    date: date("date").notNull(),
    symbol: varchar("symbol", { length: 20 }).notNull(),

    totalTrades: integer("total_trades").default(0),
    winningTrades: integer("winning_trades").default(0),
    losingTrades: integer("losing_trades").default(0),

    totalPnl: decimal("total_pnl", { precision: 20, scale: 8 }).default("0"),
    maxDrawdown: decimal("max_drawdown", { precision: 8, scale: 4 }),
  },
  (table) => ({
    pk: primaryKey({ columns: [table.date, table.symbol] }),
  })
);

// ==================== 回测 ====================

export const backtests = pgTable("backtests", {
  id: uuid("id").primaryKey().defaultRandom(),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),

  // 模式
  mode: varchar("mode", { length: 20 }).notNull(),

  // 单币种参数
  symbol: varchar("symbol", { length: 20 }),

  // 组合参数
  symbolsConfig: jsonb("symbols_config"),
  portfolioParams: jsonb("portfolio_params"),

  // 通用参数
  startDate: date("start_date").notNull(),
  endDate: date("end_date").notNull(),
  initialCapital: decimal("initial_capital", { precision: 20, scale: 2 }).notNull(),
  leverage: decimal("leverage", { precision: 4, scale: 1 }),
  strategyMode: varchar("strategy_mode", { length: 20 }),
  params: jsonb("params"),

  // 状态
  status: varchar("status", { length: 20 }).notNull(),
  progress: smallint("progress").default(0),
  errorMessage: text("error_message"),

  // 结果
  finalCapital: decimal("final_capital", { precision: 20, scale: 2 }),
  totalPnl: decimal("total_pnl", { precision: 20, scale: 2 }),
  totalTrades: integer("total_trades"),
  winningTrades: integer("winning_trades"),
  maxDrawdown: decimal("max_drawdown", { precision: 8, scale: 4 }),
  sharpeRatio: decimal("sharpe_ratio", { precision: 8, scale: 4 }),

  // 组合各币种结果
  symbolResults: jsonb("symbol_results"),

  completedAt: timestamp("completed_at", { withTimezone: true }),
});

export const backtestTrades = pgTable("backtest_trades", {
  id: uuid("id").primaryKey().defaultRandom(),
  backtestId: uuid("backtest_id")
    .notNull()
    .references(() => backtests.id, { onDelete: "cascade" }),

  symbol: varchar("symbol", { length: 20 }).notNull(),
  entryTime: timestamp("entry_time", { withTimezone: true }).notNull(),
  exitTime: timestamp("exit_time", { withTimezone: true }),
  side: varchar("side", { length: 10 }).notNull(),
  entryPrice: decimal("entry_price", { precision: 20, scale: 8 }).notNull(),
  exitPrice: decimal("exit_price", { precision: 20, scale: 8 }),
  size: decimal("size", { precision: 20, scale: 8 }).notNull(),
  pnl: decimal("pnl", { precision: 20, scale: 8 }),
  pnlPercent: decimal("pnl_percent", { precision: 8, scale: 4 }),

  decisionSnapshot: jsonb("decision_snapshot"),
});

export const backtestEquity = pgTable(
  "backtest_equity",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    backtestId: uuid("backtest_id")
      .notNull()
      .references(() => backtests.id, { onDelete: "cascade" }),

    timestamp: timestamp("timestamp", { withTimezone: true }).notNull(),
    totalEquity: decimal("total_equity", { precision: 20, scale: 2 }).notNull(),
    symbolEquity: jsonb("symbol_equity"),
  },
  (table) => ({
    backtestTimeIdx: index("idx_equity_backtest_time").on(table.backtestId, table.timestamp),
  })
);

// ==================== 回测调度配置 ====================

export const backtestScheduleConfig = pgTable("backtest_schedule_config", {
  id: uuid("id").primaryKey().defaultRandom(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),

  // 启用状态
  enabled: boolean("enabled").notNull().default(false),

  // 调度配置
  scheduleType: varchar("schedule_type", { length: 20 }).notNull().default("manual"),  // manual, daily, weekly
  scheduleCron: varchar("schedule_cron", { length: 50 }),  // cron 表达式 (可选)
  scheduleHour: smallint("schedule_hour").default(0),  // 每日执行小时 (0-23)
  scheduleDayOfWeek: smallint("schedule_day_of_week"),  // 每周执行日 (0-6, 0=周日)

  // 回测参数
  symbols: jsonb("symbols").notNull().default(["BTCUSDT"]),  // 交易对列表
  timeframe: varchar("timeframe", { length: 10 }).notNull().default("1h"),
  lookbackDays: smallint("lookback_days").notNull().default(30),  // 回测天数
  initialCapital: decimal("initial_capital", { precision: 20, scale: 2 }).notNull().default("10000"),

  // 策略配置
  enableFilters: boolean("enable_filters").notNull().default(true),
  strategies: jsonb("strategies").notNull().default(["trend_following"]),
});

// ==================== 相关性分析 ====================

export const correlationCache = pgTable(
  "correlation_cache",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    calculatedAt: timestamp("calculated_at", { withTimezone: true }).notNull().defaultNow(),

    symbolA: varchar("symbol_a", { length: 20 }).notNull(),
    symbolB: varchar("symbol_b", { length: 20 }).notNull(),
    timeframe: varchar("timeframe", { length: 10 }).notNull(),

    correlation: decimal("correlation", { precision: 5, scale: 4 }).notNull(),
    sampleSize: integer("sample_size").notNull(),
  },
  (table) => ({
    uniqueIdx: uniqueIndex("correlation_unique_idx").on(table.symbolA, table.symbolB, table.timeframe),
  })
);

export const priceHistory = pgTable(
  "price_history",
  {
    symbol: varchar("symbol", { length: 20 }).notNull(),
    timestamp: timestamp("timestamp", { withTimezone: true }).notNull(),
    closePrice: decimal("close_price", { precision: 20, scale: 8 }).notNull(),
  },
  (table) => ({
    pk: primaryKey({ columns: [table.symbol, table.timestamp] }),
  })
);

// ==================== 告警系统 ====================

export const alertSettings = pgTable("alert_settings", {
  id: uuid("id").primaryKey().defaultRandom(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),

  channels: jsonb("channels").notNull().default({}),
  rules: jsonb("rules").notNull().default({}),
  priceAlerts: jsonb("price_alerts").notNull().default([]),
  quietHours: jsonb("quiet_hours"),
});

export const alertHistory = pgTable(
  "alert_history",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),

    level: varchar("level", { length: 10 }).notNull(),
    category: varchar("category", { length: 20 }).notNull(),
    title: varchar("title", { length: 100 }).notNull(),
    message: text("message").notNull(),

    symbol: varchar("symbol", { length: 20 }),
    decisionId: uuid("decision_id").references(() => decisions.id),
    orderId: uuid("order_id").references(() => orders.id),

    channelsSent: jsonb("channels_sent"),
  },
  (table) => ({
    timeIdx: index("idx_alerts_time").on(table.createdAt),
    levelIdx: index("idx_alerts_level").on(table.level, table.createdAt),
  })
);

// ==================== LLM 使用记录 ====================

export const llmUsage = pgTable(
  "llm_usage",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),

    provider: varchar("provider", { length: 30 }).notNull(),
    model: varchar("model", { length: 100 }).notNull(),
    inputTokens: integer("input_tokens").default(0),
    outputTokens: integer("output_tokens").default(0),
    totalTokens: integer("total_tokens").default(0),
    costUsd: decimal("cost_usd", { precision: 12, scale: 8 }).default("0"),
    latencyMs: integer("latency_ms").default(0),
    success: boolean("success").default(true),
    errorMessage: text("error_message"),

    // 关联上下文（可选）
    decisionId: uuid("decision_id").references(() => decisions.id),
  },
  (table) => ({
    timeIdx: index("idx_llm_usage_time").on(table.createdAt),
    providerIdx: index("idx_llm_usage_provider").on(table.provider),
  })
);

// ==================== 系统管理 ====================

export const operationLogs = pgTable("operation_logs", {
  id: uuid("id").primaryKey().defaultRandom(),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),

  action: varchar("action", { length: 50 }).notNull(),
  operator: varchar("operator", { length: 50 }),
  details: jsonb("details"),
  ipAddress: varchar("ip_address", { length: 50 }),
});

// ==================== 策略预设 ====================

export const strategyPresets = pgTable(
  "strategy_presets",
  {
    id: integer("id").primaryKey().generatedAlwaysAsIdentity(),
    name: varchar("name", { length: 50 }).unique().notNull(),
    displayName: varchar("display_name", { length: 100 }).notNull(),
    description: text("description"),
    category: varchar("category", { length: 20 }).notNull(),
    riskLevel: varchar("risk_level", { length: 20 }).notNull(),
    configJson: jsonb("config_json").notNull(),
    isSystem: boolean("is_system").default(true).notNull(),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
    updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => ({
    nameIdx: uniqueIndex("idx_strategy_presets_name").on(table.name),
  })
);

export const activeStrategy = pgTable(
  "active_strategy",
  {
    id: integer("id").primaryKey().generatedAlwaysAsIdentity(),
    presetId: integer("preset_id")
      .references(() => strategyPresets.id)
      .notNull(),
    activatedAt: timestamp("activated_at", { withTimezone: true }).notNull().defaultNow(),
    deactivatedAt: timestamp("deactivated_at", { withTimezone: true }),
  },
  (table) => ({
    activeIdx: index("idx_active_strategy_active").on(table.deactivatedAt),
  })
);

// ==================== AI Advisory ====================

export const advisories = pgTable(
  "advisories",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),

    triggerType: varchar("trigger_type", { length: 30 }).notNull(),
    triggerDetail: jsonb("trigger_detail"),
    urgency: varchar("urgency", { length: 10 }).notNull(),
    marketSummary: text("market_summary"),
    status: varchar("status", { length: 20 }).notNull().default("pending"),

    llmProvider: varchar("llm_provider", { length: 30 }),
    llmModel: varchar("llm_model", { length: 100 }),
    tokensUsed: integer("tokens_used"),

    resolvedAt: timestamp("resolved_at", { withTimezone: true }),
  },
  (table) => ({
    timeIdx: index("idx_advisories_time").on(table.createdAt),
    statusIdx: index("idx_advisories_status").on(table.status),
  })
);

export const advisorySuggestions = pgTable(
  "advisory_suggestions",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    advisoryId: uuid("advisory_id")
      .notNull()
      .references(() => advisories.id, { onDelete: "cascade" }),

    sortOrder: integer("sort_order").notNull().default(0),
    type: varchar("type", { length: 20 }).notNull(),
    target: varchar("target", { length: 30 }).notNull(),
    action: varchar("action", { length: 50 }).notNull(),
    detail: jsonb("detail"),
    reasoning: text("reasoning"),
    riskNote: text("risk_note"),

    status: varchar("status", { length: 20 }).notNull().default("pending"),
    executionResult: jsonb("execution_result"),
    rejectionReason: text("rejection_reason"),

    updatedAt: timestamp("updated_at", { withTimezone: true }),
  },
  (table) => ({
    advisoryIdx: index("idx_advisory_suggestions_advisory").on(table.advisoryId),
    statusIdx: index("idx_advisory_suggestions_status").on(table.status),
  })
);

// ==================== 关系定义 ====================

export const decisionsRelations = relations(decisions, ({ one }) => ({
  technical: one(technicalSnapshots, {
    fields: [decisions.id],
    references: [technicalSnapshots.decisionId],
  }),
  risk: one(riskSnapshots, {
    fields: [decisions.id],
    references: [riskSnapshots.decisionId],
  }),
  sentiment: one(sentimentSnapshots, {
    fields: [decisions.id],
    references: [sentimentSnapshots.decisionId],
  }),
  order: one(orders, {
    fields: [decisions.orderId],
    references: [orders.id],
  }),
}));

export const backtestsRelations = relations(backtests, ({ many }) => ({
  trades: many(backtestTrades),
  equity: many(backtestEquity),
}));

export const backtestTradesRelations = relations(backtestTrades, ({ one }) => ({
  backtest: one(backtests, {
    fields: [backtestTrades.backtestId],
    references: [backtests.id],
  }),
}));

export const backtestEquityRelations = relations(backtestEquity, ({ one }) => ({
  backtest: one(backtests, {
    fields: [backtestEquity.backtestId],
    references: [backtests.id],
  }),
}));

export const advisoriesRelations = relations(advisories, ({ many }) => ({
  suggestions: many(advisorySuggestions),
}));

export const advisorySuggestionsRelations = relations(advisorySuggestions, ({ one }) => ({
  advisory: one(advisories, {
    fields: [advisorySuggestions.advisoryId],
    references: [advisories.id],
  }),
}));

// ==================== LLM Provider 配置 ====================

export const llmProviders = pgTable("llm_providers", {
  id: integer("id").primaryKey().generatedAlwaysAsIdentity(),
  name: varchar("name", { length: 50 }).notNull().unique(),
  displayName: varchar("display_name", { length: 100 }).notNull(),
  providerType: varchar("provider_type", { length: 30 }).notNull(),
  apiKeyEncrypted: text("api_key_encrypted"),
  baseUrl: varchar("base_url", { length: 500 }),
  timeout: integer("timeout").notNull().default(60),
  models: jsonb("models").$type<string[]>().notNull().default([]),
  isBuiltin: boolean("is_builtin").notNull().default(false),
  isEnabled: boolean("is_enabled").notNull().default(true),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
});

export const llmRoutingConfig = pgTable("llm_routing_config", {
  id: integer("id").primaryKey().generatedAlwaysAsIdentity(),
  scope: varchar("scope", { length: 30 }).notNull(),
  providerId: integer("provider_id").notNull().references(() => llmProviders.id, { onDelete: "cascade" }),
  model: varchar("model", { length: 100 }).notNull(),
  priority: integer("priority").notNull().default(0),
  isEnabled: boolean("is_enabled").notNull().default(true),
});

// ==================== 性能追踪 ====================

export const performanceReports = pgTable("performance_reports", {
  id: uuid("id").primaryKey().defaultRandom(),
  computedAt: timestamp("computed_at", { withTimezone: true }).notNull().defaultNow(),

  period: varchar("period", { length: 20 }).notNull(),
  totalTrades: integer("total_trades").default(0),
  winRate: decimal("win_rate", { precision: 6, scale: 4 }),
  avgPnl: decimal("avg_pnl", { precision: 10, scale: 4 }),
  totalPnl: decimal("total_pnl", { precision: 20, scale: 4 }),
  sharpeRatio: decimal("sharpe_ratio", { precision: 8, scale: 4 }),
  maxDrawdownPct: decimal("max_drawdown_pct", { precision: 8, scale: 4 }),
  rawData: jsonb("raw_data"),
});

export const parameterChanges = pgTable("parameter_changes", {
  id: uuid("id").primaryKey().defaultRandom(),
  changedAt: timestamp("changed_at", { withTimezone: true }).notNull().defaultNow(),

  changes: jsonb("changes").notNull(),
  evalResult: jsonb("eval_result"),
  source: varchar("source", { length: 30 }).notNull(),
});

// ==================== 系统设置 ====================

export const systemSettings = pgTable("system_settings", {
  key: varchar("key", { length: 50 }).primaryKey(),
  value: text("value").notNull(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
});
