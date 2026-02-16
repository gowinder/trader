# 交易系统架构审核与改进设计

> 日期: 2026-02-15
> 范围: 全系统架构审核，覆盖 P0-P3 共 16 个问题的修复方案

---

## 问题总览

| # | 问题 | 严重度 | 优先级 |
|---|------|--------|--------|
| 1 | 每日亏损限制未启用 | 🔴 | P0 |
| 2 | SignalFilter 未集成主循环 | 🔴 | P0 |
| 3 | ShadowRunner 仅初始化从未调用 | 🟠 | P1 |
| 4 | 复盘结果只存不用 | 🟠 | P1 |
| 5 | 回测结果孤立 | 🟡 | P2 |
| 6 | AI 决策 Prompt 静态无反馈 | 🟠 | P1 |
| 7 | Distilled Rules 无消费者 | 🟡 | P2 |
| 8 | 配置更新非原子性 | 🟠 | P1 |
| 9 | Advisory 与主循环决策矛盾 | 🟡 | P2 |
| 10 | 多交易对 Testnet 虚拟账户不准 | 🟡 | P2 |
| 11 | 策略权重硬编码 | 🟡 | P2 |
| 12 | 决策阈值无自适应 | 🟡 | P2 |
| 13 | 平仓信号融合缺陷 | 🟠 | P1 |
| 14 | 缺少回测→实盘闭环验证 | 🔵 | P3 |
| 15 | 缺少性能基线追踪 | 🔵 | P3 |
| 16 | LLM 输出质量监控 | 🔵 | P3 |

---

## Phase 1: P0 — 资金安全（#1, #2）

### 1.1 每日亏损限制集成

**现状**: `PositionManager.check_daily_loss_limit()` 完整实现但从未被调用。

**方案**:

#### 1.1.1 新增每日盈亏追踪器

在 `scheduler.py` 中维护每日累计盈亏，每个交易日 00:00 UTC 重置：

```python
# scheduler.py 新增属性
self._daily_pnl: Dict[str, float] = {}  # symbol -> 当日累计盈亏
self._daily_pnl_date: str = ""           # 当前日期 YYYY-MM-DD
self._trading_halted: bool = False        # 当日是否已触发亏损限制
self._halt_until: Optional[datetime] = None  # 连续触发时的强制休息截止时间
```

#### 1.1.2 在主循环决策前检查

在 `_run_cycle_for_symbol_impl` 中，**止损止盈检查之后、LLM 决策之前**插入：

```python
# scheduler.py _run_cycle_for_symbol_impl 中插入
# ── 每日亏损限制检查 ──
if self._trading_halted:
    if self._halt_until and datetime.now() < self._halt_until:
        logger.warning(f"强制休息中，截止: {self._halt_until}")
        return
    else:
        self._trading_halted = False
        self._halt_until = None

daily_pnl_total = sum(self._daily_pnl.values())
should_halt, reason = self.position_mgr.check_daily_loss_limit(
    daily_pnl=daily_pnl_total,
    account_balance=total_equity,
)
if should_halt:
    self._trading_halted = True
    logger.warning(f"每日亏损限制触发: {reason}")
    if self._notification_manager:
        await self._notification_manager.notify_alert(
            f"⚠️ 每日亏损限制触发: {reason}\n当日累计亏损: {daily_pnl_total:.2f} USDT"
        )
    return  # 跳过本轮决策
```

#### 1.1.3 平仓时累加每日盈亏

在 `_persist_position_change` 的平仓逻辑中：

```python
# 平仓成功后累加
self._daily_pnl[symbol] = self._daily_pnl.get(symbol, 0) + pnl
```

#### 1.1.4 每日重置

在主循环 `_run_trading_loop` 开头检查日期变化：

```python
today = datetime.utcnow().strftime("%Y-%m-%d")
if today != self._daily_pnl_date:
    self._daily_pnl = {}
    self._daily_pnl_date = today
    self._trading_halted = False
    logger.info(f"新交易日: {today}, 每日统计已重置")
```

#### 1.1.5 配置项暴露

在 `config.py` 新增：

```python
daily_loss_limit_percent: float = Field(default=3.0, description="每日最大亏损百分比")
consecutive_halt_days_for_break: int = Field(default=2, description="连续触发多少天后强制休息")
forced_break_days: int = Field(default=7, description="强制休息天数")
```

---

### 1.2 SignalFilter 集成主循环

**现状**: `SignalFilter` 仅在回测中使用，主循环无时间维度信号过滤。

**方案**:

#### 1.2.1 在 Scheduler 初始化 SignalFilter

```python
# scheduler.py __init__
from ..strategies.strategy_base import SignalFilter
self._signal_filters: Dict[str, SignalFilter] = {}  # 每个 symbol 独立过滤器
```

#### 1.2.2 在决策执行前过滤

在 `_run_cycle_for_symbol_impl` 中，**LLM 决策返回后、执行订单前**插入：

```python
# 获取该 symbol 的信号过滤器
if symbol not in self._signal_filters:
    self._signal_filters[symbol] = SignalFilter(
        min_interval_hours=config.signal_min_interval_hours
    )
signal_filter = self._signal_filters[symbol]

# 过滤信号
if decision.action not in ("hold", "close_long", "close_short"):
    from ..strategies.strategy_base import SignalAction
    action_map = {
        "open_long": SignalAction.LONG,
        "open_short": SignalAction.SHORT,
    }
    signal_action = action_map.get(decision.action)
    if signal_action:
        allowed, filter_reason = signal_filter.should_allow_signal(
            signal_action, datetime.now()
        )
        if not allowed:
            logger.info(f"信号被过滤: {decision.action} -> hold, 原因: {filter_reason}")
            decision.action = "hold"
            decision.reasoning += f"\n[Signal Filter] {filter_reason}"
```

#### 1.2.3 成功执行后更新过滤器状态

```python
# 订单执行成功后
if order_result and decision.action in ("open_long", "open_short"):
    signal_filter.record_trade(action_map[decision.action], datetime.now())
```

#### 1.2.4 新增配置项

```python
# config.py
signal_min_interval_hours: float = Field(default=4.0, description="同方向信号最小间隔（小时）")
signal_reverse_cooldown_hours: float = Field(default=12.0, description="反向信号冷却时间（小时）")
```

---

## Phase 2: P1 — 自优化闭环与决策修复（#3, #4, #6, #8, #13）

### 2.1 打通复盘 → 影子验证 → 参数应用管线（#3, #4）

**现状**: 复盘结果存 DB 后断裂，ShadowRunner 未被调用。

**方案**: 在复盘完成后自动启动影子运行验证，验证通过后自动应用参数。

#### 2.1.1 新增 OptimizationOrchestrator

创建 `src/ai_trader/optimization/orchestrator.py`：

```python
class OptimizationOrchestrator:
    """编排 复盘 → 影子验证 → 参数应用 的完整闭环"""

    def __init__(self, db: DatabaseManager, shadow_runner: ShadowRunner,
                 parameter_registry: ParameterRegistry):
        self.db = db
        self.shadow_runner = shadow_runner
        self.registry = parameter_registry

    async def handle_reflection_result(self, reflection_result: dict):
        """处理复盘结果，决定是否启动影子验证"""
        suggestions = reflection_result.get("parameter_suggestions", {})
        if not suggestions:
            return

        # 过滤只保留在 ParameterRegistry 中注册的参数
        valid_suggestions = {}
        for param_name, detail in suggestions.items():
            param = self.registry.get(param_name)
            if param and param.is_within_bounds(detail.get("new_value", 0)):
                valid_suggestions[param_name] = detail

        if not valid_suggestions:
            logger.info("复盘参数建议均不在合法范围内，跳过")
            return

        # 构建候选参数
        current_params = self.registry.to_dict()
        candidate_params = current_params.copy()
        for name, detail in valid_suggestions.items():
            candidate_params[name] = detail["new_value"]

        # 启动影子运行
        if not self.shadow_runner.is_running:
            run_id = await self.shadow_runner.start(current_params, candidate_params)
            logger.info(f"从复盘结果启动影子运行: {run_id}, 候选参数: {valid_suggestions}")

    async def evaluate_and_apply(self) -> Optional[dict]:
        """评估影子运行结果，通过则自动应用"""
        if not self.shadow_runner.is_running:
            return None

        result = self.shadow_runner.evaluate()
        if result.get("should_switch"):
            # 应用新参数
            candidate = self.shadow_runner._candidate_params
            for name, value in candidate.items():
                old = self.registry.get(name)
                if old:
                    self.registry.update(name, value, reason="shadow_run_validated")
                    # 同步到 runtime config
                    if hasattr(config, name):
                        setattr(config, name, value)

            # 记录参数变更到 DB
            await self._save_parameter_changes(candidate, result)
            await self.shadow_runner.complete(switched=True, conclusion="验证通过，自动切换")

            # 发布配置更新事件
            await self._publish_config_update()

            logger.info(f"影子运行验证通过，参数已自动切换")
            return result

        # 检查是否样本足够但不达标
        stats = result.get("stats", {})
        if stats.get("candidate_trades", 0) >= self.shadow_runner.MIN_TRADES:
            await self.shadow_runner.complete(switched=False, conclusion="验证不通过")
            logger.info("影子运行验证不通过，保持原参数")

        return None
```

#### 2.1.2 集成到 Scheduler

在 `scheduler.py` 中：

```python
# 初始化时创建编排器
if config.enable_auto_optimization:
    self.optimization_orchestrator = OptimizationOrchestrator(
        db=self.db_manager,
        shadow_runner=self.shadow_runner,
        parameter_registry=ParameterRegistry(),
    )

# 复盘任务完成后（监听 Redis 队列 reflection:results）
async def _reflection_results_listener(self):
    while self.running:
        result = await self._redis.brpop("reflection:results", timeout=5)
        if result:
            reflection_data = json.loads(result[1])
            await self.optimization_orchestrator.handle_reflection_result(reflection_data)

# 每次交易完成后，记录影子运行数据
if self.shadow_runner and self.shadow_runner.is_running:
    self.shadow_runner.record_current_result(is_winner=pnl > 0, pnl=pnl_percent)
    # 用候选参数模拟判断（简化版：对比止损/止盈距离）
    # ... 候选结果记录
    eval_result = await self.optimization_orchestrator.evaluate_and_apply()
```

#### 2.1.3 ReflectionEngine 输出写入 Redis 队列

修改 `reflection/engine.py`，复盘完成后将结果推入队列：

```python
# engine.py run_reflection 末尾新增
async def run_reflection(self, memories):
    ...
    # 推入结果队列供 orchestrator 消费
    if hasattr(self, 'redis') and self.redis:
        await self.redis.lpush("reflection:results", json.dumps(result))
    return result
```

---

### 2.2 Prompt 动态注入历史表现（#6）

**现状**: `TRADING_SYSTEM` / `TRADING_USER` 是静态字符串，AI 看不到自己的历史。

**方案**: 在 `TRADING_USER` prompt 中动态注入"历史表现摘要"和"已验证规则"。

#### 2.2.1 新增 PromptContextEnricher

创建 `src/ai_trader/prompts/enricher.py`：

```python
class PromptContextEnricher:
    """动态丰富 AI 决策 prompt 上下文"""

    def __init__(self, db: DatabaseManager):
        self.db = db

    async def get_performance_summary(self, symbol: str, limit: int = 20) -> str:
        """获取近期表现摘要"""
        rows = await self.db.fetch("""
            SELECT action, pnl_percent, market_state, is_winner,
                   hour_of_day, confidence
            FROM trade_memory
            WHERE symbol = $1
            ORDER BY timestamp DESC LIMIT $2
        """, symbol, limit)

        if not rows:
            return "无历史交易数据"

        total = len(rows)
        wins = sum(1 for r in rows if r["is_winner"])
        avg_pnl = sum(r["pnl_percent"] or 0 for r in rows) / total
        win_rate = wins / total * 100

        # 按市场状态分析
        state_perf = {}
        for r in rows:
            state = r["market_state"] or "unknown"
            if state not in state_perf:
                state_perf[state] = {"trades": 0, "wins": 0, "pnl": 0}
            state_perf[state]["trades"] += 1
            if r["is_winner"]:
                state_perf[state]["wins"] += 1
            state_perf[state]["pnl"] += r["pnl_percent"] or 0

        state_lines = []
        for state, perf in state_perf.items():
            wr = perf["wins"] / perf["trades"] * 100 if perf["trades"] > 0 else 0
            avg = perf["pnl"] / perf["trades"] if perf["trades"] > 0 else 0
            state_lines.append(
                f"  - {state}: {perf['trades']} trades, "
                f"win rate {wr:.0f}%, avg PnL {avg:+.2f}%"
            )

        # 最近失败模式
        recent_losses = [r for r in rows[:10] if not r["is_winner"]]
        loss_pattern = ""
        if len(recent_losses) >= 3:
            loss_states = [r["market_state"] for r in recent_losses]
            most_common = max(set(loss_states), key=loss_states.count)
            loss_pattern = f"\n⚠️ Recent losses concentrated in {most_common} market"

        return (
            f"Recent {total} trades: win rate {win_rate:.0f}%, "
            f"avg PnL {avg_pnl:+.2f}%\n"
            f"Performance by market state:\n"
            + "\n".join(state_lines)
            + loss_pattern
        )

    async def get_active_rules(self) -> str:
        """获取已验证生效的规则"""
        rows = await self.db.fetch("""
            SELECT condition, recommendation, reasoning, win_rate, sample_size
            FROM distilled_rules
            WHERE status = 'active'
            ORDER BY win_rate DESC LIMIT 5
        """)

        if not rows:
            return "无已验证规则"

        lines = []
        for r in rows:
            condition = json.loads(r["condition"])
            recommendation = json.loads(r["recommendation"])
            lines.append(
                f"- When {condition}: {recommendation} "
                f"(win rate: {r['win_rate']:.0%}, samples: {r['sample_size']})"
            )
        return "\n".join(lines)
```

#### 2.2.2 修改 TRADING_USER 模板

在 `prompts/trading.py` 的 `TRADING_USER` 末尾新增段落：

```python
## Historical Performance (Your Recent Track Record)
{performance_summary}

## Validated Trading Rules (Learned from Past Trades)
{active_rules}
```

#### 2.2.3 在 DecisionEngine 中注入

修改 `decision.py` 的 `_make_decision()` 方法，在构建 `TRADING_USER` 时填充新字段：

```python
if self.prompt_enricher:
    perf_summary = await self.prompt_enricher.get_performance_summary(market_data.symbol)
    active_rules = await self.prompt_enricher.get_active_rules()
else:
    perf_summary = "数据不可用"
    active_rules = "数据不可用"
```

---

### 2.3 配置更新原子性（#8）

**现状**: Advisory 执行器和 Redis 配置监听器直接 `setattr(config, ...)` 无锁保护。

**方案**: 引入配置更新锁。

#### 2.3.1 新增全局配置锁

```python
# scheduler.py
self._config_lock = asyncio.Lock()
```

#### 2.3.2 所有配置更新路径加锁

```python
# _config_listener 中
async with self._config_lock:
    for param in ["stop_loss_percent", "take_profit_percent", ...]:
        setattr(config, param, cfg[param])

# advisory executor 结果处理中
async with self._config_lock:
    result = await executor.execute(action, target, detail)
```

#### 2.3.3 主循环决策前快照配置

```python
# _run_cycle_for_symbol_impl 开头
async with self._config_lock:
    config_snapshot = {
        "stop_loss_percent": config.stop_loss_percent,
        "take_profit_percent": config.take_profit_percent,
        "leverage_max": config.leverage_max,
        "ai_weight": config.ai_weight,
        "quant_weight": config.quant_weight,
    }
# 后续使用 config_snapshot 而非直接读 config
```

---

### 2.4 平仓信号融合修复（#13）

**现状**: 量化的 `CLOSE_LONG`/`CLOSE_SHORT` 被乘 0.6 衰减后当反向分数，无法触发独立平仓。

**方案**: 增加独立的平仓判断路径。

#### 2.4.1 修改 _make_hybrid_decision

在融合逻辑中增加平仓专用判断：

```python
# hybrid_decision.py _make_hybrid_decision 中，在计算 final_score 之后

# ── 独立平仓路径 ──
# 如果持仓中，量化发出明确平仓信号且置信度高，独立处理
if current_position and current_position.size > 0 and quant_signal:
    if (current_position.side == "long"
        and quant_signal.action == SignalAction.CLOSE_LONG
        and quant_signal.confidence >= 0.6):
        # 检查 AI 是否也倾向平仓或不看多
        if ai_score <= 0:  # AI 不看多
            action = "close_long"
            logger.info("独立平仓路径: quant CLOSE_LONG + AI 不看多")

    elif (current_position.side == "short"
          and quant_signal.action == SignalAction.CLOSE_SHORT
          and quant_signal.confidence >= 0.6):
        if ai_score >= 0:  # AI 不看空
            action = "close_short"
            logger.info("独立平仓路径: quant CLOSE_SHORT + AI 不看空")
```

#### 2.4.2 量化平仓信号不再作为反向分数

```python
# 修改 quant_score 计算
if quant_signal:
    if quant_signal.action in (SignalAction.LONG,):
        quant_score = quant_confidence
    elif quant_signal.action in (SignalAction.SHORT,):
        quant_score = -quant_confidence
    elif quant_signal.action in (SignalAction.CLOSE_LONG, SignalAction.CLOSE_SHORT):
        quant_score = 0  # 平仓信号不参与方向分数，走独立路径
```

---

## Phase 3: P2 — 模块协调与自适应（#5, #7, #9, #10, #11, #12）

### 3.1 回测结果驱动策略权重优化（#5, #11）

**现状**: 回测结果存 DB 后孤立，策略权重硬编码。

**方案**: 定期从回测数据中学习最优策略权重。

#### 3.1.1 新增 StrategyWeightOptimizer

创建 `src/ai_trader/optimization/weight_optimizer.py`：

```python
class StrategyWeightOptimizer:
    """基于历史回测和实盘数据优化策略权重"""

    def __init__(self, db: DatabaseManager):
        self.db = db

    async def compute_optimal_weights(self, market_state: str) -> Dict[str, float]:
        """根据特定市场状态下的历史表现计算最优权重

        数据来源:
        1. 回测结果 (backtests 表) — 大量历史数据
        2. 实盘记忆 (trade_memory 表) — 真实表现
        """
        # 从 trade_memory 获取各策略在该市场状态下的表现
        rows = await self.db.fetch("""
            SELECT
                d.strategy_signals,
                tm.pnl_percent,
                tm.is_winner
            FROM trade_memory tm
            JOIN decisions d ON d.symbol = tm.symbol
                AND d.created_at BETWEEN tm.timestamp - INTERVAL '5 minutes'
                AND tm.timestamp + INTERVAL '5 minutes'
            WHERE tm.market_state = $1
            AND tm.pnl_percent IS NOT NULL
            ORDER BY tm.timestamp DESC
            LIMIT 100
        """, market_state)

        if len(rows) < 20:
            return {}  # 样本不足，使用默认权重

        # 分析各策略贡献度
        # ... 基于回归分析或简单统计
        return optimized_weights

    async def update_strategy_selector(self, selector: StrategySelector):
        """更新策略选择器的权重映射"""
        for state in ["STRONG_TREND", "WEAK_TREND", "RANGE_BOUND", "SIDEWAYS", "BREAKOUT"]:
            weights = await self.compute_optimal_weights(state)
            if weights:
                selector.update_weights(state, weights)
```

#### 3.1.2 StrategySelector 支持动态权重

修改 `strategy_selector.py`：

```python
class StrategySelector:
    def __init__(self, enabled_strategies):
        self._weight_overrides: Dict[str, Dict[str, float]] = {}

    def update_weights(self, market_state: str, weights: Dict[str, float]):
        """动态更新特定市场状态的策略权重"""
        self._weight_overrides[market_state] = weights

    def _get_strategy_weights(self, market_state: MarketState) -> Dict[str, float]:
        """获取策略权重，优先使用动态覆盖"""
        state_key = market_state.value
        if state_key in self._weight_overrides:
            return self._weight_overrides[state_key]
        return self.DEFAULT_WEIGHTS[market_state]  # 原有硬编码作为 fallback
```

---

### 3.2 Distilled Rules 消费者（#7）

**方案**: 已在 2.2 中通过 `PromptContextEnricher.get_active_rules()` 注入到 AI prompt。

补充**规则生命周期管理**：

#### 3.2.1 规则状态流转

```
candidate → active → deprecated
   ↑                    |
   └────── 重新验证 ─────┘
```

#### 3.2.2 在复盘中验证规则

修改 `ReflectionEngine`，每次复盘时自动验证现有 candidate 规则：

```python
async def _validate_candidate_rules(self, memories: list[TradeMemoryEntry]):
    """用最新交易数据验证候选规则"""
    candidates = await self.db.fetch(
        "SELECT * FROM distilled_rules WHERE status = 'candidate'"
    )
    for rule in candidates:
        condition = json.loads(rule["condition"])
        # 统计符合条件的交易表现
        matching_trades = [m for m in memories if self._matches_condition(m, condition)]
        if len(matching_trades) >= 5:
            win_rate = sum(1 for m in matching_trades if m.is_winner) / len(matching_trades)
            if win_rate >= 0.6:
                # 升级为 active
                await self.db.execute(
                    "UPDATE distilled_rules SET status='active', validation_count=validation_count+1, win_rate=$1, sample_size=$2, last_validated=NOW() WHERE id=$3",
                    win_rate, len(matching_trades), rule["id"]
                )
            elif rule["validation_count"] >= 3 and win_rate < 0.45:
                # 验证多次不达标，废弃
                await self.db.execute(
                    "UPDATE distilled_rules SET status='deprecated' WHERE id=$1",
                    rule["id"]
                )
```

---

### 3.3 Advisory 与主循环协调（#9）

**现状**: Advisory 和主循环可能对同一 symbol 给出相反建议。

**方案**: 引入"决策协调窗口"。

#### 3.3.1 Advisory 感知主循环最新决策

在 Advisory 上下文中注入主循环最近决策：

```python
# advisory/context.py build() 新增
async def _get_last_decision(self, symbol: str) -> Optional[Dict]:
    """获取主循环最近决策"""
    row = await self.db.pool.fetchrow("""
        SELECT action, confidence, reasoning, created_at
        FROM decisions
        WHERE symbol = $1
        ORDER BY created_at DESC LIMIT 1
    """, symbol)
    return dict(row) if row else None
```

在 `ADVISORY_USER` prompt 中新增段落：

```
## 主循环最近决策
{last_decisions}
注意：你的建议应与主循环决策保持一致性。如果建议与主循环最近决策矛盾，
请在 reasoning 中明确说明为什么需要覆盖主循环的判断。
```

#### 3.3.2 冲突检测与冷却

```python
# advisory/service.py
async def _check_decision_conflict(self, suggestion, symbol):
    """检查 advisory 建议是否与主循环最近决策冲突"""
    last_decision = await self._get_last_decision(symbol)
    if not last_decision:
        return False

    # 如果主循环刚开仓 (< 30分钟)，advisory 不应建议平仓
    time_since = datetime.now() - last_decision["created_at"]
    if time_since.total_seconds() < 1800:  # 30 分钟
        if ("open" in last_decision["action"]
            and "close" in suggestion.get("action", "")):
            logger.warning(f"Advisory 建议与主循环最近决策冲突，跳过: {suggestion}")
            return True
    return False
```

---

### 3.4 多交易对 Testnet 虚拟账户修正（#10）

**现状**: `_build_testnet_account_state` 仅查单 symbol 仓位。

**方案**: 汇总所有 open 仓位计算真实 equity。

```python
async def _build_testnet_account_state(self, symbol: str, current_price: float):
    """Testnet 虚拟账户（汇总所有交易对仓位）"""
    # 获取所有 open 仓位
    all_positions = await self.db_manager.fetch(
        "SELECT symbol, side, entry_price, entry_size, leverage FROM position_history WHERE status='open'"
    )

    base_equity = config.testnet_initial_equity  # 新增配置项，默认 10000
    total_margin = 0.0
    total_unrealized_pnl = 0.0
    current_symbol_position = None

    for row in all_positions:
        pos_symbol = row["symbol"]
        # 获取该 symbol 的当前价格
        if pos_symbol == symbol:
            mark_price = current_price
        else:
            mark_price = await self._get_mark_price(pos_symbol)  # 从缓存或交易所获取

        entry_price = row["entry_price"]
        size = row["entry_size"]
        side = row["side"].lower()
        leverage = row["leverage"] or config.default_leverage

        if side == "long":
            unrealized = (mark_price - entry_price) * size
        else:
            unrealized = (entry_price - mark_price) * size

        margin = (entry_price * size) / leverage
        total_margin += margin
        total_unrealized_pnl += unrealized

        if pos_symbol == symbol:
            current_symbol_position = Position(...)

    # 加上已实现盈亏
    realized_pnl = await self._get_total_realized_pnl()
    total_equity = base_equity + realized_pnl + total_unrealized_pnl
    available_balance = max(total_equity - total_margin, 0.0)

    return AccountInfo(total_equity, available_balance, total_margin, total_unrealized_pnl), current_symbol_position
```

新增配置：

```python
# config.py
testnet_initial_equity: float = Field(default=10000.0, description="Testnet 初始权益")
```

---

### 3.5 决策阈值自适应（#12）

**现状**: `SCORE_THRESHOLD=0.15` 和 `CONFIDENCE_THRESHOLD=0.5` 硬编码。

**方案**: 基于市场波动率动态调整。

```python
# hybrid_decision.py _make_hybrid_decision 中

# 动态阈值（基于 ATR 相对波动率）
atr = market_data.indicators.atr if market_data.indicators and market_data.indicators.atr else 0
atr_pct = (atr / market_data.current_price * 100) if market_data.current_price > 0 else 0

if atr_pct > 3.0:
    # 高波动：提高阈值减少噪音
    score_threshold = 0.25
    confidence_threshold = 0.55
elif atr_pct < 0.5:
    # 低波动：降低阈值捕捉机会
    score_threshold = 0.10
    confidence_threshold = 0.45
else:
    score_threshold = 0.15
    confidence_threshold = 0.50
```

同时将基础阈值加入 `ParameterRegistry`：

```python
"score_threshold": AdjustableParameter(
    name="score_threshold", current_value=0.15,
    min_bound=0.05, max_bound=0.35, step=0.05,
    category="decision", description="融合得分阈值",
),
"confidence_threshold": AdjustableParameter(
    name="confidence_threshold", current_value=0.5,
    min_bound=0.3, max_bound=0.7, step=0.05,
    category="decision", description="最低置信度阈值",
),
```

---

## Phase 4: P3 — 可观测性与工程流程（#14, #15, #16）

### 4.1 回测→实盘闭环验证（#14）

**方案**: 参数变更前自动触发回测验证。

#### 4.1.1 修改 OptimizationOrchestrator

在影子运行验证通过后、应用参数前，自动回测：

```python
async def _backtest_before_apply(self, candidate_params: dict) -> bool:
    """参数应用前自动回测验证"""
    from ..backtest.engine import BacktestEngine

    # 用候选参数运行回测（最近 30 天数据）
    engine = BacktestEngine(
        stop_loss_pct=candidate_params.get("stop_loss_percent", 5.0),
        take_profit_pct=candidate_params.get("take_profit_percent", 10.0),
    )
    result = await engine.run(...)

    # 验证：胜率 > 40%，夏普 > 0.5，最大回撤 < 15%
    if (result.win_rate > 0.4
        and result.sharpe_ratio > 0.5
        and result.max_drawdown < 0.15):
        return True
    else:
        logger.warning(f"回测验证不通过: win_rate={result.win_rate}, sharpe={result.sharpe_ratio}")
        return False
```

---

### 4.2 性能基线追踪（#15）

**方案**: 新增周期性表现评估任务。

#### 4.2.1 新增 PerformanceTracker

创建 `src/ai_trader/monitoring/performance_tracker.py`：

```python
class PerformanceTracker:
    """周期性计算系统表现基线"""

    async def compute_weekly_report(self) -> dict:
        """计算本周表现"""
        rows = await self.db.fetch("""
            SELECT pnl_percent, is_winner, market_state, confidence
            FROM trade_memory
            WHERE timestamp > NOW() - INTERVAL '7 days'
        """)
        return {
            "period": "weekly",
            "total_trades": len(rows),
            "win_rate": ...,
            "avg_pnl": ...,
            "sharpe_ratio": ...,
            "max_drawdown": ...,
            "trend_vs_last_week": ...,  # 与上周对比
        }

    async def detect_degradation(self) -> Optional[str]:
        """检测表现退化"""
        current = await self.compute_weekly_report()
        previous = await self._get_previous_report()

        if previous and current["win_rate"] < previous["win_rate"] - 0.1:
            return f"胜率下降: {previous['win_rate']:.0%} → {current['win_rate']:.0%}"
        if previous and current["avg_pnl"] < previous["avg_pnl"] - 1.0:
            return f"平均盈亏下降: {previous['avg_pnl']:+.2f}% → {current['avg_pnl']:+.2f}%"
        return None
```

#### 4.2.2 集成到 Scheduler

每周日自动生成报告并推送：

```python
# scheduler.py
async def _weekly_performance_check(self):
    """每周日 UTC 0:00 执行"""
    tracker = PerformanceTracker(self.db_manager)
    report = await tracker.compute_weekly_report()

    # 检测退化
    degradation = await tracker.detect_degradation()
    if degradation:
        report["alert"] = degradation
        # 自动触发 Advisory 深度分析
        if self._advisory_service:
            await self._advisory_service.force_check(trigger_reason=f"性能退化: {degradation}")

    # 推送到 Telegram
    if self._notification_manager:
        await self._notification_manager.notify_weekly_report(report)
```

---

### 4.3 LLM 输出质量监控（#16）

**方案**: 在决策持久化时记录输出质量指标。

#### 4.3.1 新增质量评分逻辑

在 `persistence/decision_persistence.py` 中：

```python
def _compute_decision_quality(self, decision: TradingDecision, market_data: MarketData) -> dict:
    """评估 LLM 输出质量"""
    issues = []

    # 检查价格合理性
    if decision.entry_price and decision.entry_price > 0:
        price_deviation = abs(decision.entry_price - market_data.current_price) / market_data.current_price
        if price_deviation > 0.05:
            issues.append(f"entry_price偏差过大: {price_deviation:.1%}")

    # 检查止损合理性
    if decision.stop_loss_price and decision.entry_price:
        sl_distance = abs(decision.stop_loss_price - decision.entry_price) / decision.entry_price
        if sl_distance > 0.15 or sl_distance < 0.005:
            issues.append(f"止损距离异常: {sl_distance:.1%}")

    # 检查风险回报比
    if decision.stop_loss_price and decision.take_profit_price and decision.entry_price:
        risk = abs(decision.entry_price - decision.stop_loss_price)
        reward = abs(decision.take_profit_price - decision.entry_price)
        if risk > 0:
            rr_ratio = reward / risk
            if rr_ratio < 1.0:
                issues.append(f"风险回报比不足: {rr_ratio:.1f}")

    return {
        "quality_score": max(0, 100 - len(issues) * 20),
        "issues": issues,
    }
```

#### 4.3.2 按 Provider 统计质量

在 `llm_usage` 表中新增 `quality_score` 列，按 provider 聚合分析：

```sql
-- 查看各 provider 的决策质量
SELECT provider, model,
       AVG(quality_score) as avg_quality,
       COUNT(*) as total_decisions,
       SUM(CASE WHEN quality_score >= 80 THEN 1 ELSE 0 END) as high_quality_count
FROM llm_usage
WHERE quality_score IS NOT NULL
GROUP BY provider, model
ORDER BY avg_quality DESC;
```

---

## 整体架构改进后的数据流

```
┌───────────────────────────────────────────────────────────┐
│                    Main Trading Loop                       │
│                                                           │
│  Market Data → [Daily Loss Check] → [SL/TP Check]        │
│       ↓              ↓(halt)            ↓(trigger)       │
│  Technical    Stop trading         Auto close             │
│  Analysis                                                 │
│       ↓                                                   │
│  AI Decision ← [Prompt Enricher: 历史表现 + 已验证规则]    │
│       ↓                                                   │
│  Quant Signal ← [Dynamic Weights from optimizer]          │
│       ↓                                                   │
│  Hybrid Fusion (含独立平仓路径)                            │
│       ↓                                                   │
│  [Signal Filter: 时间间隔 + 反向冷却]                     │
│       ↓                                                   │
│  Order Execution                                          │
│       ↓                                                   │
│  ┌─ Trade Memory ─┐                                      │
│  │                 ↓                                      │
│  │  Reflection Engine (每 N 笔)                           │
│  │       ↓                                                │
│  │  parameter_suggestions + candidate_rules               │
│  │       ↓                                                │
│  │  OptimizationOrchestrator                              │
│  │       ↓                                                │
│  │  Shadow Runner (验证)                                   │
│  │       ↓                                                │
│  │  [Backtest 验证] → 通过 → 自动应用参数                  │
│  │       ↓                                                │
│  │  distilled_rules (active → 注入 Prompt)                 │
│  └─────────────────┘                                      │
│                                                           │
│  ┌─ Advisory (异步) ─┐                                    │
│  │  感知主循环决策    │                                    │
│  │  冲突检测 + 冷却   │                                    │
│  │  → TG → 用户确认   │                                    │
│  │  → [Config Lock]  │                                    │
│  │  → 执行            │                                    │
│  └───────────────────┘                                    │
│                                                           │
│  ┌─ Monitoring ──────┐                                    │
│  │  Weekly Report     │                                    │
│  │  退化检测 → Alert  │                                    │
│  │  LLM 质量追踪     │                                    │
│  └───────────────────┘                                    │
└───────────────────────────────────────────────────────────┘
```

---

## 实施顺序

| Phase | 内容 | 涉及文件 | 预估改动量 |
|-------|------|----------|-----------|
| Phase 1 | 每日亏损限制 + 信号过滤器 | scheduler.py, config.py, position_manager.py | 中 |
| Phase 2.1 | 复盘→影子验证闭环 | 新建 orchestrator.py, 修改 scheduler.py, reflection/engine.py | 大 |
| Phase 2.2 | Prompt 动态注入 | 新建 prompts/enricher.py, 修改 prompts/trading.py, decision.py | 中 |
| Phase 2.3 | 配置原子性 | scheduler.py | 小 |
| Phase 2.4 | 平仓信号修复 | hybrid_decision.py | 小 |
| Phase 3.1 | 策略权重优化 | 新建 weight_optimizer.py, 修改 strategy_selector.py | 中 |
| Phase 3.2 | 规则生命周期 | reflection/engine.py | 小 |
| Phase 3.3 | Advisory 协调 | advisory/context.py, advisory/service.py | 中 |
| Phase 3.4 | Testnet 多交易对 | scheduler.py | 中 |
| Phase 3.5 | 决策阈值自适应 | hybrid_decision.py, parameter_registry.py | 小 |
| Phase 4.1 | 回测→实盘闭环 | orchestrator.py | 中 |
| Phase 4.2 | 性能基线追踪 | 新建 performance_tracker.py | 中 |
| Phase 4.3 | LLM 质量监控 | persistence/decision_persistence.py | 小 |

---

## 新增/修改文件清单

### 新增文件
- `src/ai_trader/optimization/orchestrator.py` — 优化编排器
- `src/ai_trader/optimization/weight_optimizer.py` — 策略权重优化器
- `src/ai_trader/prompts/enricher.py` — Prompt 上下文增强器
- `src/ai_trader/monitoring/performance_tracker.py` — 性能追踪器

### 主要修改文件
- `src/ai_trader/scheduler.py` — 每日亏损、信号过滤、配置锁、闭环集成
- `src/ai_trader/config.py` — 新增配置项
- `src/ai_trader/ai/hybrid_decision.py` — 平仓路径修复、阈值自适应
- `src/ai_trader/ai/decision.py` — Prompt enricher 集成
- `src/ai_trader/prompts/trading.py` — 新增历史表现段落
- `src/ai_trader/strategies/strategy_selector.py` — 动态权重支持
- `src/ai_trader/reflection/engine.py` — 规则验证、结果推送
- `src/ai_trader/advisory/context.py` — 主循环决策感知
- `src/ai_trader/advisory/service.py` — 冲突检测
- `src/ai_trader/optimization/parameter_registry.py` — 新增阈值参数
- `src/ai_trader/persistence/decision_persistence.py` — 质量评分

### 数据库迁移
- 新增 `llm_usage.quality_score` 列
- 新增 `performance_reports` 表
- 新增 `config.testnet_initial_equity` 配置项
