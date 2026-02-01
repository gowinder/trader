# AI 记忆与策略自优化系统设计

> 创建时间: 2026-02-01
> 状态: 待实现

## 1. 概述

### 1.1 目标

让 AI 交易系统具备「记忆」能力，能够：
- 回顾历史下单决策
- 定期进行复盘反思
- 自动优化策略参数

### 1.2 核心决策

| 维度 | 决策 |
|------|------|
| 触发时机 | 按交易数量触发（每 N 笔交易后复盘，默认 10 笔，可配置） |
| 经验应用 | 自动参数调整 |
| 可调范围 | 全参数可调，但带硬性边界 |
| 分析维度 | 全维度（绩效、市况、信号、时段、心理） |
| 存储结构 | 短期 + 长期双层记忆 |
| 晋升机制 | LLM 提炼 + 统计双重验证 |
| 生效方式 | 模拟验证后生效（影子运行对比） |

---

## 2. 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        AI 记忆与自优化系统                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │ 交易执行层   │───▶│ 记忆收集器   │───▶│  短期记忆    │      │
│  │ (现有系统)   │    │ TradeMemory  │    │ (最近N笔)    │      │
│  └──────────────┘    │  Collector   │    └──────┬───────┘      │
│                      └──────────────┘           │              │
│                                                 ▼              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │ 参数注册表   │◀───│ 复盘引擎     │◀───│ 复盘触发器   │      │
│  │ Parameter    │    │ Reflection   │    │ (每N笔触发)  │      │
│  │ Registry     │    │ Engine       │    └──────────────┘      │
│  └──────┬───────┘    └──────┬───────┘                          │
│         │                   │                                  │
│         ▼                   ▼                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │ 影子运行器   │◀───│ 规则提炼器   │───▶│  长期记忆    │      │
│  │ Shadow       │    │ (LLM+统计)   │    │ (验证规则)   │      │
│  │ Runner       │    └──────────────┘    └──────────────┘      │
│  └──────┬───────┘                                              │
│         │                                                      │
│         ▼                                                      │
│  ┌──────────────┐                                              │
│  │ 参数切换器   │──▶ 验证通过后更新决策引擎参数                  │
│  └──────────────┘                                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 核心组件

- **TradeMemoryCollector**：每笔交易完成后收集完整上下文到短期记忆
- **ReflectionEngine**：复盘引擎，调用 LLM 进行全维度分析
- **RuleDistiller**：规则提炼器，LLM 生成候选规则 + 统计验证
- **ShadowRunner**：影子运行器，新参数与现参数并行对比
- **ParameterRegistry**：参数注册表，管理所有可调参数及其硬边界

---

## 3. 数据模型

### 3.1 短期记忆结构 (TradeMemoryEntry)

```python
@dataclass
class TradeMemoryEntry:
    # 基础信息
    trade_id: str
    timestamp: datetime
    symbol: str

    # 决策快照
    action: str  # open_long, open_short, close_long, close_short
    confidence: float
    leverage: float
    reasoning: str  # AI 生成的决策理由

    # 市场上下文
    market_state: str  # strong_trend, weak_trend, ranging, breakout
    timeframe_alignment: dict  # 多时间框架一致性

    # 技术指标快照
    technical_snapshot: dict  # RSI, MACD, MA, Bollinger 等
    pattern_detected: list[str]  # 识别到的 K 线形态

    # 结果
    entry_price: float
    exit_price: float | None
    pnl_percent: float | None
    max_adverse_excursion: float  # 最大逆向波动
    max_favorable_excursion: float  # 最大顺向波动
    holding_duration: timedelta

    # 分析维度
    hour_of_day: int  # 交易时段
    day_of_week: int
    consecutive_losses: int  # 之前连亏次数
    is_winner: bool | None
```

### 3.2 长期记忆结构 (DistilledRule)

```python
@dataclass
class DistilledRule:
    rule_id: str
    created_at: datetime
    last_validated: datetime

    # 规则定义
    condition: dict  # 触发条件，如 {"market_state": "ranging", "rsi": ">70"}
    recommendation: dict  # 建议，如 {"action_bias": "short", "confidence_boost": 0.15}

    # 统计验证
    sample_size: int  # 验证样本数
    win_rate: float
    avg_pnl: float
    p_value: float  # 统计显著性

    # 状态
    status: str  # candidate, active, deprecated
    validation_count: int  # 被验证次数
```

---

## 4. 参数注册表与硬边界

### 4.1 可调参数定义

```python
@dataclass
class AdjustableParameter:
    name: str
    current_value: float
    min_bound: float  # 硬性下限
    max_bound: float  # 硬性上限
    step: float  # 最小调整步长
    category: str  # decision, position, risk, timing

PARAMETER_REGISTRY = {
    # 决策偏好类
    "confidence_threshold": AdjustableParameter(
        name="confidence_threshold",
        current_value=60.0, min_bound=40.0, max_bound=90.0, step=5.0,
        category="decision"
    ),
    "hold_bias": AdjustableParameter(  # HOLD 倾向权重
        name="hold_bias",
        current_value=0.0, min_bound=-0.3, max_bound=0.3, step=0.05,
        category="decision"
    ),
    "quant_ai_weight_trend": AdjustableParameter(  # 趋势市量化权重
        name="quant_ai_weight_trend",
        current_value=0.7, min_bound=0.3, max_bound=0.9, step=0.1,
        category="decision"
    ),

    # 仓位控制类
    "max_position_percent": AdjustableParameter(
        name="max_position_percent",
        current_value=20.0, min_bound=5.0, max_bound=30.0, step=5.0,
        category="position"
    ),
    "max_leverage": AdjustableParameter(
        name="max_leverage",
        current_value=5.0, min_bound=1.0, max_bound=10.0, step=1.0,
        category="position"
    ),

    # 风险控制类
    "stop_loss_percent": AdjustableParameter(
        name="stop_loss_percent",
        current_value=5.0, min_bound=2.0, max_bound=10.0, step=0.5,
        category="risk"
    ),
    "take_profit_percent": AdjustableParameter(
        name="take_profit_percent",
        current_value=10.0, min_bound=5.0, max_bound=25.0, step=1.0,
        category="risk"
    ),

    # 时段控制类
    "avoid_hours": AdjustableParameter(  # 避开交易的小时（位图）
        name="avoid_hours",
        current_value=0, min_bound=0, max_bound=16777215, step=1,
        category="timing"
    ),
}
```

### 4.2 硬边界原则

| 参数类别 | 硬边界逻辑 |
|---------|-----------|
| 杠杆 | 永不超过 10x（交易所限制） |
| 止损 | 永不小于 2%（防止频繁止损） |
| 仓位 | 永不超过 30%（单笔风险控制） |
| 置信度阈值 | 永不低于 40%（防止过度交易） |

---

## 5. 复盘引擎流程

### 5.1 触发与分析流程

```
交易完成 → 计数器+1 → 达到阈值(默认10)？
                            │
                            ▼ 是
                    ┌───────────────┐
                    │ 1. 收集数据   │
                    │ 提取短期记忆  │
                    │ 最近N笔交易   │
                    └───────┬───────┘
                            │
                            ▼
                    ┌───────────────┐
                    │ 2. LLM 分析   │
                    │ 全维度复盘    │
                    └───────┬───────┘
                            │
            ┌───────────────┼───────────────┐
            ▼               ▼               ▼
    ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
    │ 绩效分析    │ │ 市况分析    │ │ 信号分析    │
    │ 胜率/盈亏比 │ │ 各状态表现  │ │ 指标有效性  │
    └─────────────┘ └─────────────┘ └─────────────┘
            │               │               │
            └───────────────┼───────────────┘
                            ▼
                    ┌───────────────┐
                    │ 3. 提炼规则   │
                    │ 生成候选规则  │
                    └───────┬───────┘
                            │
                            ▼
                    ┌───────────────┐
                    │ 4. 统计验证   │
                    │ p_value<0.05? │
                    └───────┬───────┘
                            │
                    ┌───────┴───────┐
                    ▼               ▼
                通过            不通过
                 │               │
                 ▼               ▼
           存入长期记忆      丢弃候选规则
```

### 5.2 LLM 复盘 Prompt 结构

```python
REFLECTION_PROMPT = """
你是交易策略分析师。分析以下 {n} 笔交易记录，从多个维度总结经验。

## 交易数据
{trade_data_json}

## 当前参数
{current_parameters}

## 分析维度要求

1. **绩效总览**：胜率、平均盈亏、最大回撤
2. **市况表现**：趋势市 vs 震荡市 vs 突破市的表现差异
3. **信号质量**：哪些技术信号组合更可靠，哪些容易误判
4. **时段分析**：不同时段的交易效果
5. **心理因素**：连亏后的决策质量是否下降

## 输出格式
{
  "summary": "整体表现概述",
  "insights": [{"dimension": "...", "finding": "...", "confidence": 0-1}],
  "candidate_rules": [
    {
      "condition": {"market_state": "...", "indicator": "..."},
      "recommendation": {"param": "...", "adjustment": ...},
      "reasoning": "..."
    }
  ],
  "parameter_suggestions": {
    "param_name": {"new_value": ..., "reasoning": "..."}
  }
}
"""
```

---

## 6. 规则验证与影子运行

### 6.1 统计验证逻辑

```python
class RuleValidator:
    """候选规则的统计验证器"""

    MIN_SAMPLE_SIZE = 20  # 最小样本量
    P_VALUE_THRESHOLD = 0.05  # 显著性阈值
    MIN_WIN_RATE_IMPROVEMENT = 0.05  # 最小胜率提升

    def validate(self, rule: CandidateRule, history: list[TradeMemoryEntry]) -> bool:
        # 1. 筛选符合规则条件的历史交易
        matched_trades = [t for t in history if self._match_condition(t, rule.condition)]

        if len(matched_trades) < self.MIN_SAMPLE_SIZE:
            return False  # 样本不足

        # 2. 计算应用规则后的预期效果
        baseline_win_rate = self._calc_win_rate(matched_trades, use_rule=False)
        rule_win_rate = self._calc_win_rate(matched_trades, use_rule=True)

        # 3. 卡方检验 / t检验
        p_value = self._statistical_test(matched_trades, rule)

        # 4. 综合判断
        return (
            p_value < self.P_VALUE_THRESHOLD and
            rule_win_rate - baseline_win_rate >= self.MIN_WIN_RATE_IMPROVEMENT
        )
```

### 6.2 影子运行机制

```
参数调整建议生成
        │
        ▼
┌───────────────────────────────────────────┐
│              影子运行器                    │
├───────────────────────────────────────────┤
│                                           │
│   实盘决策引擎          影子决策引擎        │
│   (current_params)     (candidate_params) │
│         │                    │            │
│         ▼                    ▼            │
│   ┌──────────┐         ┌──────────┐       │
│   │ 生成决策 │         │ 生成决策 │       │
│   │ 实际执行 │         │ 仅记录   │       │
│   └────┬─────┘         └────┬─────┘       │
│        │                    │             │
│        ▼                    ▼             │
│   实盘结果记录          模拟结果记录        │
│                                           │
└───────────────────────────────────────────┘
        │
        ▼ (累计 N 笔后对比)

┌───────────────────────────────────────────┐
│              对比评估                      │
├───────────────────────────────────────────┤
│  指标        │  实盘参数  │  候选参数      │
│  ──────────────────────────────────────   │
│  胜率        │   58%     │    65%        │
│  平均盈亏    │  +1.2%    │   +1.8%       │
│  最大回撤    │   -8%     │    -6%        │
└───────────────────────────────────────────┘
        │
        ▼
   候选参数全面优于实盘？
        │
   ┌────┴────┐
   是        否
   │         │
   ▼         ▼
 切换参数   保留现参数
 记录日志   丢弃候选
```

### 6.3 切换条件

```python
SWITCH_CRITERIA = {
    "min_shadow_trades": 10,  # 最少影子交易数
    "win_rate_improvement": 0.03,  # 胜率至少提升 3%
    "pnl_improvement": 0.005,  # 平均盈亏至少提升 0.5%
    "max_drawdown_not_worse": True,  # 回撤不能恶化
}
```

---

## 7. 数据库表设计

### 7.1 新增表结构

```sql
-- 短期记忆表
CREATE TABLE trade_memory (
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
CREATE TABLE distilled_rules (
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
    status VARCHAR(20) DEFAULT 'candidate',  -- candidate, active, deprecated
    validation_count INT DEFAULT 0,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_validated TIMESTAMPTZ
);

-- 参数历史表
CREATE TABLE parameter_history (
    id SERIAL PRIMARY KEY,
    param_name VARCHAR(64) NOT NULL,
    old_value FLOAT NOT NULL,
    new_value FLOAT NOT NULL,
    trigger_type VARCHAR(20),  -- reflection, shadow_switch, manual
    reasoning TEXT,
    changed_at TIMESTAMPTZ DEFAULT NOW()
);

-- 影子运行结果表
CREATE TABLE shadow_runs (
    id SERIAL PRIMARY KEY,
    run_id VARCHAR(64) UNIQUE NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,

    -- 参数对比
    current_params JSONB NOT NULL,
    candidate_params JSONB NOT NULL,

    -- 结果统计
    current_trades INT DEFAULT 0,
    candidate_trades INT DEFAULT 0,
    current_win_rate FLOAT,
    candidate_win_rate FLOAT,
    current_avg_pnl FLOAT,
    candidate_avg_pnl FLOAT,

    -- 结论
    status VARCHAR(20) DEFAULT 'running',  -- running, switched, rejected
    conclusion TEXT
);

-- 复盘记录表
CREATE TABLE reflection_logs (
    id SERIAL PRIMARY KEY,
    reflection_id VARCHAR(64) UNIQUE NOT NULL,
    triggered_at TIMESTAMPTZ NOT NULL,
    trades_analyzed INT NOT NULL,

    -- LLM 分析结果
    summary TEXT,
    insights JSONB,
    candidate_rules JSONB,
    parameter_suggestions JSONB,

    -- 后续动作
    rules_created INT DEFAULT 0,
    shadow_run_started BOOLEAN DEFAULT FALSE
);
```

### 7.2 索引建议

```sql
-- 短期记忆查询优化
CREATE INDEX idx_trade_memory_timestamp ON trade_memory(timestamp DESC);
CREATE INDEX idx_trade_memory_symbol ON trade_memory(symbol);
CREATE INDEX idx_trade_memory_market_state ON trade_memory(market_state);

-- 长期规则查询优化
CREATE INDEX idx_distilled_rules_status ON distilled_rules(status);

-- 影子运行查询优化
CREATE INDEX idx_shadow_runs_status ON shadow_runs(status);
```

---

## 8. 代码模块结构

### 8.1 新增文件结构

```
src/ai_trader/
├── memory/                          # 新增：记忆系统
│   ├── __init__.py
│   ├── collector.py                 # TradeMemoryCollector
│   ├── short_term.py                # ShortTermMemory 管理
│   └── long_term.py                 # LongTermMemory 管理
│
├── reflection/                      # 新增：复盘系统
│   ├── __init__.py
│   ├── engine.py                    # ReflectionEngine 主引擎
│   ├── trigger.py                   # ReflectionTrigger 触发器
│   ├── analyzer.py                  # 多维度分析器
│   └── prompts.py                   # 复盘 Prompt 模板
│
├── optimization/                    # 新增：自优化系统
│   ├── __init__.py
│   ├── parameter_registry.py        # 参数注册表
│   ├── rule_distiller.py            # 规则提炼器
│   ├── rule_validator.py            # 统计验证器
│   └── shadow_runner.py             # 影子运行器
│
├── config.py                        # 修改：新增记忆系统配置
└── scheduler.py                     # 修改：集成复盘触发
```

### 8.2 与现有系统集成点

```python
# scheduler.py 修改示意

class TradingScheduler:
    def __init__(self):
        # ... 现有初始化 ...

        # 新增：记忆与复盘系统
        self.memory_collector = TradeMemoryCollector(db_manager)
        self.reflection_trigger = ReflectionTrigger(
            threshold=config.reflection_trade_count,  # 默认 10
            engine=ReflectionEngine(llm_client, db_manager)
        )
        self.shadow_runner = ShadowRunner(db_manager)

    async def on_position_closed(self, position: Position, result: TradeResult):
        """仓位关闭时的回调"""
        # 1. 收集到短期记忆
        await self.memory_collector.collect(position, result)

        # 2. 检查是否触发复盘
        await self.reflection_trigger.check_and_run()

        # 3. 如果有影子运行，记录影子决策结果
        if self.shadow_runner.is_running:
            await self.shadow_runner.record_result(position, result)
```

### 8.3 配置扩展

```python
# config.py 新增配置项

class MemoryConfig:
    # 复盘触发
    reflection_trade_count: int = 10  # 每 N 笔触发复盘
    short_term_memory_size: int = 100  # 短期记忆保留笔数

    # 规则验证
    min_validation_sample: int = 20
    p_value_threshold: float = 0.05
    min_win_rate_improvement: float = 0.05

    # 影子运行
    shadow_run_min_trades: int = 10
    shadow_win_rate_threshold: float = 0.03
    shadow_pnl_threshold: float = 0.005
```

---

## 9. 端到端工作流示例

```
第 1-9 笔交易：
  └─ 每笔交易完成 → 收集到短期记忆 → 计数器累加

第 10 笔交易完成：
  └─ 触发复盘
      │
      ├─ 1. 提取短期记忆（最近 10 笔）
      │
      ├─ 2. LLM 全维度分析
      │     输出示例：
      │     {
      │       "summary": "震荡市表现较差，RSI 超买做空胜率较高",
      │       "insights": [
      │         {"dimension": "市况", "finding": "趋势市胜率72%，震荡市仅45%", "confidence": 0.85},
      │         {"dimension": "信号", "finding": "RSI>75做空胜率80%", "confidence": 0.78}
      │       ],
      │       "candidate_rules": [
      │         {
      │           "condition": {"market_state": "ranging"},
      │           "recommendation": {"confidence_threshold": "+10"},
      │           "reasoning": "震荡市误判率高，提高开仓门槛"
      │         }
      │       ],
      │       "parameter_suggestions": {
      │         "confidence_threshold": {"new_value": 70, "reasoning": "整体胜率偏低"}
      │       }
      │     }
      │
      ├─ 3. 规则统计验证
      │     └─ "震荡市提高门槛" 规则：样本 25 笔，p_value=0.03 → 通过
      │
      ├─ 4. 存入长期记忆（status=candidate）
      │
      └─ 5. 启动影子运行
            current_params: {confidence_threshold: 60}
            candidate_params: {confidence_threshold: 70}

第 11-20 笔交易：
  └─ 并行运行
      ├─ 实盘：使用 current_params 执行
      └─ 影子：使用 candidate_params 仅记录

第 20 笔完成后：
  └─ 影子对比评估
      │
      ├─ 实盘胜率: 55%, 平均盈亏: +0.8%
      ├─ 影子胜率: 62%, 平均盈亏: +1.3%
      │
      └─ 候选参数全面优于实盘 → 执行切换
          ├─ 更新 ParameterRegistry
          ├─ 规则状态: candidate → active
          └─ 记录 parameter_history
```

---

## 10. 安全保障

| 风险 | 防护措施 |
|-----|---------|
| 过拟合 | LLM + 统计双重验证，p_value < 0.05 |
| 激进调参 | 硬边界限制，单次调整幅度限制 |
| 短期噪音 | 影子运行验证，至少 10 笔对比 |
| 连续错误调整 | 参数历史回溯，支持一键回滚 |
| 市场剧变 | 长期规则定期重验证，失效则 deprecate |

---

## 11. 实现优先级建议

### Phase 1: 基础记忆系统
- [ ] 实现 TradeMemoryCollector
- [ ] 实现 ShortTermMemory 存储
- [ ] 创建数据库表 trade_memory
- [ ] 集成到 scheduler 的仓位关闭回调

### Phase 2: 复盘引擎
- [ ] 实现 ReflectionTrigger
- [ ] 实现 ReflectionEngine（LLM 分析）
- [ ] 创建数据库表 reflection_logs
- [ ] 实现复盘 Prompt 模板

### Phase 3: 规则提炼与验证
- [ ] 实现 RuleDistiller
- [ ] 实现 RuleValidator（统计验证）
- [ ] 实现 LongTermMemory 管理
- [ ] 创建数据库表 distilled_rules

### Phase 4: 参数优化系统
- [ ] 实现 ParameterRegistry
- [ ] 实现 ShadowRunner
- [ ] 创建数据库表 shadow_runs, parameter_history
- [ ] 实现参数切换逻辑

### Phase 5: Dashboard 集成
- [ ] 添加记忆查看页面
- [ ] 添加复盘报告展示
- [ ] 添加规则管理界面
- [ ] 添加参数调整历史查看
