# PnL 优化设计文档

> **版本**: v2（2026-03-04）— 纳入 Codex CLI 审核意见 + 数据库验证结果

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

### 问题1（P0）：杠杆几乎始终为 1x

**现象**：配置 `LEVERAGE_MIN=3, LEVERAGE_MAX=10, DEFAULT_LEVERAGE=5`，但实际交易杠杆分布：

| leverage | 决策数 | 占比 |
|----------|--------|------|
| 1x | 1,081 | 90.5% |
| 3x | 113 | 9.5% |
| 5x | 1 | 0.08% |

注：leverage=3 集中在 2 月 13-19 日，之后全部变为 1x。

**根因验证**（数据库验证 + 代码审查）：

`llm_raw_output` 字段全部为空（未保存），无法直接查看 LLM 原始返回值。但基于以下证据，判定为**多因素问题**：

1. **LLM 主动选择保守杠杆**（主因）：
   - 风险提示词 `prompts/risk.py:22` 写死 "max 5x for confluence > 0.7"，引导 LLM 偏向低杠杆
   - 交易提示词 `prompts/trading.py:98` 虽然传了 `Leverage Range: {leverage_min}x - {leverage_max}x`，但没有**强制指令**要求 LLM 必须在此范围内选择
   - 证据：2 月 13-19 日有 113 笔 leverage=3 的决策，说明 LLM 有能力返回高杠杆，但大多数时候选择了 1

2. **400 重试回退路径**（次因）：
   - `providers/base.py:144-157`：当 LLM 服务返回 400 时，去掉 `response_format`（strict JSON schema）重试
   - 重试后只做 JSON 解析，不做 schema 校验
   - 此时若 LLM 返回的 JSON 缺少 `leverage` 字段，Pydantic 默认值 1 生效
   - 当前使用 qwen-max（dashscope API），该 API 对 `response_format` 的兼容性未知

3. **Pydantic 默认值兜底**（辅因）：
   - `models/decision.py:27` `recommended_leverage: int = 1`
   - `models/decision.py:50` `leverage: int = 1`
   - 无论 LLM 返回什么，代码层面没有 clamp 到 `[leverage_min, leverage_max]` 范围

**影响**：PnL 理论上应为当前的 3-5 倍。

### 问题2（P1）：决策上下文缺失导致胜率低

**现象**：484 笔交易只有 66 笔盈利（13.6%）。

**根因分析**（含 Codex 审核发现的遗漏）：

1. **scheduler 未传关键纪律上下文**（最严重的遗漏）：
   - `scheduler.py:2190-2194` 调用 `analyze_and_decide()` 时，缺少以下参数：
     - `daily_pnl`（默认 0.0）
     - `trades_today`（默认 0）
     - `consecutive_losses`（默认 0）
     - `emotional_state`（默认 "calm"）
   - 但 scheduler 本身已经维护了这些值：`self._daily_pnl`、`self._consecutive_losses`
   - **影响**：LLM 收到的纪律约束上下文全是默认值，无法做出有纪律的决策

2. **风险评估中的占位数据**：
   - `decision.py:151` `recent_trade_count=0`（硬编码 TODO）
   - `decision.py:152` `recent_pnl=0.0`（硬编码 TODO）
   - `decision.py:231` `recent_win_rate=0.0`（硬编码 TODO）
   - **影响**：LLM 永远认为"无最近交易"，无法学习历史表现

3. **缺少 confidence/confluence 硬性过滤**：
   - 提示词要求 "confluence < 0.5 → MUST HOLD"，但代码层面无强制
   - 没有最低 confidence 阈值

### 问题3（P2）：HOLD 过滤效果差

**现象**：76% 的决策是 HOLD，但剩下 24% 的信号胜率仅 13.6%。

**根因**：
- HOLD 决策主要由 LLM 主观判断，缺少基于回测验证的客观过滤规则
- `prompt_enricher` 已正确初始化（`scheduler.py:187`），但 `performance_summary` 数据可能因数据库查询异常或无平仓数据而降级为 "Performance data unavailable"
- 问题不是 "prompt_enricher 未初始化"，而是**数据依赖和降级路径**未处理好

---

## 修复方案

### Phase 1：修复杠杆问题（P0）

#### 1.1 在 response 层补默认值并 clamp（核心修复）

**文件**: `src/ai_trader/ai/decision.py`

**方案**：不修改 Pydantic 模型的默认值（避免硬编码业务配置），而是在原始 response 实例化模型**之前**，按运行时配置补默认值。

在 `_assess_risk()` 的 `return RiskAssessment(**response)` 之前：

```python
# 确保 leverage 在配置范围内（防止 LLM 返回过低/过高或字段缺失使用默认值 1）
if "recommended_leverage" not in response or response["recommended_leverage"] < config.leverage_min:
    response["recommended_leverage"] = config.default_leverage
response["recommended_leverage"] = max(
    config.leverage_min,
    min(config.leverage_max, response["recommended_leverage"])
)
return RiskAssessment(**response)
```

在 `_make_decision()` 的 `decision = TradingDecision(**response)` 之后：

```python
# 强制杠杆在配置范围内
if decision.action in ("open_long", "open_short", "add_long", "add_short"):
    decision.leverage = max(config.leverage_min, min(config.leverage_max, decision.leverage))
```

#### 1.2 优化风险提示词，强制引导杠杆范围

**文件**: `src/ai_trader/prompts/risk.py`

将 RISK_SYSTEM 中硬编码的杠杆规则改为动态引用：

```
## Position Sizing Rules (Fixed Percentage Risk Method)
1. **Risk Per Trade**: 1% for normal trades, 2% for high-confidence setups only
2. **Formula**: Position Size = (Account Balance × Risk %) / (Entry Price - Stop Loss Price)
3. **Leverage Selection** (MANDATORY: must be within [{leverage_min}x, {leverage_max}x]):
   - High Confluence (≥ 0.7): Use higher leverage (up to {leverage_max}x)
   - Medium Confluence (0.5-0.7): Use midpoint leverage
   - Low Confluence (< 0.5): Use {leverage_min}x or recommend HOLD
   ⚠️ NEVER return recommended_leverage < {leverage_min} or > {leverage_max}
4. **Daily Loss Limit**: Stop trading if daily loss exceeds 3% of account balance
```

注意：RISK_SYSTEM 是静态模板，`{leverage_min}` 等占位符需要在 RISK_USER 中通过 format 传入。当前 RISK_USER 已有 `Allowed Leverage: {leverage_min}x - {leverage_max}x`，但 RISK_SYSTEM 中的规则硬编码了 "max 5x"，需要移除硬编码引用改为通用描述。

#### 1.3 保存 LLM 原始输出用于诊断

**文件**: `src/ai_trader/ai/decision.py` 或对应的持久化代码

当前 `llm_raw_output` 字段全部为空，导致无法事后验证 LLM 行为。需要确保在保存决策记录时同时保存原始 JSON 输出。

---

### Phase 2：补齐决策上下文 + 信号过滤（P1）

#### 2.1 scheduler 传入真实纪律上下文（最高优先级）

**文件**: `src/ai_trader/scheduler.py:2190`

当前调用：
```python
decision, tech, risk = await self.decision_engine.analyze_and_decide(
    market_data, position, balance, equity,
    mtf_data=mtf_data,
    trigger_context=trigger_context,
)
```

修改为：
```python
# 计算当前 symbol 的当日 PnL
symbol_daily_pnl = self._daily_pnl.get(symbol, 0.0)
total_daily_pnl = sum(self._daily_pnl.values())

decision, tech, risk = await self.decision_engine.analyze_and_decide(
    market_data, position, balance, equity,
    mtf_data=mtf_data,
    daily_pnl=total_daily_pnl,
    trades_today=self._trades_today,  # 需新增计数器
    consecutive_losses=self._consecutive_losses,
    emotional_state=self._get_emotional_state(),  # 基于连亏等计算
    trigger_context=trigger_context,
)
```

需要新增 `self._trades_today` 计数器（每日重置），以及基于连亏次数推算 emotional_state 的辅助方法。

#### 2.2 补齐风险评估中的占位数据

**文件**: `src/ai_trader/ai/decision.py:151-152`

将 `recent_trade_count=0` 和 `recent_pnl=0.0` 改为从 `prompt_enricher` 或传入参数获取真实值。

可复用已有的 `PromptContextEnricher`（`scheduler.py:187` 已注入）来获取这些数据，避免在 DecisionEngine 中直接访问数据库。

#### 2.3 添加信号质量硬过滤

**文件**: `src/ai_trader/scheduler.py`

**关键要求**（Codex 审核意见）：
1. **过滤必须放在通知之前**，避免先通知 "open_long" 再改成 "hold" 的误通知问题
2. **使用原地修改 `decision.action`**，不要重建 `TradingDecision` 对象（保留原始 reasoning 等上下文）
3. **保留原始决策的可观测性**（日志记录原始 action 和过滤原因）

```python
# 在 LLM 决策返回后、发送通知之前
original_action = decision.action

# Confidence 过滤
if decision.action in ("open_long", "open_short"):
    if decision.confidence < config.min_confidence_to_trade:
        logger.info(
            f"Confidence filter: {decision.action} -> hold "
            f"(confidence={decision.confidence} < {config.min_confidence_to_trade})"
        )
        decision.action = "hold"
        decision.reasoning += f" [FILTERED: low confidence {decision.confidence}]"

# Confluence 过滤
if decision.action in ("open_long", "open_short"):
    if mtf_data and mtf_data.confluence_score < config.min_confluence_to_trade:
        logger.info(
            f"Confluence filter: {decision.action} -> hold "
            f"(confluence={mtf_data.confluence_score} < {config.min_confluence_to_trade})"
        )
        decision.action = "hold"
        decision.reasoning += f" [FILTERED: low confluence {mtf_data.confluence_score:.2f}]"

# 然后发送通知（此时 action 已是最终值）
if self._notification_manager:
    ...
```

#### 2.4 新增配置项

**文件**: `src/ai_trader/config.py`

```python
# 信号质量过滤
min_confidence_to_trade: float = Field(
    default=60.0, validation_alias="MIN_CONFIDENCE_TO_TRADE",
    description="最低 confidence 才允许开仓（从 60 开始，观察后逐步调整）",
)
min_confluence_to_trade: float = Field(
    default=0.5, validation_alias="MIN_CONFLUENCE_TO_TRADE",
    description="最低 confluence score 才允许开仓",
)
```

---

### Phase 3：优化提示词和数据降级（P2）

#### 3.1 修复 performance_summary 数据降级路径

**文件**: `src/ai_trader/prompts/enricher.py`

`PromptContextEnricher` 已正确初始化（`scheduler.py:187`），但当数据库查询失败或无平仓数据时降级为 "Performance data unavailable"。

修复方向：
- 在 `get_performance_summary()` 中添加更详细的降级信息（如 "No closed trades yet" vs "Database error"）
- 确保即使无平仓数据，也能传入当前持仓和当日 PnL 等基础信息
- 添加日志记录降级原因，便于诊断

#### 3.2 优化交易提示词中的开仓条件

**文件**: `src/ai_trader/prompts/trading.py`

调整入场标准（在 Phase 2 的硬过滤基础上，提示词层面也加强约束）：

```
## Opening Conditions (ALL required for new positions):
1. **Multi-Timeframe Alignment**: Confluence score ≥ 0.6 (raised from 0.5)
2. **Clear Trend**: Trend confidence > 65% across at least 2 timeframes (raised from 60%)
3. **Risk Assessment**: should_trade = true, risk_level not "very_high"
4. **Minimum Risk-Reward**: Expected move > 2× total fees AND risk-reward ≥ 2:1
5. **Win Rate Awareness**: If recent win rate < 20%, increase caution and require confluence ≥ 0.75
```

---

## 涉及文件清单

| 文件 | 修改内容 | Phase |
|------|----------|-------|
| `src/ai_trader/ai/decision.py` | response 层 leverage clamp + 补齐占位数据 | P0+P1 |
| `src/ai_trader/prompts/risk.py` | 移除硬编码杠杆上限，强制引导范围 | P0 |
| `src/ai_trader/scheduler.py` | 传入真实纪律上下文 + 信号质量过滤（通知前）| P1 |
| `src/ai_trader/config.py` | 新增 min_confidence/confluence 配置 | P1 |
| `src/ai_trader/prompts/trading.py` | 提高入场标准 | P2 |
| `src/ai_trader/prompts/enricher.py` | 改善数据降级路径和日志 | P2 |

**不修改的文件**：
- `src/ai_trader/models/decision.py` — Pydantic 模型默认值保持 1，不硬编码业务配置。通过 response 层 clamp 解决。

## 预期效果

| 改动 | 预期影响 |
|------|----------|
| leverage clamp（P0）| PnL × 3-5 倍（$600 → $2,000-3,000）|
| 补齐纪律上下文（P1）| LLM 能感知当日 PnL/连亏/交易次数，做出更有纪律的决策 |
| confidence/confluence 过滤（P1）| 减少低质量交易，胜率提升 |
| 补齐 win_rate 等真实数据（P1）| LLM 自适应调整策略 |
| 提示词优化（P2）| 长期提升信号质量 |

## 风险评估

| 风险 | 说明 | 缓解措施 |
|------|------|----------|
| 杠杆放大亏损 | 从 1x 提升到 3-5x，亏损也同比放大 | 先用 `leverage_min=3` 运行 1 周观察 |
| 交易频率降低 | confidence/confluence 过滤可能大幅减少交易 | confidence 阈值从 60 开始，逐步调整 |
| 误通知 | 如果过滤放在通知后，会发"假"开仓通知 | **已解决**：过滤放在通知前 |
| 数据依赖失败 | prompt_enricher 查询数据库异常 | 保留降级路径，添加异常日志 |
| LLM 仍返回低杠杆 | 即使提示词改了，LLM 可能仍偏保守 | **已解决**：代码层 clamp 强制 `[min, max]` |
| 400 重试丢 schema | provider 回退后字段可能缺失 | Pydantic 默认值 1 仍生效，但 clamp 会修正 |

## 实施顺序

1. **Phase 1**：修复杠杆（response 层 clamp + 提示词优化）— 影响最大，风险最低
2. **Phase 2**：补齐上下文 + 信号过滤 — 与 Phase 1 一起部署
3. **Phase 3**：提示词入场标准优化 + 数据降级修复 — Phase 1+2 稳定后再做

## 附录：Codex CLI 审核要点及处理

| 审核意见 | 处理方式 |
|----------|----------|
| P0 根因证据不足 | 已通过数据库验证杠杆分布，确认为多因素问题（LLM 主动选择 + 400 回退 + 默认值），不再简单定性为"Bug" |
| 默认值方案自相矛盾 | 已改为"不修改模型默认值，在 response 层按运行时配置 clamp" |
| 过滤插入点时序问题 | 已改为"过滤放在通知之前"，且使用原地修改 `decision.action` |
| prompt_enricher 分析不准 | 已修正为"已初始化但数据依赖和降级路径问题" |
| 遗漏占位数据 | 已补充 `recent_trade_count`、`recent_pnl`、scheduler 未传 `daily_pnl/trades_today/consecutive_losses` |
