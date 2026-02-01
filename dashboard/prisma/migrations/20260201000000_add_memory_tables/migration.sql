-- AI 记忆与自优化系统数据库表

-- 短期记忆表
CREATE TABLE IF NOT EXISTS trade_memory (
    id SERIAL PRIMARY KEY,
    trade_id VARCHAR(64) UNIQUE NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(20) NOT NULL,

    -- 决策快照
    action VARCHAR(20) NOT NULL,
    confidence FLOAT NOT NULL,
    leverage FLOAT NOT NULL,
    reasoning TEXT,

    -- 市场上下文
    market_state VARCHAR(20),
    timeframe_alignment JSONB,
    technical_snapshot JSONB,
    patterns_detected JSONB,

    -- 结果
    entry_price FLOAT,
    exit_price FLOAT,
    pnl_percent FLOAT,
    max_adverse_excursion FLOAT,
    max_favorable_excursion FLOAT,
    holding_duration INTERVAL,

    -- 分析维度
    hour_of_day INT,
    day_of_week INT,
    consecutive_losses INT,
    is_winner BOOLEAN,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 长期记忆表（提炼规则）
CREATE TABLE IF NOT EXISTS distilled_rules (
    id SERIAL PRIMARY KEY,
    rule_id VARCHAR(64) UNIQUE NOT NULL,

    -- 规则定义
    condition JSONB NOT NULL,
    recommendation JSONB NOT NULL,
    reasoning TEXT,

    -- 统计验证
    sample_size INT NOT NULL,
    win_rate FLOAT NOT NULL,
    avg_pnl FLOAT NOT NULL,
    p_value FLOAT NOT NULL,

    -- 状态
    status VARCHAR(20) DEFAULT 'candidate',
    validation_count INT DEFAULT 0,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_validated TIMESTAMPTZ
);

-- 参数历史表
CREATE TABLE IF NOT EXISTS parameter_history (
    id SERIAL PRIMARY KEY,
    param_name VARCHAR(64) NOT NULL,
    old_value FLOAT NOT NULL,
    new_value FLOAT NOT NULL,
    trigger_type VARCHAR(20),
    reasoning TEXT,
    changed_at TIMESTAMPTZ DEFAULT NOW()
);

-- 影子运行结果表
CREATE TABLE IF NOT EXISTS shadow_runs (
    id SERIAL PRIMARY KEY,
    run_id VARCHAR(64) UNIQUE NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,

    current_params JSONB NOT NULL,
    candidate_params JSONB NOT NULL,

    current_trades INT DEFAULT 0,
    candidate_trades INT DEFAULT 0,
    current_win_rate FLOAT,
    candidate_win_rate FLOAT,
    current_avg_pnl FLOAT,
    candidate_avg_pnl FLOAT,

    status VARCHAR(20) DEFAULT 'running',
    conclusion TEXT
);

-- 复盘记录表
CREATE TABLE IF NOT EXISTS reflection_logs (
    id SERIAL PRIMARY KEY,
    reflection_id VARCHAR(64) UNIQUE NOT NULL,
    triggered_at TIMESTAMPTZ NOT NULL,
    trades_analyzed INT NOT NULL,

    summary TEXT,
    insights JSONB,
    candidate_rules JSONB,
    parameter_suggestions JSONB,

    rules_created INT DEFAULT 0,
    shadow_run_started BOOLEAN DEFAULT FALSE
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_trade_memory_timestamp ON trade_memory(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_trade_memory_symbol ON trade_memory(symbol);
CREATE INDEX IF NOT EXISTS idx_trade_memory_market_state ON trade_memory(market_state);
CREATE INDEX IF NOT EXISTS idx_distilled_rules_status ON distilled_rules(status);
CREATE INDEX IF NOT EXISTS idx_shadow_runs_status ON shadow_runs(status);
CREATE INDEX IF NOT EXISTS idx_parameter_history_param ON parameter_history(param_name);
