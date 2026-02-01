CREATE TABLE "alert_history" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"level" varchar(10) NOT NULL,
	"category" varchar(20) NOT NULL,
	"title" varchar(100) NOT NULL,
	"message" text NOT NULL,
	"symbol" varchar(20),
	"decision_id" uuid,
	"order_id" uuid,
	"channels_sent" jsonb
);
--> statement-breakpoint
CREATE TABLE "alert_settings" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	"channels" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"rules" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"price_alerts" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"quiet_hours" jsonb
);
--> statement-breakpoint
CREATE TABLE "backtest_equity" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"backtest_id" uuid NOT NULL,
	"timestamp" timestamp with time zone NOT NULL,
	"total_equity" numeric(20, 2) NOT NULL,
	"symbol_equity" jsonb
);
--> statement-breakpoint
CREATE TABLE "backtest_schedule_config" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	"enabled" boolean DEFAULT false NOT NULL,
	"schedule_type" varchar(20) DEFAULT 'manual' NOT NULL,
	"schedule_cron" varchar(50),
	"schedule_hour" smallint DEFAULT 0,
	"schedule_day_of_week" smallint,
	"symbols" jsonb DEFAULT '["BTCUSDT"]'::jsonb NOT NULL,
	"timeframe" varchar(10) DEFAULT '1h' NOT NULL,
	"lookback_days" smallint DEFAULT 30 NOT NULL,
	"initial_capital" numeric(20, 2) DEFAULT '10000' NOT NULL,
	"enable_filters" boolean DEFAULT true NOT NULL,
	"strategies" jsonb DEFAULT '["trend_following"]'::jsonb NOT NULL
);
--> statement-breakpoint
CREATE TABLE "backtest_trades" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"backtest_id" uuid NOT NULL,
	"symbol" varchar(20) NOT NULL,
	"entry_time" timestamp with time zone NOT NULL,
	"exit_time" timestamp with time zone,
	"side" varchar(10) NOT NULL,
	"entry_price" numeric(20, 8) NOT NULL,
	"exit_price" numeric(20, 8),
	"size" numeric(20, 8) NOT NULL,
	"pnl" numeric(20, 8),
	"pnl_percent" numeric(8, 4),
	"decision_snapshot" jsonb
);
--> statement-breakpoint
CREATE TABLE "backtests" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"mode" varchar(20) NOT NULL,
	"symbol" varchar(20),
	"symbols_config" jsonb,
	"portfolio_params" jsonb,
	"start_date" date NOT NULL,
	"end_date" date NOT NULL,
	"initial_capital" numeric(20, 2) NOT NULL,
	"leverage" numeric(4, 1),
	"strategy_mode" varchar(20),
	"params" jsonb,
	"status" varchar(20) NOT NULL,
	"progress" smallint DEFAULT 0,
	"error_message" text,
	"final_capital" numeric(20, 2),
	"total_pnl" numeric(20, 2),
	"total_trades" integer,
	"winning_trades" integer,
	"max_drawdown" numeric(8, 4),
	"sharpe_ratio" numeric(8, 4),
	"symbol_results" jsonb,
	"completed_at" timestamp with time zone
);
--> statement-breakpoint
CREATE TABLE "correlation_cache" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"calculated_at" timestamp with time zone DEFAULT now() NOT NULL,
	"symbol_a" varchar(20) NOT NULL,
	"symbol_b" varchar(20) NOT NULL,
	"timeframe" varchar(10) NOT NULL,
	"correlation" numeric(5, 4) NOT NULL,
	"sample_size" integer NOT NULL
);
--> statement-breakpoint
CREATE TABLE "daily_stats" (
	"date" date NOT NULL,
	"symbol" varchar(20) NOT NULL,
	"total_trades" integer DEFAULT 0,
	"winning_trades" integer DEFAULT 0,
	"losing_trades" integer DEFAULT 0,
	"total_pnl" numeric(20, 8) DEFAULT '0',
	"max_drawdown" numeric(8, 4),
	CONSTRAINT "daily_stats_date_symbol_pk" PRIMARY KEY("date","symbol")
);
--> statement-breakpoint
CREATE TABLE "decisions" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"symbol" varchar(20) NOT NULL,
	"timeframe" varchar(10) NOT NULL,
	"action" varchar(20) NOT NULL,
	"confidence" smallint NOT NULL,
	"leverage" numeric(4, 1),
	"position_size_pct" numeric(5, 2),
	"entry_price" numeric(20, 8),
	"stop_loss" numeric(20, 8),
	"take_profit" numeric(20, 8),
	"reasoning" text,
	"llm_provider" varchar(30),
	"llm_model" varchar(50),
	"llm_raw_output" text,
	"llm_tokens_used" integer,
	"order_id" uuid
);
--> statement-breakpoint
CREATE TABLE "operation_logs" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"action" varchar(50) NOT NULL,
	"operator" varchar(50),
	"details" jsonb,
	"ip_address" varchar(50)
);
--> statement-breakpoint
CREATE TABLE "orders" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"symbol" varchar(20) NOT NULL,
	"exchange_order_id" varchar(50),
	"side" varchar(20) NOT NULL,
	"order_type" varchar(10) NOT NULL,
	"price" numeric(20, 8),
	"size" numeric(20, 8) NOT NULL,
	"filled_price" numeric(20, 8),
	"filled_size" numeric(20, 8),
	"fee" numeric(20, 8),
	"status" varchar(20) NOT NULL,
	"closed_at" timestamp with time zone
);
--> statement-breakpoint
CREATE TABLE "position_history" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"symbol" varchar(20) NOT NULL,
	"side" varchar(10) NOT NULL,
	"entry_time" timestamp with time zone NOT NULL,
	"entry_price" numeric(20, 8) NOT NULL,
	"entry_size" numeric(20, 8) NOT NULL,
	"leverage" numeric(4, 1),
	"exit_time" timestamp with time zone,
	"exit_price" numeric(20, 8),
	"realized_pnl" numeric(20, 8),
	"pnl_percent" numeric(8, 4),
	"fee_total" numeric(20, 8),
	"entry_decision_id" uuid,
	"exit_decision_id" uuid,
	"status" varchar(20) NOT NULL
);
--> statement-breakpoint
CREATE TABLE "price_history" (
	"symbol" varchar(20) NOT NULL,
	"timestamp" timestamp with time zone NOT NULL,
	"close_price" numeric(20, 8) NOT NULL,
	CONSTRAINT "price_history_symbol_timestamp_pk" PRIMARY KEY("symbol","timestamp")
);
--> statement-breakpoint
CREATE TABLE "risk_snapshots" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"decision_id" uuid NOT NULL,
	"risk_level" varchar(20),
	"risk_score" smallint,
	"recommended_leverage" numeric(4, 1),
	"recommended_position_pct" numeric(5, 2),
	"should_trade" boolean,
	"risk_factors" jsonb,
	"mitigation_suggestions" jsonb
);
--> statement-breakpoint
CREATE TABLE "sentiment_snapshots" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"decision_id" uuid NOT NULL,
	"overall_score" numeric(4, 2),
	"news_count" integer,
	"bullish_count" integer,
	"bearish_count" integer,
	"top_news" jsonb,
	"data_source" varchar(30)
);
--> statement-breakpoint
CREATE TABLE "technical_snapshots" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"decision_id" uuid NOT NULL,
	"trend" varchar(20),
	"trend_confidence" smallint,
	"signal_strength" varchar(20),
	"price" numeric(20, 8),
	"rsi" numeric(6, 2),
	"macd" numeric(20, 8),
	"macd_signal" numeric(20, 8),
	"ma7" numeric(20, 8),
	"ma25" numeric(20, 8),
	"ma99" numeric(20, 8),
	"atr" numeric(20, 8),
	"boll_upper" numeric(20, 8),
	"boll_lower" numeric(20, 8),
	"support_levels" jsonb,
	"resistance_levels" jsonb,
	"volume_trend" varchar(20),
	"pattern" varchar(50),
	"key_observations" jsonb
);
--> statement-breakpoint
ALTER TABLE "alert_history" ADD CONSTRAINT "alert_history_decision_id_decisions_id_fk" FOREIGN KEY ("decision_id") REFERENCES "public"."decisions"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "alert_history" ADD CONSTRAINT "alert_history_order_id_orders_id_fk" FOREIGN KEY ("order_id") REFERENCES "public"."orders"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "backtest_equity" ADD CONSTRAINT "backtest_equity_backtest_id_backtests_id_fk" FOREIGN KEY ("backtest_id") REFERENCES "public"."backtests"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "backtest_trades" ADD CONSTRAINT "backtest_trades_backtest_id_backtests_id_fk" FOREIGN KEY ("backtest_id") REFERENCES "public"."backtests"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "decisions" ADD CONSTRAINT "decisions_order_id_orders_id_fk" FOREIGN KEY ("order_id") REFERENCES "public"."orders"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "position_history" ADD CONSTRAINT "position_history_entry_decision_id_decisions_id_fk" FOREIGN KEY ("entry_decision_id") REFERENCES "public"."decisions"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "position_history" ADD CONSTRAINT "position_history_exit_decision_id_decisions_id_fk" FOREIGN KEY ("exit_decision_id") REFERENCES "public"."decisions"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "risk_snapshots" ADD CONSTRAINT "risk_snapshots_decision_id_decisions_id_fk" FOREIGN KEY ("decision_id") REFERENCES "public"."decisions"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "sentiment_snapshots" ADD CONSTRAINT "sentiment_snapshots_decision_id_decisions_id_fk" FOREIGN KEY ("decision_id") REFERENCES "public"."decisions"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "technical_snapshots" ADD CONSTRAINT "technical_snapshots_decision_id_decisions_id_fk" FOREIGN KEY ("decision_id") REFERENCES "public"."decisions"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "idx_alerts_time" ON "alert_history" USING btree ("created_at");--> statement-breakpoint
CREATE INDEX "idx_alerts_level" ON "alert_history" USING btree ("level","created_at");--> statement-breakpoint
CREATE INDEX "idx_equity_backtest_time" ON "backtest_equity" USING btree ("backtest_id","timestamp");--> statement-breakpoint
CREATE UNIQUE INDEX "correlation_unique_idx" ON "correlation_cache" USING btree ("symbol_a","symbol_b","timeframe");--> statement-breakpoint
CREATE INDEX "idx_decisions_symbol_time" ON "decisions" USING btree ("symbol","created_at");--> statement-breakpoint
CREATE INDEX "idx_orders_symbol_time" ON "orders" USING btree ("symbol","created_at");--> statement-breakpoint
CREATE INDEX "idx_positions_symbol" ON "position_history" USING btree ("symbol","entry_time");