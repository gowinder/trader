# 策略预设选择功能设计

## 概述

提供 7 种预设策略模板，用户可在 Dashboard 页面一键切换交易策略。切换立即生效，已有持仓不受影响。

## 策略模板

### 1. 稳健趋势 (steady_trend)

- **适用场景**: 明确趋势市场
- **风险等级**: 低
- **策略组合**: 趋势跟随 100%
- **决策权重**: AI 60% / 量化 40%
- **分析周期**: 1h + 4h
- **最小交易间隔**: 6 小时
- **止损/止盈**: ATR×3 / ATR×8
- **最大仓位**: 15%，不加仓
- **情绪过滤**: 开启
- **预计交易频率**: 每天 0-1 次

### 2. 激进趋势 (aggressive_trend)

- **适用场景**: 强趋势市场
- **风险等级**: 中高
- **策略组合**: 趋势跟随 70% + 突破 30%
- **决策权重**: AI 40% / 量化 60%
- **分析周期**: 15m + 1h
- **最小交易间隔**: 2 小时
- **止损/止盈**: ATR×2 / ATR×5
- **最大仓位**: 30%，允许金字塔加仓（最多 2 次）
- **情绪过滤**: 关闭
- **预计交易频率**: 每天 1-3 次

### 3. 震荡收割 (range_harvest)

- **适用场景**: 区间震荡市场
- **风险等级**: 中
- **策略组合**: 均值回归 80% + 趋势 20%
- **决策权重**: 量化 70% / AI 30%
- **分析周期**: 15m + 1h
- **最小交易间隔**: 2 小时
- **止损/止盈**: ATR×2 / ATR×3
- **最大仓位**: 20%，不加仓
- **情绪过滤**: 开启
- **预计交易频率**: 每天 1-3 次

### 4. 突破猎手 (breakout_hunter)

- **适用场景**: 盘整后突破
- **风险等级**: 中
- **策略组合**: 突破 80% + 趋势 20%
- **决策权重**: 量化 60% / AI 40%
- **分析周期**: 1h + 4h
- **最小交易间隔**: 4 小时
- **止损/止盈**: ATR×2.5 / ATR×6
- **最大仓位**: 25%，允许加仓 1 次
- **情绪过滤**: 开启
- **预计交易频率**: 每天 0-2 次

### 5a. 温和剥头皮 (mild_scalping)

- **适用场景**: 任何市场
- **风险等级**: 中低
- **策略组合**: 均值回归 60% + 趋势 40%
- **决策权重**: 量化 75% / AI 25%
- **分析周期**: 5m + 15m
- **最小交易间隔**: 15 分钟
- **止损/止盈**: ATR×1.5 / ATR×2
- **最大仓位**: 10%
- **最小利润阈值**: 0.15%
- **情绪过滤**: 关闭
- **预计交易频率**: 每天 3-8 次

### 5b. 激进剥头皮 (aggressive_scalping)

- **适用场景**: 任何市场
- **风险等级**: 中
- **策略组合**: 均值回归 50% + 趋势 30% + 突破 20%
- **决策权重**: 量化 90% / AI 10%
- **分析周期**: 1m + 5m
- **最小交易间隔**: 5 分钟
- **止损/止盈**: ATR×1 / ATR×1.5
- **最大仓位**: 8%
- **最小利润阈值**: 0.1%
- **情绪过滤**: 关闭
- **仅使用市价单**: 确保成交速度
- **预计交易频率**: 每天 10-30 次

### 6. 均衡保守 (balanced_conservative)

- **适用场景**: 不确定市场
- **风险等级**: 最低
- **策略组合**: 趋势 50% + 均值回归 30% + 突破 20%
- **决策权重**: AI 70% / 量化 30%
- **分析周期**: 4h + 1d
- **最小交易间隔**: 12 小时
- **止损/止盈**: ATR×4 / ATR×6
- **最大仓位**: 10%，不加仓
- **情绪过滤**: 开启
- **预计交易频率**: 每天 0-1 次

## 数据模型

### StrategyPreset (Pydantic)

```python
class StrategyPreset(BaseModel):
    name: str                       # "aggressive_scalping"
    display_name: str               # "激进剥头皮"
    description: str                # 一句话描述
    category: str                   # "scalping" / "trend" / "range" / "breakout" / "balanced"
    risk_level: str                 # "low" / "medium_low" / "medium" / "medium_high" / "lowest"

    # 策略组合
    enabled_strategies: list[str]   # ["trend_following", "mean_reversion", "breakout"]
    strategy_weights: dict[str, float]  # {"trend_following": 0.7, "breakout": 0.3}

    # 决策权重
    ai_weight: float
    quant_weight: float
    sentiment_weight: float         # 0 表示关闭

    # 周期和频率
    timeframes: list[str]           # ["1m", "5m"]
    min_trade_interval_seconds: int # 秒为单位

    # 风控参数
    stop_loss_atr_multiplier: float
    take_profit_atr_multiplier: float
    max_position_pct: float
    enable_pyramid: bool
    max_pyramid_times: int

    # 开关和特殊参数
    enable_sentiment: bool
    min_profit_threshold: float     # 剥头皮专用，0 表示不启用
    use_market_order_only: bool     # 激进剥头皮专用
```

## 数据库设计

### strategy_presets 表

```sql
CREATE TABLE strategy_presets (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    description TEXT,
    category VARCHAR(20) NOT NULL,
    risk_level VARCHAR(20) NOT NULL,
    config_json JSONB NOT NULL,          -- 完整 StrategyPreset 参数
    is_system BOOLEAN DEFAULT TRUE,      -- 内置模板 vs 用户自定义
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### active_strategy 表

```sql
CREATE TABLE active_strategy (
    id SERIAL PRIMARY KEY,
    preset_id INTEGER REFERENCES strategy_presets(id),
    activated_at TIMESTAMP DEFAULT NOW(),
    deactivated_at TIMESTAMP
);
```

系统启动时，查询 `active_strategy` 中最新一条 `deactivated_at IS NULL` 的记录作为当前活跃策略。

## 存储架构

```
PostgreSQL (持久化)          Redis (缓存)
┌─────────────────┐        ┌──────────────────────┐
│ strategy_presets │        │ strategy:active_preset│
│ active_strategy  │  ───>  │ (完整配置JSON)        │
└─────────────────┘        └──────────────────────┘
         ↑ 写入                    ↑ 优先读取
         │                         │
    切换模板时同时写入PG+Redis     Scheduler每周期读取
```

### 启动流程

1. 从 PG 读取 `active_strategy` 最新激活记录
2. 加载对应 `strategy_presets` 配置写入 Redis
3. Scheduler 使用该配置运行
4. 若 PG 无记录，使用默认"稳健趋势"模板

## 策略切换流程

```
用户在Dashboard点击"激活"
    → 确认弹窗（当前策略 → 新策略对比）
    → POST /api/strategy-presets/activate {preset_id}
    → 旧记录写入 deactivated_at
    → 新记录写入 active_strategy
    → 更新 Redis 缓存
    → 返回成功
    → Scheduler 下个周期检测到配置变更
    → 用新参数重建 HybridDecisionEngine
    → 已有持仓保持不动
```

## API 接口

```
GET  /api/strategy-presets          — 获取所有模板列表（含历史表现数据）
GET  /api/strategy-presets/active   — 获取当前活跃模板
POST /api/strategy-presets/activate — 切换模板 {preset_id}
GET  /api/strategy-presets/history  — 切换历史记录
```

### 历史表现数据

每个模板返回时附带该模板激活期间的统计：

- 累计收益率（%）
- 胜率（%）
- 总交易次数
- 平均持仓时间

数据来源：`active_strategy` 时间段关联对应时段的交易记录聚合计算。

## Dashboard UI

### 新增页面：Strategy（策略选择）

侧边栏新增"策略"入口。

#### 顶部：当前活跃策略卡片

- 模板名称 + 风险等级标签（颜色区分）
- 运行时长
- 关键参数摘要：交易频率、止损止盈、仓位上限
- "运行中"状态指示灯

#### 主体：7 个策略模板卡片网格（2 列布局）

每张卡片：

- 模板名称 + 风险等级色标（绿/黄/橙/红）
- 一句话描述
- 3-4 个关键指标：交易频率、目标利润、最大仓位
- 分类标签（趋势/震荡/剥头皮/均衡）
- 历史表现：累计收益率、胜率、交易次数、平均持仓时间
- **"激活"按钮**

#### 确认弹窗

- 当前策略 → 新策略参数对比表
- 提示"已有持仓不受影响，新策略在下个分析周期生效"
- 确认 / 取消按钮

## 风险等级配色

| 等级 | 颜色 | 模板 |
|------|------|------|
| 最低 | 绿色 | 均衡保守 |
| 低 | 浅绿 | 稳健趋势 |
| 中低 | 黄色 | 温和剥头皮 |
| 中 | 橙色 | 震荡收割、突破猎手、激进剥头皮 |
| 中高 | 红色 | 激进趋势 |
