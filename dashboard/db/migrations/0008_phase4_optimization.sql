-- Phase 4: 优化闭环验证 + 性能追踪 + LLM 质量监控

-- 4.3 decisions 新增 quality_score 列
ALTER TABLE "decisions" ADD COLUMN "quality_score" smallint;

-- 4.2 性能追踪报告表
CREATE TABLE "performance_reports" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"computed_at" timestamp with time zone DEFAULT now() NOT NULL,
	"period" varchar(20) NOT NULL,
	"total_trades" integer DEFAULT 0,
	"win_rate" numeric(6, 4),
	"avg_pnl" numeric(10, 4),
	"total_pnl" numeric(20, 4),
	"sharpe_ratio" numeric(8, 4),
	"max_drawdown_pct" numeric(8, 4),
	"raw_data" jsonb
);

-- 4.1 参数变更记录表
CREATE TABLE "parameter_changes" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"changed_at" timestamp with time zone DEFAULT now() NOT NULL,
	"changes" jsonb NOT NULL,
	"eval_result" jsonb,
	"source" varchar(30) NOT NULL
);
