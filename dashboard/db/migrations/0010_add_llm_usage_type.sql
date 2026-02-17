-- 添加 usage_type 字段到 llm_usage 表
ALTER TABLE llm_usage ADD COLUMN IF NOT EXISTS usage_type VARCHAR(30);

-- 为 usage_type 添加索引
CREATE INDEX IF NOT EXISTS idx_llm_usage_type ON llm_usage(usage_type);
