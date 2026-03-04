# PnL 优化设计文档

## 问题背景

测试资金 $10,000，运行 1 个月，PnL 仅 $646（月收益率 6%）。

### 实际交易数据（30天）

| 指标 | 数值 |
|------|------|
| 总决策次数 | 5,440 |
| HOLD 决策 | 4,136（76%）|
| 开仓信号 | 1,194（22%）|
| 实际成交 | 484 笔 |
| 胜率 | 13.6%（66 胜 / 416 负）|
| 平均盈利 | +$17.98（+1.48%）|
| 平均亏损 | -$6.36（-0.56%）|
| 盈亏比 | 2.8:1 |
| 实际杠杆 | 1.0-1.5x |
| 平均仓位 | ~$1,100 |
| 持仓时长 | 中位数 17h，均值 30.5h |

### 各币种表现

| 币种 | 交易数 | PnL | 胜率 |
|------|--------|-----|------|
| BTC | 167 | $30.50 | 15.0% |
| ETH | 143 | $303.51 | 11.2% |
| SOL | 172 | $312.31 | 14.5% |

---

## 根因分析

### 问题1（P0）：杠杆始终为 1x — Bug

**现象**：配置 `LEVERAGE_MIN=3, LEVERAGE_MAX=10, DEFAULT_LEVERAGE=5`，但实际所有交易都是 1x 杠杆。

**根因**：`src/ai_trader/models/decision.py` 中两个模型的默认值硬编码为 1：

```python
# 第 27 行
class RiskAssessment(BaseModel):
    recommended_leverage: int = 1  # 应该用 config.default_leverage

# 第 50 行
class TradingDecision(BaseModel):
    leverage: int = 1  # 应该用 config.default_leverage
```

当 LLM 返回的 JSON 缺少 `leverage` 字段或解析失败时，Pydantic 使用默认值 1。

同时，风险评估提示词 `prompts/risk.py` 中写死了 "max 5x for confluence > 0.7"，没有动态引用配置的 `leverage_min/max`。

**影响**：PnL 理论上应为当前的 3-5 倍。

### 问题2（P1）：胜率极低 13.6%

**现象**：484 笔交易只有 66 笔盈利。虽然盈亏比 2.8:1 使系统整体盈利，但大量亏损交易拖累了资本效率。

**根因分析**：
1. LLM 入场判断质量不够 — 没有最低 confidence 阈值来过滤低质量信号
2. 提示词要求 "confluence ≥ 0.5" 才能交易，但没有硬性代码约束
3. `recent_win_rate` 始终传 0.0（`decision.py:231` 写的 TODO），LLM 无法根据实际胜率调整策略
4. 交易决策提示词中 `Leverage Range: {leverage_min}x - {leverage_max}x` 虽然传了配置，但 LLM 倾向于保守返回低杠杆

### 问题3（P2）：HOLD 比例过高但未能有效过滤

**现象**：76% 的决策是 HOLD，但剩下的 24% 信号中胜率仍只有 13.6%，说明 HOLD 过滤器并没有选出高质量信号。

**根因**：HOLD 决策主要由 LLM 主观判断，没有基于回测验证的客观过滤规则。

---

## 修复方案

### Phase 1：修复杠杆 Bug（P0）

#### 1.1 修改模型默认值

**文件**: `src/ai_trader/models/decision.py`

```python
class RiskAssessment(BaseModel):
    """风险评估结果"""
    risk_level: ...
    risk_score: ...
    recommended_leverage: int = Field(default=3, ge=1, le=20)  # 改为 leverage_min
    ...

class TradingDecision(BaseModel):
    """最终交易决策"""
    ...
    leverage: int = Field(default=3, ge=1, le=20)  # 改为 leverage_min
    ...

    @field_validator("leverage")
    @classmethod
    def validate_leverage(cls, v):
        if v < 1:
            return 1
        if v > 20:
            return 20
        return v
```

注意：Pydantic 模型的默认值不能直接引用 config（模型定义时 config 可能未初始化），所以默认值设为 `leverage_min` 的默认值 3。

#### 1.2 在决策后强制约束杠杆范围

**文件**: `src/ai_trader/ai/decision.py`，在 `_make_decision()` 返回前添加：

```python
# 强制杠杆在配置范围内
decision.leverage = max(config.leverage_min, min(config.leverage_max, decision.leverage))
```

同样在 `_assess_risk()` 返回前添加：

```python
risk.recommended_leverage = max(config.leverage_min, min(config.leverage_max, risk.recommended_leverage))
```

#### 1.3 优化风险提示词

**文件**: `src/ai_trader/prompts/risk.py`

将硬编码的 "max 5x for confluence > 0.7" 改为动态引用：

```
## Position Sizing Rules
3. **Leverage Adjustment**: Use leverage within the configured range ({leverage_min}x - {leverage_max}x).
   - Low risk (confluence ≥ 0.7): Use {leverage_max}x
   - Medium risk (confluence 0.5-0.7): Use midpoint leverage
   - High risk (confluence < 0.5): Use {leverage_min}x or recommend HOLD
```

同时明确告诉 LLM **必须**返回 `recommended_leverage` 字段，且值必须在 `[leverage_min, leverage_max]` 范围内。

---

### Phase 2：提升胜率（P1）

#### 2.1 添加 confidence 硬性阈值

**文件**: `src/ai_trader/scheduler.py`，在执行交易前添加过滤：

```python
# 在信号过滤之后、下单之前
MIN_CONFIDENCE_TO_TRADE = 65.0  # 可配置

if decision.action in ("open_long", "open_short"):
    if decision.confidence < MIN_CONFIDENCE_TO_TRADE:
        logger.info(f"Skipping {decision.action}: confidence {decision.confidence} < {MIN_CONFIDENCE_TO_TRADE}")
        decision = TradingDecision(action="hold", confidence=decision.confidence, ...)
```

#### 2.2 硬性 confluence 过滤

**文件**: `src/ai_trader/scheduler.py`

当前提示词说 "Low Confluence (<0.5) → MUST HOLD"，但代码层面没有强制。添加：

```python
if mtf_data and mtf_data.confluence_score < 0.5:
    if decision.action in ("open_long", "open_short"):
        logger.info(f"Forcing HOLD: confluence {mtf_data.confluence_score} < 0.5")
        decision = TradingDecision(action="hold", ...)
```

#### 2.3 传入真实 win_rate

**文件**: `src/ai_trader/ai/decision.py:231`

当前 `recent_win_rate = 0.0  # TODO`，需要从数据库查询实际胜率：

```python
# 从持久化服务获取最近 N 笔交易的胜率
recent_win_rate = await self._get_recent_win_rate(market.symbol, lookback=50)
```

#### 2.4 新增配置项

**文件**: `src/ai_trader/config.py`

```python
# 信号质量过滤
min_confidence_to_trade: float = Field(
    default=65.0, validation_alias="MIN_CONFIDENCE_TO_TRADE",
    description="最低 confidence 才允许开仓",
)
min_confluence_to_trade: float = Field(
    default=0.5, validation_alias="MIN_CONFLUENCE_TO_TRADE",
    description="最低 confluence score 才允许开仓",
)
```

---

### Phase 3：优化 HOLD 过滤效果（P2）

#### 3.1 将 HOLD 规则从 LLM 主观判断改为混合判断

当前 LLM 的 HOLD 决策是主观的，不可控。方案：

**在 `decision.py` 的 `_make_decision()` 中，给 LLM 传入当前实际胜率数据**，让 LLM 看到自己的历史表现来调整策略。

当前已有 `performance_summary` 和 `active_rules` 字段，但 `performance_summary` 实际内容是 "Performance data unavailable"（如果 prompt_enricher 未配置）。

**修复**：确保 `prompt_enricher` 正确初始化并传入真实数据。

#### 3.2 优化交易提示词中的开仓条件

**文件**: `src/ai_trader/prompts/trading.py`

当前条件过于宽泛，调整为更精确的入场标准：

```
## Opening Conditions (ALL required for new positions):
1. **Multi-Timeframe Alignment**: Confluence score ≥ 0.6 (raised from 0.5)
2. **Clear Trend**: Trend confidence > 65% across at least 2 timeframes (raised from 60%)
3. **Risk Assessment**: should_trade = true, risk_level must be "low" or "very_low" (tightened from "not very_high")
4. **Minimum Risk-Reward**: Expected move > 2× total fees AND risk-reward ≥ 2:1
5. **Win Rate Awareness**: If recent win rate < 20%, require confluence ≥ 0.75
```

---

## 涉及文件清单

| 文件 | 修改内容 | Phase |
|------|----------|-------|
| `src/ai_trader/models/decision.py` | 修改默认杠杆值，添加范围约束 | P0 |
| `src/ai_trader/ai/decision.py` | 强制杠杆范围、传入真实胜率 | P0+P1 |
| `src/ai_trader/prompts/risk.py` | 动态杠杆范围、强调必须返回 leverage | P0 |
| `src/ai_trader/prompts/trading.py` | 提高入场标准、胜率感知 | P2 |
| `src/ai_trader/config.py` | 新增 min_confidence/confluence 配置 | P1 |
| `src/ai_trader/scheduler.py` | 添加 confidence/confluence 硬性过滤 | P1 |

## 预期效果

| 改动 | 预期影响 |
|------|----------|
| 修复杠杆（P0）| PnL × 3-5 倍（$600 → $2,000-3,000）|
| confidence 阈值（P1）| 减少 30-50% 低质量交易，胜率提升至 20-25% |
| confluence 硬过滤（P1）| 避免趋势不明时开仓 |
| 真实胜率反馈（P1）| LLM 自适应调整策略 |
| 提示词优化（P2）| 长期提升信号质量 |

## 风险评估

- **P0 杠杆修复**：风险低，但杠杆提高意味着亏损也放大。建议先用 3x 默认值运行 1 周观察。
- **P1 过滤阈值**：可能导致交易频率大幅降低。建议 confidence 阈值从 60 开始，逐步调到 65。
- **P2 提示词调整**：效果依赖 LLM 对提示词的理解，需要监控胜率变化。

## 实施顺序

1. Phase 1：修复杠杆 Bug（必须先做，影响最大）
2. Phase 2：添加信号质量过滤（需要与 Phase 1 一起部署观察）
3. Phase 3：优化提示词和 HOLD 策略（Phase 1+2 稳定后再做）
