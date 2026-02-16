# 交易系统架构改进 开发任务清单

> 根据 `2026-02-15-architecture-review-improvements-design.md` 自动生成
> 生成时间：2026-02-15

## 总览

- 总 Phase 数：4（含子阶段共 13 个模块）
- 预估任务数：52
- 涉及新建文件：4 个
- 涉及修改文件：11 个
- 数据库迁移：3 项

---

## Phase 1: P0 — 资金安全（#1 每日亏损限制, #2 信号过滤器）

### 目标
修复两个 🔴 严重级别问题：每日亏损限制未启用、信号过滤器未集成主循环

### 任务清单

#### 1.1 每日亏损限制集成
- [x] config.py 新增配置项：`daily_loss_limit_percent`、`consecutive_halt_days_for_break`、`forced_break_days`
- [x] scheduler.py 新增每日盈亏追踪属性：`_daily_pnl`、`_daily_pnl_date`、`_trading_halted`、`_halt_until`、`_halt_consecutive_days`
- [x] scheduler.py `start()` 主循环中实现每日重置逻辑（UTC 00:00）
- [x] scheduler.py `_run_cycle_for_symbol_impl` 中在 SL/TP 检查后、LLM 决策前插入每日亏损限制检查
- [x] scheduler.py `_persist_position_change` 平仓/减仓逻辑中累加 `_daily_pnl`
- [x] 触发时发送 Telegram 告警通知
- [x] 实现连续触发 N 天 → 强制休息逻辑
- [x] 强制休息结束后重置 `_halt_consecutive_days`（Code Review 修复）
- [x] halt 状态下有持仓时允许 LLM 平仓操作（Code Review 修复）

#### 1.2 SignalFilter 集成主循环
- [x] scheduler.py `__init__` 初始化 `_signal_filters: Dict[str, SignalFilter]`
- [x] config.py 新增 `signal_min_interval_hours`、`signal_reverse_cooldown_hours` 配置项
- [x] scheduler.py `_run_cycle_for_symbol_impl` 中 LLM 决策后、订单执行前插入信号过滤
- [x] 订单执行成功后调用 `signal_filter.record_trade()` 更新状态（仅 order_id 有效时）
- [x] SignalFilter 增强：`min_interval_hours` 改为 float，新增 `reverse_cooldown_hours` 参数

### 测试任务
- [x] 单元测试：每日亏损限制检查逻辑（正常/触发/连续触发/日期重置/强制休息）— 9 tests
- [x] 单元测试：信号过滤器基础功能 + 反向冷却 + float interval + reset — 10 tests
- [x] 单元测试：信号过滤器集成（快速开仓拦截/平仓不过滤/失败不记录/symbol 隔离）— 4 tests
- [x] 单元测试：Phase 1 新增配置项默认值及环境变量覆盖 — 6 tests
- [x] **总计 29 tests 全部通过** ✅

---

## Phase 2.1: P1 — 复盘→影子验证→参数应用闭环（#3, #4）

### 目标
打通 复盘结果 → ShadowRunner 验证 → 参数自动应用 的完整管线

### 任务清单
- [ ] 新建 `src/ai_trader/optimization/orchestrator.py`：`OptimizationOrchestrator` 类
- [ ] 实现 `handle_reflection_result()`：过滤合法参数建议、启动影子运行
- [ ] 实现 `evaluate_and_apply()`：评估影子运行结果、自动应用参数、记录变更到 DB、发布配置更新
- [ ] 实现 `_save_parameter_changes()` 和 `_publish_config_update()` 辅助方法
- [ ] 修改 `reflection/engine.py`：复盘完成后将结果推入 Redis 队列 `reflection:results`
- [ ] ReflectionEngine 构造函数新增 `redis` 参数
- [ ] scheduler.py 初始化 `OptimizationOrchestrator`（在 `enable_auto_optimization` 时）
- [ ] scheduler.py 新增 `_reflection_results_listener()` 异步任务监听 Redis 队列
- [ ] scheduler.py 平仓时记录影子运行数据 `shadow_runner.record_current_result()`
- [ ] scheduler.py 平仓后调用 `optimization_orchestrator.evaluate_and_apply()`

### 测试任务
- [ ] 单元测试：OptimizationOrchestrator 处理合法/非法参数建议
- [ ] 单元测试：影子运行评估通过/不通过/样本不足三种场景
- [ ] 集成测试：复盘→Redis 队列→Orchestrator→ShadowRunner→参数应用完整链路

---

## Phase 2.2: P1 — Prompt 动态注入历史表现（#6）

### 目标
让 AI 决策 prompt 动态包含历史交易表现和已验证规则

### 任务清单
- [ ] 新建 `src/ai_trader/prompts/enricher.py`：`PromptContextEnricher` 类
- [ ] 实现 `get_performance_summary(symbol)`：从 trade_memory 查询近期表现、按市场状态分析、识别失败模式
- [ ] 实现 `get_active_rules()`：从 distilled_rules 查询 status='active' 的规则
- [ ] 修改 `prompts/trading.py` `TRADING_USER` 模板：末尾新增 `{performance_summary}` 和 `{active_rules}` 段落
- [ ] 修改 `ai/decision.py` `_make_decision()`：集成 PromptContextEnricher，填充新 prompt 字段
- [ ] DecisionEngine 构造函数新增 `prompt_enricher` 可选参数
- [ ] scheduler.py 创建 DecisionEngine 时传入 PromptContextEnricher 实例

### 测试任务
- [ ] 单元测试：PromptContextEnricher 无数据/有数据/失败模式检测
- [ ] 单元测试：TRADING_USER 模板渲染包含新字段
- [ ] 集成测试：完整决策流程中 prompt 包含历史数据

---

## Phase 2.3: P1 — 配置更新原子性（#8）

### 目标
通过配置锁防止并发配置读写冲突

### 任务清单
- [ ] scheduler.py `__init__` 新增 `_config_lock = asyncio.Lock()`
- [ ] `_config_listener` 中所有 `setattr(config, ...)` 路径加 `async with self._config_lock`
- [ ] Advisory executor 结果处理路径加 `async with self._config_lock`
- [ ] `_run_cycle_for_symbol_impl` 开头加配置快照逻辑，后续使用 snapshot 而非直接读 config

### 测试任务
- [ ] 单元测试：配置锁在并发更新时的互斥性
- [ ] 集成测试：主循环决策使用配置快照而非实时 config

---

## Phase 2.4: P1 — 平仓信号融合修复（#13）

### 目标
修复量化平仓信号被错误地当作反向分数的问题

### 任务清单
- [ ] hybrid_decision.py 修改 quant_score 计算：`CLOSE_LONG`/`CLOSE_SHORT` 的 quant_score 设为 0
- [ ] hybrid_decision.py 在 final_score 计算后新增独立平仓判断路径
- [ ] 独立平仓条件：持仓中 + 量化平仓信号置信度 ≥ 0.6 + AI 不持反向观点

### 测试任务
- [ ] 单元测试：量化 CLOSE_LONG + AI hold → 触发平仓
- [ ] 单元测试：量化 CLOSE_LONG + AI 强看多 → 不平仓
- [ ] 单元测试：量化平仓信号不再影响方向分数

---

## Phase 3.1: P2 — 策略权重数据驱动优化（#5, #11）

### 目标
让策略权重基于回测和实盘数据动态调整，替代硬编码

### 任务清单
- [ ] 新建 `src/ai_trader/optimization/weight_optimizer.py`：`StrategyWeightOptimizer` 类
- [ ] 实现 `compute_optimal_weights(market_state)`：从 trade_memory + decisions 联合查询分析
- [ ] 实现 `update_strategy_selector(selector)`：批量更新各市场状态的权重
- [ ] strategy_selector.py 新增 `_weight_overrides` 字典和 `update_weights()` 方法
- [ ] strategy_selector.py `_get_strategy_weights()` 优先使用动态覆盖，fallback 到默认值
- [ ] scheduler.py 定期调用 `StrategyWeightOptimizer.update_strategy_selector()`（如每天一次）

### 测试任务
- [ ] 单元测试：权重优化器样本不足时返回空（使用默认）
- [ ] 单元测试：StrategySelector 动态权重覆盖 + fallback
- [ ] 集成测试：权重更新后决策引擎使用新权重

---

## Phase 3.2: P2 — Distilled Rules 生命周期管理（#7）

### 目标
实现规则 candidate→active→deprecated 状态流转

### 任务清单
- [ ] reflection/engine.py 新增 `_validate_candidate_rules(memories)` 方法
- [ ] 实现 `_matches_condition(memory, condition)` 规则匹配逻辑
- [ ] 在 `run_reflection()` 中调用 `_validate_candidate_rules()`
- [ ] 规则升级逻辑：匹配交易 ≥ 5 笔 + 胜率 ≥ 60% → active
- [ ] 规则废弃逻辑：验证 ≥ 3 次 + 胜率 < 45% → deprecated

### 测试任务
- [ ] 单元测试：规则匹配逻辑
- [ ] 单元测试：规则升级/废弃/样本不足三种场景

---

## Phase 3.3: P2 — Advisory 与主循环协调（#9）

### 目标
防止 Advisory 建议与主循环最近决策产生矛盾

### 任务清单
- [ ] advisory/context.py 新增 `_get_last_decision(symbol)` 方法
- [ ] advisory/context.py `build()` 中注入主循环最近决策信息
- [ ] advisory/prompts.py `ADVISORY_USER` 模板新增"主循环最近决策"段落
- [ ] advisory/service.py 新增 `_check_decision_conflict()` 冲突检测方法
- [ ] advisory/service.py 在生成建议后、推送前调用冲突检测

### 测试任务
- [ ] 单元测试：冲突检测（30 分钟内开仓 + advisory 建议平仓 → 跳过）
- [ ] 单元测试：无冲突场景正常通过

---

## Phase 3.4: P2 — Testnet 多交易对虚拟账户修正（#10）

### 目标
修正多交易对场景下 Testnet 虚拟账户 equity 计算不准的问题

### 任务清单
- [ ] config.py 新增 `testnet_initial_equity` 配置项
- [ ] scheduler.py `_build_testnet_account_state` 改为查询所有 status='open' 仓位
- [ ] 实现跨交易对 mark_price 获取（缓存 + 交易所 fallback）
- [ ] 累加已实现盈亏到 total_equity
- [ ] 汇总所有仓位 margin 和 unrealized_pnl

### 测试任务
- [ ] 单元测试：单交易对/多交易对虚拟账户计算
- [ ] 单元测试：已实现盈亏正确累加

---

## Phase 3.5: P2 — 决策阈值自适应（#12）

### 目标
让决策阈值基于市场波动率动态调整

### 任务清单
- [ ] hybrid_decision.py `_make_hybrid_decision` 中基于 ATR% 动态计算 score_threshold 和 confidence_threshold
- [ ] parameter_registry.py 新增 `score_threshold` 和 `confidence_threshold` 参数定义
- [ ] 动态阈值作为基线，ParameterRegistry 值用于覆盖默认基线

### 测试任务
- [ ] 单元测试：高波动/低波动/正常波动三档阈值
- [ ] 单元测试：ParameterRegistry 覆盖阈值

---

## Phase 4.1: P3 — 回测→实盘闭环验证（#14）

### 目标
参数变更前自动回测验证，防止劣质参数上线

### 任务清单
- [ ] orchestrator.py 新增 `_backtest_before_apply(candidate_params)` 方法
- [ ] 在 `evaluate_and_apply()` 中影子运行通过后调用回测验证
- [ ] 回测验证标准：胜率 > 40%、夏普 > 0.5、最大回撤 < 15%
- [ ] 验证不通过时拒绝参数切换并记录日志

### 测试任务
- [ ] 单元测试：回测通过/不通过时的行为
- [ ] 集成测试：影子运行→回测→应用完整链路

---

## Phase 4.2: P3 — 性能基线追踪（#15）

### 目标
建立周期性表现评估和退化检测机制

### 任务清单
- [ ] 新建 `src/ai_trader/monitoring/__init__.py`
- [ ] 新建 `src/ai_trader/monitoring/performance_tracker.py`：`PerformanceTracker` 类
- [ ] 实现 `compute_weekly_report()`：从 trade_memory 计算周报指标
- [ ] 实现 `detect_degradation()`：与上周对比检测退化
- [ ] 实现 `_get_previous_report()` 和 `_save_report()` 持久化方法
- [ ] 数据库迁移：新增 `performance_reports` 表
- [ ] scheduler.py 新增 `_weekly_performance_check()` 每周日执行
- [ ] 退化检测触发 Advisory 深度分析 + Telegram 推送

### 测试任务
- [ ] 单元测试：周报计算（有数据/无数据）
- [ ] 单元测试：退化检测（胜率下降/盈亏下降/无变化）

---

## Phase 4.3: P3 — LLM 输出质量监控（#16）

### 目标
追踪各 LLM Provider 的决策输出质量

### 任务清单
- [ ] persistence/decision_persistence.py 新增 `_compute_decision_quality()` 方法
- [ ] 在 `save_decision()` 中调用质量评分并记录
- [ ] 数据库迁移：`llm_usage` 表新增 `quality_score` 列
- [ ] 按 provider 聚合质量统计 SQL 查询

### 测试任务
- [ ] 单元测试：质量评分（正常/价格偏差/止损异常/风险回报比不足）

---

## 完成标准

每个 phase 完成标准：
- ✅ 所有任务项标记为完成 `[x]`
- ✅ 所有测试通过
- ✅ Code review 无阻塞性问题
- ✅ 相关配置项有默认值且向后兼容

## 注意事项

1. **顺序执行**：严格按 Phase 顺序开发，Phase 1 完成后才能开始 Phase 2
2. **Phase 2 内部**：2.3（配置锁）应最先做，其他子阶段可并行
3. **Phase 3 内部**：各子阶段相互独立，可并行开发
4. **增量提交**：每个 Phase 完成后进行代码提交
5. **向后兼容**：所有新功能默认关闭或有安全默认值，不影响现有功能
6. **数据库迁移**：Phase 4.2 和 4.3 涉及数据库变更，需先运行迁移
