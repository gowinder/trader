# PnL 优化设计文档

> **版本**: v4（2026-03-04）— 纳入三轮 Codex CLI 审核意见 + 数据库验证结果

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

**类型安全处理**（第三轮 Codex 审核）：400 fallback 路径去掉了 `response_format` schema 校验，LLM 可能返回非标类型（字符串 `"3"`、`null`、浮点 `3.5` 等）。因此 clamp 前必须做类型转换：

```python
def _safe_int(value, default: int) -> int:
    """安全地将 LLM 返回值转为 int，处理 400 fallback 可能产生的非标类型"""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default
```

在 `_assess_risk()` 的 `return RiskAssessment(**response)` 之前：

```python
# 类型安全 + leverage clamp
raw_lev = response.get("recommended_leverage")
lev = _safe_int(raw_lev, config.default_leverage)
# 仅当 should_trade=true 时 clamp 到 [min, max]；should_trade=false 时尊重 LLM 的保守信号
if response.get("should_trade", False):
    lev = max(config.leverage_min, min(config.leverage_max, lev))
response["recommended_leverage"] = lev
return RiskAssessment(**response)
```

在 `_make_decision()` 的 `decision = TradingDecision(**response)` 之后：

```python
# 仅对开仓/加仓动作 clamp 杠杆（hold/close 不需要）
# 类型已由 Pydantic field_validator 保证为 int
if decision.action in ("open_long", "open_short", "add_long", "add_short"):
    decision.leverage = max(config.leverage_min, min(config.leverage_max, decision.leverage))
```

**关键设计决策**（第三轮 Codex 审核 Issue #2）：
- 当 `should_trade=false` 时，**不 clamp** `recommended_leverage`。这是因为 LLM 返回 `should_trade=false, leverage=1` 是合理的保守信号，强行改为 5x 是错误的。
- clamp 只在 LLM 明确建议交易（`should_trade=true`）或实际开仓（`action=open_*`）时才生效。

#### 1.2 优化风险提示词，强制引导杠杆范围

**文件**: `src/ai_trader/prompts/risk.py`

**关键约束**：`RISK_SYSTEM` 是常量，在 `decision.py:159` 原样传给 LLM，不做 `format()`。`RISK_USER` 通过 `format()` 传入动态值。因此**动态杠杆规则必须放在 `RISK_USER` 中**，不能放在 `RISK_SYSTEM`。

具体修改：

**RISK_SYSTEM** — 移除硬编码的 "max 5x for confluence > 0.7"，改为通用描述：

```python
RISK_SYSTEM = """...
## Position Sizing Rules (Fixed Percentage Risk Method)
1. **Risk Per Trade**: 1% for normal trades, 2% for high-confidence setups only
2. **Formula**: Position Size = (Account Balance × Risk %) / (Entry Price - Stop Loss Price)
3. **Leverage Selection**: Choose leverage within the allowed range (see Strategy Configuration below).
   Higher confluence allows higher leverage; low confluence should use minimum leverage or HOLD.
4. **Daily Loss Limit**: Stop trading if daily loss exceeds 3% of account balance
..."""
```

**RISK_USER** — 在 `## Strategy Configuration` 区域追加强制指令：

```python
RISK_USER = """...
## Strategy Configuration
- Strategy Type: {strategy_type}
- Allowed Leverage: {leverage_min}x - {leverage_max}x
- Max Position %: {max_position_percent}%
- Default Stop Loss: {stop_loss_percent}%
- Default Take Profit: {take_profit_percent}%

⚠️ MANDATORY: recommended_leverage MUST be between {leverage_min} and {leverage_max}.
- High Confluence (≥ 0.7): Use up to {leverage_max}x
- Medium Confluence (0.5-0.7): Use midpoint ({leverage_mid}x)
- Low Confluence (< 0.5): Use {leverage_min}x or set should_trade=false
..."""
```

`decision.py:130` 的 `RISK_USER.format()` 调用需新增 `leverage_mid` 参数：

```python
leverage_mid=(config.leverage_min + config.leverage_max) // 2,
```

#### 1.3 保存 LLM 原始输出用于诊断

**问题**：当前 `llm_raw_output` 字段全部为空。数据链断裂分析：

1. `providers/base.py:79` `_parse_response()` 接收 `data`（API 原始响应），直接解析 `content` 为 dict 返回，**原始文本被丢弃**
2. `llm_manager.py:328` `chat()` 返回解析后的 dict
3. `decision.py` 用返回的 dict 实例化 `TradingDecision`/`RiskAssessment`
4. `hybrid_decision.py:271` 调 `save_decision()` 时**没有传 `llm_raw_output` 参数**

**修复方案 — 完整透传链路**：

**(a) provider 层保留原始文本**

`providers/base.py:_parse_response()` 返回值中加入 `_raw_content` 字段：

```python
def _parse_response(self, data, schema=None):
    content = data["choices"][0]["message"]["content"]
    result = json.loads(content)  # ... 现有解析逻辑
    result["_raw_content"] = content  # 附加原始文本
    return result
```

**(b) decision.py 保存并剥离**

在 `_make_decision()` 中：

```python
response = await self.llm.chat(...)
raw_content = response.pop("_raw_content", None)  # 剥离后再传给 Pydantic
decision = TradingDecision(**response)
decision._raw_output = raw_content  # 临时属性，供持久化使用
```

注意：`TradingDecision` 是 Pydantic 模型，不能直接 `decision._raw_output`。改用返回时额外携带：

```python
# 在 analyze_and_decide 返回时，将 raw_output 附加到 decision 对象
# 方案：改 analyze_and_decide 返回值为 4 元组，或在 decision 模型中增加 Optional 字段
# 推荐：在 decision 模型中增加不参与序列化的字段
class TradingDecision(BaseModel):
    ...
    _llm_raw_output: Optional[str] = None  # Pydantic private attribute

    class Config:
        # 允许 private attributes
        underscore_attrs_are_private = True
```

实际上 Pydantic v2 使用 `model_config = ConfigDict(...)` 和 `PrivateAttr`：

```python
from pydantic import PrivateAttr

class TradingDecision(BaseModel):
    ...
    _llm_raw_output: str = PrivateAttr(default="")
```

**(c) hybrid_decision.py 传递给 persistence**

`hybrid_decision.py:271` 的 `save_decision()` 调用增加参数：

```python
await self.persistence_service.save_decision(
    decision=decision,
    ...
    llm_raw_output=getattr(decision, '_llm_raw_output', None),
)
```

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
total_daily_pnl = sum(self._daily_pnl.values())

decision, tech, risk = await self.decision_engine.analyze_and_decide(
    market_data, position, balance, equity,
    mtf_data=mtf_data,
    daily_pnl=total_daily_pnl,
    trades_today=self._trades_today,
    consecutive_losses=self._consecutive_losses,
    emotional_state=self._get_emotional_state(),
    trigger_context=trigger_context,
)
```

**新增 `self._trades_today` 计数器**：

```python
# __init__ 中初始化
self._trades_today: int = 0
self._trades_today_date: str = ""

# _run_cycle_for_symbol_impl 中每日重置（同 _daily_pnl 的重置逻辑）
today_str = _dt.utcnow().strftime("%Y-%m-%d")
if today_str != self._trades_today_date:
    self._trades_today = 0
    self._trades_today_date = today_str

# 每次执行订单成功后递增
self._trades_today += 1
```

**新增 `_get_emotional_state()` 方法**：

```python
def _get_emotional_state(self) -> str:
    if self._consecutive_losses >= 5:
        return "fearful"
    elif self._consecutive_losses >= 3:
        return "cautious"
    elif self._trading_halted:
        return "restricted"
    return "calm"
```

#### 2.2 补齐风险评估中的占位数据（含 recent_win_rate）

**文件**: `src/ai_trader/ai/decision.py:151-152, 231`

三个占位数据 `recent_trade_count`、`recent_pnl`、`recent_win_rate` 需要补齐。

**数据来源**：复用已注入的 `self.prompt_enricher`（`PromptContextEnricher`），它已经能从数据库查询历史交易数据。

**方案**：在 `PromptContextEnricher` 中新增 `get_recent_stats()` 方法：

```python
# src/ai_trader/prompts/enricher.py

async def get_recent_stats(self, symbol: str, hours: int = 24) -> dict:
    """获取最近 N 小时的交易统计（用于风险评估和决策上下文）"""
    try:
        rows = await self.db.fetch(
            """
            SELECT realized_pnl
            FROM position_history
            WHERE symbol = $1
              AND status = 'closed'
              AND exit_time >= NOW() - INTERVAL '1 hour' * $2
            ORDER BY exit_time DESC
            """,
            symbol, hours,
        )
    except Exception as e:
        logger.warning(f"Failed to fetch recent stats: {e}")
        return {"trade_count": 0, "total_pnl": 0.0, "win_rate": 0.0}

    if not rows:
        return {"trade_count": 0, "total_pnl": 0.0, "win_rate": 0.0}

    trade_count = len(rows)
    total_pnl = sum(float(r["realized_pnl"] or 0) for r in rows)
    wins = sum(1 for r in rows if (r["realized_pnl"] or 0) > 0)
    win_rate = wins / trade_count if trade_count > 0 else 0.0

    return {"trade_count": trade_count, "total_pnl": total_pnl, "win_rate": win_rate}
```

**在 `decision.py` 中调用**：

`_assess_risk()` 中替换 `recent_trade_count=0` 和 `recent_pnl=0.0`：

```python
# 获取真实的近期交易统计
recent_stats = {"trade_count": 0, "total_pnl": 0.0, "win_rate": 0.0}
if self.prompt_enricher:
    try:
        recent_stats = await self.prompt_enricher.get_recent_stats(market.symbol, hours=1)
    except Exception:
        pass

user_prompt = RISK_USER.format(
    ...
    recent_trade_count=recent_stats["trade_count"],
    recent_pnl=f"{recent_stats['total_pnl']:+.2f}",
    ...
)
```

`_make_decision()` 中替换 `recent_win_rate=0.0`：

```python
# 获取最近 50 笔交易的胜率（更长时间窗口）
recent_win_rate = 0.0
if self.prompt_enricher:
    try:
        perf = await self.prompt_enricher.get_recent_stats(market.symbol, hours=168)  # 7天
        recent_win_rate = perf["win_rate"] * 100  # 转换为百分比
    except Exception:
        pass
```

#### 2.3 统一所有 action 改写到通知之前

**文件**: `src/ai_trader/scheduler.py`

**关键要求**（第二轮 Codex 审核）：不仅新增的 confidence/confluence 过滤要放在通知前，**现有的所有 action 改写逻辑也必须移到通知前**，包括：
- 每日亏损拦截（`scheduler.py:2208`，当前在通知后）
- `SignalFilter` 过滤（`scheduler.py:2214-2229`，当前在通知后）

**重构后的执行顺序**：

```python
# ── 2. 决策（含多时间框架数据）──
decision, tech, risk = await self.decision_engine.analyze_and_decide(...)

# ── 3. 所有 rule-based 过滤（统一在通知前）──
original_action = decision.action

# 3a. Confidence 过滤
if decision.action in ("open_long", "open_short"):
    if decision.confidence < _cfg.get("min_confidence_to_trade", 60.0):
        logger.info(f"Confidence filter: {decision.action} -> hold")
        decision.action = "hold"
        decision.reasoning += f" [FILTERED: low confidence {decision.confidence}]"

# 3b. Confluence 过滤
if decision.action in ("open_long", "open_short"):
    if mtf_data and mtf_data.confluence_score < _cfg.get("min_confluence_to_trade", 0.5):
        logger.info(f"Confluence filter: {decision.action} -> hold")
        decision.action = "hold"
        decision.reasoning += f" [FILTERED: low confluence {mtf_data.confluence_score:.2f}]"

# 3c. 每日亏损限制拦截（从通知后移到通知前）
if self._trading_halted and decision.action in ("open_long", "open_short"):
    logger.info(f"Daily loss limit: {decision.action} -> hold")
    decision.action = "hold"
    decision.reasoning += "\n[DailyLossLimit] 当日亏损限制已触发，禁止开新仓"

# 3d. SignalFilter 过滤（从通知后移到通知前）
if decision.action in ("open_long", "open_short"):
    if symbol not in self._signal_filters:
        self._signal_filters[symbol] = SignalFilter(
            min_interval_hours=_cfg["signal_min_interval_hours"],
            reverse_cooldown_hours=_cfg["signal_reverse_cooldown_hours"],
        )
    sf = self._signal_filters[symbol]
    action_map = {"open_long": SignalAction.LONG, "open_short": SignalAction.SHORT}
    allowed, filter_reason = sf.should_allow_signal(action_map[decision.action], _dt.utcnow())
    if not allowed:
        logger.info(f"[SignalFilter] {symbol} {decision.action} -> hold: {filter_reason}")
        decision.action = "hold"
        decision.reasoning += f"\n[SignalFilter] {filter_reason}"

# 3e. 记录过滤结果
if decision.action != original_action:
    logger.info(f"Action changed: {original_action} -> {decision.action}")

# ── 4. 发送通知（此时 action 已是最终值）──
if self._notification_manager:
    await self._notification_manager.notify_decision(
        symbol=symbol,
        action=decision.action,
        confidence=decision.confidence,
        reasoning=decision.reasoning_zh or decision.reasoning,
    )

# ── 5. 执行 ──
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

#### 2.5 `_cfg` 快照补齐新配置项（第三轮 Codex 审核 Issue #1）

**文件**: `src/ai_trader/scheduler.py:2004-2014`

当前 `_cfg` 快照缺少新增的 `min_confidence_to_trade` 和 `min_confluence_to_trade`，导致 Phase 2.3 中的 confidence/confluence 过滤使用 `_cfg.get("min_confidence_to_trade", 60.0)` 时始终走默认值，**配置修改不会生效**。

**修复**：在 `_cfg` 字典中添加：

```python
_cfg = {
    "analysis_interval": config.analysis_interval,
    "stop_loss_percent": config.stop_loss_percent,
    "take_profit_percent": config.take_profit_percent,
    "leverage_max": config.leverage_max,
    "leverage_min": config.leverage_min,              # 新增：leverage clamp 需要
    "default_leverage": config.default_leverage,      # 新增：leverage clamp 需要
    "ai_weight": config.ai_weight,
    "quant_weight": config.quant_weight,
    "daily_loss_limit_percent": config.daily_loss_limit_percent,
    "signal_min_interval_hours": config.signal_min_interval_hours,
    "signal_reverse_cooldown_hours": config.signal_reverse_cooldown_hours,
    "min_confidence_to_trade": config.min_confidence_to_trade,    # 新增
    "min_confluence_to_trade": config.min_confluence_to_trade,    # 新增
}
```

注：同时补充了 `leverage_min` 和 `default_leverage`，Phase 1 的 clamp 逻辑如果从 `_cfg` 取值也需要这些字段。

---

### Phase 3：优化提示词和数据降级（P2）

#### 3.1 修复 performance_summary 数据降级路径

**文件**: `src/ai_trader/prompts/enricher.py`

当前 `get_performance_summary(symbol, limit=20)` 只查询平仓历史。需要扩展以支持传入当前持仓和当日 PnL。

**方案**：新增 `get_enhanced_performance_summary()` 方法，扩展签名以接受额外上下文：

```python
async def get_enhanced_performance_summary(
    self,
    symbol: str,
    limit: int = 20,
    current_position: Optional[dict] = None,
    daily_pnl: float = 0.0,
) -> str:
    """获取增强版表现摘要（含当前持仓和当日 PnL）"""
    base = await self.get_performance_summary(symbol, limit)

    extra_lines = []
    if daily_pnl != 0.0:
        extra_lines.append(f"Today's PnL: {daily_pnl:+.2f} USDT")
    if current_position:
        side = current_position.get("side", "unknown")
        upnl = current_position.get("unrealized_pnl", 0)
        extra_lines.append(f"Current position: {side}, unrealized PnL: {upnl:+.2f} USDT")

    if extra_lines:
        return base + "\n" + "\n".join(extra_lines)
    return base
```

**在 `decision.py:236` 调用时传入额外参数**：

```python
if self.prompt_enricher:
    try:
        pos_dict = None
        if pos:
            pos_dict = {"side": pos.side, "unrealized_pnl": pos.unrealized_pnl}
        performance_summary = await self.prompt_enricher.get_enhanced_performance_summary(
            market.symbol, current_position=pos_dict, daily_pnl=daily_pnl
        )
        active_rules = await self.prompt_enricher.get_active_rules()
    except Exception as e:
        logger.warning(f"Prompt enricher failed: {e}")
        performance_summary = "Performance data unavailable (enricher error)"
        active_rules = "No validated rules yet"
```

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

注：第 5 条的 `recent win rate` 数据来源已在 Phase 2.2 中定义（通过 `prompt_enricher.get_recent_stats()`），不存在数据源缺失问题。

---

## 涉及文件清单

| 文件 | 修改内容 | Phase |
|------|----------|-------|
| `src/ai_trader/ai/decision.py` | response 层 leverage clamp + 补齐占位数据 + raw_output 透传 | P0+P1 |
| `src/ai_trader/prompts/risk.py` | RISK_SYSTEM 移除硬编码杠杆；RISK_USER 追加杠杆强制指令 | P0 |
| `src/ai_trader/scheduler.py` | 传入真实纪律上下文 + 统一所有 action 改写到通知前 | P1 |
| `src/ai_trader/config.py` | 新增 min_confidence/confluence 配置 | P1 |
| `src/ai_trader/prompts/enricher.py` | 新增 `get_recent_stats()` + `get_enhanced_performance_summary()` | P1+P2 |
| `src/ai_trader/ai/providers/base.py` | `_parse_response()` 保留 `_raw_content` | P0 |
| `src/ai_trader/ai/hybrid_decision.py` | `save_decision()` 传递 `llm_raw_output` | P0 |
| `src/ai_trader/models/decision.py` | `TradingDecision` 增加 `_llm_raw_output` PrivateAttr | P0 |
| `src/ai_trader/prompts/trading.py` | 提高入场标准 | P2 |

**不修改的文件**：
- `src/ai_trader/models/decision.py` 的默认杠杆值 — 保持 1，不硬编码业务配置。通过 response 层 clamp 解决。

## 预期效果

| 改动 | 预期影响 |
|------|----------|
| leverage clamp（P0）| PnL × 3-5 倍（$600 → $2,000-3,000）|
| 补齐纪律上下文（P1）| LLM 能感知当日 PnL/连亏/交易次数，做出更有纪律的决策 |
| confidence/confluence 过滤（P1）| 减少低质量交易，胜率提升 |
| 补齐 win_rate 等真实数据（P1）| LLM 自适应调整策略 |
| 统一 action 改写时序（P1）| 消除误通知问题 |
| llm_raw_output 保存（P0）| 支持事后诊断 LLM 行为 |
| 提示词优化（P2）| 长期提升信号质量 |

## 风险评估

| 风险 | 说明 | 缓解措施 |
|------|------|----------|
| 杠杆放大亏损 | 从 1x 提升到 3-5x，亏损也同比放大 | 先用 `leverage_min=3` 运行 1 周观察 |
| 交易频率降低 | confidence/confluence 过滤可能大幅减少交易 | confidence 阈值从 60 开始，逐步调整 |
| 通知时序变更 | 现有 action 改写逻辑移到通知前，通知行为会变 | 变更本身是修正，但需确认外部系统无依赖 |
| 数据依赖失败 | prompt_enricher 查询数据库异常 | 所有新增查询都有 try/except 降级，返回默认值 |
| LLM 仍返回低杠杆 | 即使提示词改了，LLM 可能仍偏保守 | 代码层 clamp 强制 `[min, max]` 兜底 |
| 400 重试丢 schema | provider 回退后字段可能缺失 | Pydantic 默认值 1 仍生效，但 clamp 会修正 |
| raw_output 体积 | 每笔决策多存一个文本字段 | 数据库已有 `llm_raw_output text` 列，无额外 schema 变更 |

## 实施顺序

1. **Phase 1**：修复杠杆（response 层 clamp + 提示词优化 + raw_output 保存）— 影响最大，风险最低
2. **Phase 2**：补齐上下文 + 信号过滤 + 统一 action 改写时序 — 与 Phase 1 一起部署
3. **Phase 3**：提示词入场标准优化 + 数据降级修复 — Phase 1+2 稳定后再做

## 附录：Codex CLI 审核要点及处理

### 第一轮审核（v1 → v2）

| 审核意见 | 处理方式 |
|----------|----------|
| P0 根因证据不足 | 已通过数据库验证杠杆分布，确认为多因素问题 |
| 默认值方案自相矛盾 | 已改为 response 层按运行时配置 clamp |
| 过滤插入点时序问题 | 部分解决（见第二轮） |
| prompt_enricher 分析不准 | 已修正为"已初始化但数据依赖问题" |
| 遗漏占位数据 | 部分补充（见第二轮） |

### 第二轮审核（v2 → v3）

| 审核意见 | 处理方式 |
|----------|----------|
| RISK_SYSTEM 动态占位不可行 | 已明确：动态杠杆规则放在 RISK_USER 中，RISK_SYSTEM 只保留通用描述 |
| 过滤时序未彻底解决 | 已将**所有** action 改写逻辑（含日亏损拦截、SignalFilter）统一移到通知前 |
| `recent_win_rate` 无落地方案 | 已定义：通过 `enricher.get_recent_stats()` 获取，时间窗口 7 天，转百分比后传入 |
| `performance_summary` 接口不够 | 已新增 `get_enhanced_performance_summary()` 方法，扩展签名接受持仓和当日 PnL |
| `llm_raw_output` 透传链路未定义 | 已定义完整链路：provider 保留 → decision 剥离存 PrivateAttr → hybrid_decision 传给 persistence |

### 第三轮审核（v3 → v4）

| 审核意见 | 处理方式 |
|----------|----------|
| `_cfg` 快照遗漏 `min_confidence_to_trade`/`min_confluence_to_trade` | 已在 2.5 节补充：`_cfg` 字典新增 4 个字段（含 `leverage_min`、`default_leverage`） |
| leverage clamp 不应在 `should_trade=false` 时强改保守信号 | 已在 1.1 节修改：`_assess_risk()` 的 clamp 加 `if response.get("should_trade", False)` 条件 |
| clamp 代码对 400 fallback 返回的非标类型不安全 | 已在 1.1 节新增 `_safe_int()` 辅助函数，处理 `None`/string/float 等非标类型 |
