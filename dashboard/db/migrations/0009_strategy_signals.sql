-- Phase 2 闭环: 为 decisions 表添加策略信号和市场状态列
-- 用于 StrategyWeightOptimizer 查询历史表现计算最优权重
ALTER TABLE "decisions" ADD COLUMN "market_state" varchar(30);
ALTER TABLE "decisions" ADD COLUMN "strategy_signals" jsonb;
