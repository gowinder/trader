# 混合 TDD + BDD 测试补齐计划

## 目标

在不大改核心逻辑的前提下，先把测试缺口梳理清楚，按业务风险分批补齐。策略采用混合 TDD + BDD：

- 纯计算、纯转换、规则边界清晰的模块优先补 `unit test`，按 red -> green -> refactor 执行。
- 交易风控、调度、鉴权、配置切换、策略变更、路由行为这类跨模块流程优先补 `behavior-style test`，用 Given / When / Then 描述业务结果。
- 每个 BDD 场景下面再补最小必要的 unit test，避免只测 happy path。

## 扫描结论

- Python 主体代码位于 `src/ai_trader`，共 106 个模块文件。
- 现有 Python 自动化测试位于 `tests/`，共 49 个测试文件。
- 现有 BDD 特性文件位于 `tests/bdd/features`，共 4 个，当前集中在仓位 sizing / 日亏损限制 / 移动止损 / 金字塔加仓。
- `dashboard/` 前端存在 55 个 route 文件、13 个组件文件、1 个鉴权服务文件，但 `dashboard/package.json` 没有测试脚本，当前基本没有成体系前端自动化测试。
- `pytest tests --cov=src/ai_trader -q` 当前无法完成收集，直接暴露出测试基座问题：缺少 `pydantic`、`pydantic_settings`、`httpx`、`ccxt`、`asyncpg`、`redis`、`loguru`、`pytest_bdd` 等依赖，同时存在导入期副作用。
- 裸跑 `pytest --cov=src/ai_trader -q` 还会误收集 `scripts/test_api_simple.py`，该脚本在导入期直接 `exit(1)`，说明脚本目录与正式测试目录边界不清。

## 现有覆盖概况

- 已有相对明确的 Python 测试域：`advisory` 核心、`exchange` 核心、`events` 聚合层、`memory`、`optimization`、`risk`、`sentiment`、`reflection`、`config`、`reporter`、若干 phase 集成测试。
- 已有 behavior-style 测试仅覆盖风控规则的一部分，尚未扩展到交易调度、鉴权、策略切换、Dashboard API、持久化链路。
- 多个模块虽然“有测试文件”，但只在 phase 测试或单点测试中被间接触达，仍然属于薄弱覆盖，不足以支撑安全回归。

## 未覆盖模块

### Python 完全未直接覆盖

- `src/ai_trader/advisory/prompts.py`
- `src/ai_trader/advisory/telegram/auth.py`
- `src/ai_trader/advisory/telegram/bot.py`
- `src/ai_trader/advisory/telegram/commands.py`
- `src/ai_trader/advisory/telegram/formatters.py`
- `src/ai_trader/advisory/telegram/handlers/advisory.py`
- `src/ai_trader/advisory/telegram/handlers/decisions.py`
- `src/ai_trader/advisory/telegram/handlers/llm_usage.py`
- `src/ai_trader/advisory/telegram/handlers/menu.py`
- `src/ai_trader/advisory/telegram/handlers/overview.py`
- `src/ai_trader/advisory/telegram/handlers/positions.py`
- `src/ai_trader/advisory/telegram/handlers/strategy.py`
- `src/ai_trader/advisory/telegram/handlers/trading.py`
- `src/ai_trader/advisory/telegram/keyboards.py`
- `src/ai_trader/advisory/telegram/notifier.py`
- `src/ai_trader/ai/analyzer.py`
- `src/ai_trader/ai/client.py`
- `src/ai_trader/ai/hybrid_decision.py`
- `src/ai_trader/ai/llm_client.py`
- `src/ai_trader/ai/llm_manager.py`
- `src/ai_trader/ai/providers/base.py`
- `src/ai_trader/ai/providers/cli_provider.py`
- `src/ai_trader/ai/providers/codex_oauth.py`
- `src/ai_trader/ai/providers/gemini_oauth.py`
- `src/ai_trader/ai/providers/qwen_oauth.py`
- `src/ai_trader/ai/token_manager.py`
- `src/ai_trader/ai/usage_tracker.py`
- `src/ai_trader/analytics/trade_journal.py`
- `src/ai_trader/backtest/engine.py`
- `src/ai_trader/backtest/runner.py`
- `src/ai_trader/events/detectors/base.py`
- `src/ai_trader/events/detectors/bollinger_break.py`
- `src/ai_trader/events/detectors/macd_cross.py`
- `src/ai_trader/events/detectors/market_state_change.py`
- `src/ai_trader/events/detectors/position_pnl.py`
- `src/ai_trader/events/detectors/price_surge.py`
- `src/ai_trader/events/detectors/rsi_extreme.py`
- `src/ai_trader/events/detectors/volume_spike.py`
- `src/ai_trader/exchange/position.py`
- `src/ai_trader/main.py`
- `src/ai_trader/models/strategy_preset.py`
- `src/ai_trader/notification/formatter.py`
- `src/ai_trader/notification/manager.py`
- `src/ai_trader/persistence/database.py`
- `src/ai_trader/persistence/strategy_service.py`
- `src/ai_trader/prompts/risk.py`
- `src/ai_trader/prompts/technical.py`
- `src/ai_trader/prompts/trading.py`
- `src/ai_trader/reflection/prompts.py`
- `src/ai_trader/reflection/service.py`
- `src/ai_trader/scheduler.py`
- `src/ai_trader/sentiment/data_sources.py`
- `src/ai_trader/strategies/pattern_recognition.py`
- `src/ai_trader/strategies/presets.py`
- `src/ai_trader/utils/logger.py`
- `src/ai_trader/utils/translator.py`

### Python 薄弱覆盖

- `src/ai_trader/ai/decision.py`
- `src/ai_trader/advisory/llm_client.py`
- `src/ai_trader/advisory/persistence.py`
- `src/ai_trader/advisory/triggers.py`
- `src/ai_trader/data/fetcher.py`
- `src/ai_trader/data/indicators.py`
- `src/ai_trader/data/market_data.py`
- `src/ai_trader/data/multi_timeframe.py`
- `src/ai_trader/events/cooldown.py`
- `src/ai_trader/exchange/order.py`
- `src/ai_trader/memory/collector.py`
- `src/ai_trader/monitoring/performance_tracker.py`
- `src/ai_trader/optimization/rule_validator.py`
- `src/ai_trader/persistence/service.py`
- `src/ai_trader/reflection/trigger.py`
- `src/ai_trader/reporter.py`
- `src/ai_trader/sentiment/analyzer.py`
- `src/ai_trader/sentiment/cache.py`
- `src/ai_trader/strategies/market_classifier.py`

### Dashboard 当前无自动化测试覆盖

- `dashboard/app/routes/*.tsx`
- `dashboard/app/routes/api.*.ts`
- `dashboard/app/services/auth.server.ts`
- `dashboard/app/components/**/*`
- `dashboard/db/index.ts`
- `dashboard/db/schema.ts`

注：`dashboard/app/routes/api.llm-config.test.ts` 是业务路由文件，不是测试文件。

## P0 / P1 / P2 优先级

| 优先级 | 模块范围 | 原因 | 建议测试类型 |
| --- | --- | --- | --- |
| P0 | `src/ai_trader/scheduler.py`、`src/ai_trader/risk/position_manager.py`、`src/ai_trader/exchange/order.py`、`src/ai_trader/exchange/position.py`、`src/ai_trader/exchange/__init__.py`、`src/ai_trader/ai/decision.py`、`src/ai_trader/ai/hybrid_decision.py`、`src/ai_trader/config.py`、`src/ai_trader/main.py`、`src/ai_trader/persistence/database.py`、`src/ai_trader/persistence/service.py`、`src/ai_trader/persistence/strategy_service.py`、`dashboard/app/services/auth.server.ts`、所有会修改交易/策略/配置状态的 `dashboard/app/routes/api.*.ts` | 直接影响下单、风控、停机保护、鉴权、参数写入、配置切换 | 规则计算用 `unit test`；交易暂停、调度、登录、改密、策略激活/锁定/重置、触发器配置等用 `behavior-style test` |
| P1 | `src/ai_trader/backtest/*`、`src/ai_trader/optimization/*`、`src/ai_trader/strategies/*`、`src/ai_trader/events/*`、`src/ai_trader/reflection/*`、`src/ai_trader/analytics/trade_journal.py`、`src/ai_trader/notification/*`、`src/ai_trader/sentiment/*`、`src/ai_trader/advisory/service.py`、`src/ai_trader/advisory/triggers.py`、`src/ai_trader/advisory/telegram/*`、Dashboard 只读 API 与关键 dashboard 页面 | 影响策略质量、告警质量、运营可用性和回归稳定性，但不直接改变底层下单安全边界 | 算法/解析/格式化优先 `unit test`；“策略推荐 -> 审核 -> 生效”、“事件触发 -> 通知”、“页面 loader/action 行为”用 `behavior-style test` |
| P2 | `src/ai_trader/prompts/*`、`src/ai_trader/advisory/prompts.py`、`src/ai_trader/reflection/prompts.py`、`src/ai_trader/ai/providers/*`、`src/ai_trader/ai/token_manager.py`、`src/ai_trader/ai/usage_tracker.py`、`src/ai_trader/utils/*`、Dashboard UI 组件与纯展示页面、`scripts/test_*.py` | 风险较低，更多是包装层、文本层、外部平台兼容层和展示层 | 大多使用 `unit test`；少量高价值 UI / OAuth 流程保留 `behavior-style test` 即可 |

## 分批补齐策略

### 第一阶段：先修测试基座，再进入 P0

- 把 pytest 收集范围固定到 `tests/`，避免 `scripts/test_*.py` 被当成正式测试。
- 补齐 Python 测试依赖安装入口，保证 `pytest tests` 能稳定收集。
- 先补 P0 的 unit test 骨架，再补最关键的 BDD 场景。

### 第二阶段：P0 重点场景

- `scheduler`：行为测试覆盖“达到日亏损阈值后停止交易”“强制休息期内禁止开新仓”“冷却窗口内忽略重复信号”“恢复条件满足后重新允许执行”。
- `risk + exchange`：单元测试覆盖仓位计算、止盈止损边界、订单参数规范化、异常映射；行为测试覆盖“下单失败回滚”“仓位关闭后状态一致”“testnet/live 切换”。
- `decision + hybrid_decision`：单元测试覆盖置信度融合、权重边界、空数据处理；行为测试覆盖“低置信度不下单”“风险阈值触发后只允许 hold/close”。
- `persistence`：单元测试覆盖 SQL 输入/输出映射与序列化；行为测试覆盖“决策写入 -> 查询 -> 策略状态更新”的完整链路。
- `dashboard auth + mutating APIs`：行为测试覆盖登录、登出、改密、策略 preset 的 activate / update / reset / lock / delete / save-as、通知与交易配置写入、LLM 配置测试接口的成功/失败分支。

### 第三阶段：P1 规则与运营链路

- `strategies`、`events/detectors`、`optimization`、`backtest`、`reflection` 以 unit test 为主，把每个规则模块拆成输入输出断言。
- 对“策略筛选 -> 事件检测 -> advisory 触发 -> 持久化/通知”补 3 到 5 个端到端 behavior 场景，保证关键协同链路可回归。
- `advisory/telegram/*` 优先补 handler 级行为测试，验证命令路由、按钮回调、消息格式、异常兜底。
- Dashboard 只读 API 与关键页面 loader/action 做行为测试，重点覆盖空状态、错误状态、权限状态。

### 第四阶段：P2 包装层与展示层

- `prompts`、`providers`、`token_manager`、`usage_tracker`、`utils` 以 unit test 为主，验证文本拼装、参数传递、错误翻译、token 解析。
- Dashboard UI 组件只覆盖有业务分支的组件；纯样式组件不追求高覆盖率。

## 模块与测试类型建议

| 模块类别 | 优先测试方式 | 说明 |
| --- | --- | --- |
| 配置、模型、参数边界、格式转换、计算器 | `unit test` | 这类逻辑输入输出明确，最适合 TDD |
| 风控规则、调度器、下单流程、鉴权流程、策略状态流转 | `behavior-style test` + 必要 unit test | 需要验证业务语义，不应只靠底层函数断言 |
| Dashboard API routes | `behavior-style test` | 重点验证 request -> response -> side effect |
| Dashboard 组件和展示页 | `unit test` | 只测有条件分支、状态转换、关键渲染逻辑 |
| 外部 provider / OAuth / token 适配 | `unit test` | 通过 stub/mock 保持稳定；只保留少量行为测试验证关键握手流程 |
| 事件检测器、策略选择器、优化器、回测引擎 | 先 `unit test`，后补少量 `behavior-style test` | 先把规则矩阵测实，再测跨模块协同 |

## 建议新增的 BDD 场景

- 交易日亏损达到阈值时，系统停止新开仓并记录暂停原因。
- 冷却期内重复方向信号出现时，系统忽略下单。
- 强制休息期结束后，系统恢复调度但不自动补单。
- 策略参数切换前，影子运行或回测不达标时拒绝生效。
- 用户登录成功后可以访问 Dashboard，登出后再次访问被重定向。
- 修改 Dashboard 密码后，旧密码失效，新密码立即生效。
- 策略 preset 被锁定后，更新与重置接口返回受限结果。
- LLM 配置测试接口在 token 缺失、token 过期、provider 不存在时返回正确错误语义。
- 事件触发后，advisory 服务只在冷却窗口外生成新建议。
- 复盘规则命中后，系统写入新规则但不影响当前运行中的交易状态。

## 最小必要重构建议

以下调整只为提高可测性，不直接改业务核心决策：

- 限制 pytest 收集范围到 `tests/`，或把 `scripts/test_*.py` 改名，避免脚本被正式测试收集。
- 减少包级 `__init__.py` 的重导出与重量级导入，尤其是 `src/ai_trader/ai/__init__.py`、`src/ai_trader/strategies/__init__.py`、`src/ai_trader/exchange/__init__.py`、`src/ai_trader/reflection/__init__.py`、`src/ai_trader/persistence/__init__.py`、`src/ai_trader/utils/__init__.py`、`src/ai_trader/data/__init__.py`、`src/ai_trader/advisory/telegram/__init__.py`。
- 把导入期副作用挪出模块初始化：`src/ai_trader/config.py` 当前在导入时构造全局 `config`，`dashboard/app/services/auth.server.ts` 当前在模块加载时自动执行 `initializePassword()`，`dashboard/db/index.ts` 当前在模块加载时直接创建数据库连接。
- 为数据库、时钟、环境变量、HTTP 客户端、provider client 提供显式注入点，避免测试必须依赖真实环境。
- 把外部 API/OAuth/token 文件读取逻辑收敛到薄适配层，避免 route / service 直接访问文件系统和全局环境。
- 对 `scheduler`、`main`、`telegram bot` 这类编排入口，优先抽出纯函数或 service 层，再补测试；不要先改核心策略逻辑。

## 建议执行顺序

1. 修测试基座，先保证 `pytest tests` 可以稳定收集。
2. 先做 P0 的 unit test，再补 P0 的关键 BDD 场景。
3. 再补 P1 的规则矩阵和协同链路。
4. 最后收尾 P2 的 provider / prompt / UI 展示层。

## 完成标准

- `pytest tests` 可稳定收集并执行。
- P0 模块具备明确的 unit + behavior 双层保护。
- Dashboard 至少覆盖鉴权、关键写接口、关键只读页面的基础回归。
- 新增测试优先围绕业务风险，而不是单纯追求覆盖率数字。
