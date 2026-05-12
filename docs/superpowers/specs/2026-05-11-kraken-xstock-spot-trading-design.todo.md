# Kraken XStock 美股现货交易接入开发任务清单

> 根据 plan 文档自动生成
> 生成时间：2026-05-11 14:00:00

## 总览

- 总 Phase 数：5
- 预估任务数：18
- 测试策略：单元测试 + API Mock 测试

---

## Phase 1: 配置与基础设施

### 目标
增加 Kraken XStock 相关的配置项和环境变量，注册交易所客户端工厂。

### 任务清单
- [ ] 修改 `src/ai_trader/config.py`，在 `exchange_type` 增加 `kraken`，并添加 API 凭证及 `stock_trading_symbols` 配置 [§2.1]
- [ ] 修改 `src/ai_trader/exchange/__init__.py`，在 `credentials_map` 中增加 Kraken 凭证映射 [§2.2]
- [ ] 修改 `src/ai_trader/exchange/__init__.py`，在 `create_exchange_client` 工厂函数中添加 Kraken 实例化分支 [§3.5]
- [ ] 更新 `.env.example`，加入 Kraken 相关环境变量 [§2.3]
- [ ] 修改 `src/ai_trader/exchange/base.py`，在 `Position` 模型中增加 `margin_mode` 可选字段 [§9]

### 测试任务
- [ ] 单元测试：验证配置类能正确解析和加载新的环境变量。

---

## Phase 2: Kraken XStock 交易所适配器

### 目标
实现基于 ccxt 的 Kraken 现货（XStock）交易适配器。

### 任务清单
- [ ] 创建 `src/ai_trader/exchange/kraken_xstock_adapter.py` 文件并定义 `KrakenXStockAdapter`（继承 `BaseExchange`） [§3.1, §3.2]
- [ ] 实现 `get_account()` 方法（计算可用余额和持仓 PnL） [§3.3]
- [ ] 实现行情和持仓读取方法：`get_klines()`, `get_ticker()`, `get_positions()`（统一转换为做多格式） [§3.3, §3.4]
- [ ] 实现 `set_leverage()` 方法（现货直接返回 True，no-op） [§3.3]
- [ ] 实现订单相关方法：`create_order()`（注入 `asset_class=tokenized_asset` 参数）和 `cancel_order()` [§3.3]
- [ ] 实现 `get_available_symbols()` 方法过滤可交易现货对 [§3.3]

### 测试任务
- [ ] 单元测试：Mock CCXT 返回，验证各个方法的 API 调用参数（特别是 `asset_class` 参数） [§8.2]
- [ ] 单元测试：验证现货 `Position` 对象的数据映射逻辑（`leverage=1`, `side="long"` 等） [§8.2]

---

## Phase 3: 美股 AI 决策引擎

### 目标
针对美股现货交易定制 LLM prompt 和决策过滤逻辑。

### 任务清单
- [ ] 创建 `src/ai_trader/prompts/stock_trading.py`，编写美股量化交易员专属 Prompt 模板 [§4.1]
- [ ] 修改 `src/ai_trader/ai/hybrid_decision.py`，在执行 LLM 决策前根据 symbol 切换使用对应的 prompt [§4.2]
- [ ] 修改 `src/ai_trader/ai/hybrid_decision.py`，对美股决策结果进行动作白名单过滤（仅允许 buy/sell/hold/add/reduce），并将杠杆强制置为 1 [§4.2]

### 测试任务
- [ ] 单元测试：验证 `hybrid_decision.py` 能正确切换 prompt 并截断/过滤无效动作（如 short） [§8.2]

---

## Phase 4: 美股量化策略

### 目标
实现专属于美股的量化交易策略。

### 任务清单
- [ ] 创建 `src/ai_trader/strategies/stock/__init__.py` [§5.1]
- [ ] 创建 `src/ai_trader/strategies/stock/stock_strategy_base.py`，定义 `StockSignal` 和 `StockSignalAction` [§5.2]
- [ ] 创建 `src/ai_trader/strategies/stock/stock_trend_following.py`，实现 MA + MACD 趋势跟随策略 [§5.3]
- [ ] 创建 `src/ai_trader/strategies/stock/stock_mean_reversion.py`，实现 RSI + Bollinger 均值回归策略 [§5.3]

### 测试任务
- [ ] 单元测试：验证美股量化策略逻辑不会生成 `short` 相关信号，只返回多头买卖及持有信号。

---

## Phase 5: 调度器与数据持久化适配

### 目标
修改核心调度器，以支持合约和现货混合的符号循环和现货特有的交易逻辑。

### 任务清单
- [ ] 修改 `src/ai_trader/scheduler.py` 中的 `is_stock_symbol()` 函数判断逻辑 [§6.3]
- [ ] 修改 `src/ai_trader/scheduler.py` 中的初始化逻辑，合并合约与美股现货的 trading symbols [§6.1]
- [ ] 修改 `run_cycle_for_symbol()`，针对美股执行差异化的 quantity 计算（无杠杆）、跳过 `set_leverage` 调用，且不应用 `reverse_cooldown` [§6.2]
- [ ] 修改 `run_cycle_for_symbol()` 中的止盈止损逻辑，现货只支持多头方向检查 [§6.2]
- [ ] 确认写入 `position_history` 和 `decision` 数据库表的字段兼容性（leverage=1, action等对应） [§7.1, §7.2]

### 测试任务
- [ ] 单元测试：验证 `scheduler.py` 对于美股 symbol 的 quantity 计算和动作过滤是否正确 [§8.2]
- [ ] 单元测试：验证现货止盈止损仅应用单向检测逻辑 [§8.2]

---

## 完成标准

每个 phase 完成标准：
- ✅ 所有任务项标记为完成 `[x]`
- ✅ 所有测试通过（本地及 CI）
- ✅ Code review 无阻塞性问题
- ✅ 静态检查 / 类型检查（Mypy/Ruff）通过

## 注意事项

1. **顺序执行**：严格按 phase 顺序开发，不跨阶段
2. **测试先行**：Kraken 无沙盒环境，必须通过 `validate=true` 或 mock 测试覆盖所有新逻辑
3. **资金安全**：涉及订单生成的部分需要特别留意资金和 quantity 的计算
