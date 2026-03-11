# Per-Symbol 策略配置设计

## 目标

将策略配置从全局设置改为按交易对（symbol）独立配置，每个 symbol 选择预设 + 可微调参数。启用 symbol 时必须选择预设。

## 数据模型

### 新增表：`symbol_strategy`

```sql
CREATE TABLE symbol_strategy (
  id SERIAL PRIMARY KEY,
  symbol VARCHAR(20) NOT NULL UNIQUE,        -- "BTC/USDT:USDT"
  preset_id INTEGER NOT NULL REFERENCES strategy_presets(id),
  config_overrides JSONB DEFAULT '{}',       -- 只存与预设不同的参数
  enabled BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX idx_symbol_strategy_symbol ON symbol_strategy(symbol);
```

### Drizzle Schema（`dashboard/db/schema.ts`）

```ts
export const symbolStrategy = pgTable(
  "symbol_strategy",
  {
    id: integer("id").primaryKey().generatedAlwaysAsIdentity(),
    symbol: varchar("symbol", { length: 20 }).unique().notNull(),
    presetId: integer("preset_id").references(() => strategyPresets.id).notNull(),
    configOverrides: jsonb("config_overrides").default({}).notNull(),
    enabled: boolean("enabled").default(true).notNull(),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
    updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => ({
    symbolIdx: uniqueIndex("idx_symbol_strategy_symbol").on(table.symbol),
  })
);
```

### `config_overrides` 示例

```json
{
  "ai_weight": 0.7,
  "stop_loss_atr_multiplier": 2.5
}
```

只存差异字段，未覆盖的参数从关联 preset 的 `config_json` 继承。

### 废弃

- `active_strategy` 表停用（全局策略概念去掉）
- `config.py` 中 `enabled_strategies` / `ai_weight` / `quant_weight` 降级为系统 fallback，不再直接用于决策

## API 设计

### GET /api/symbols

```json
{
  "available": ["BTC/USDT:USDT", "ETH/USDT:USDT", ...],
  "configured": [
    {
      "symbol": "BTC/USDT:USDT",
      "preset_name": "steady_trend",
      "preset_display_name": "稳健趋势",
      "config_overrides": {"ai_weight": 0.7, "stop_loss_atr_multiplier": 2.5},
      "enabled": true
    },
    {
      "symbol": "DOGE/USDT:USDT",
      "preset_name": "mild_scalping",
      "preset_display_name": "温和剥头皮",
      "config_overrides": {},
      "enabled": true
    }
  ]
}
```

### POST /api/symbols

```json
{
  "configured": [
    {
      "symbol": "BTC/USDT:USDT",
      "preset_name": "steady_trend",
      "config_overrides": {"ai_weight": 0.7, "stop_loss_atr_multiplier": 2.5}
    },
    {
      "symbol": "DOGE/USDT:USDT",
      "preset_name": "mild_scalping",
      "config_overrides": {}
    }
  ]
}
```

未出现在 `configured` 中的 symbol 视为禁用（`enabled = false`）。

### GET /api/presets

返回所有可用预设，供前端下拉选择：

```json
[
  {
    "name": "steady_trend",
    "display_name": "稳健趋势",
    "description": "跟随明确趋势，低频交易，严格风控",
    "category": "trend",
    "risk_level": "low",
    "config": {
      "enabled_strategies": ["trend_following"],
      "ai_weight": 0.6,
      "quant_weight": 0.4,
      "sentiment_weight": 0.2,
      "stop_loss_atr_multiplier": 3.0,
      "take_profit_atr_multiplier": 8.0,
      "max_position_pct": 15.0,
      ...
    }
  },
  ...
]
```

## 后端改造

### 配置合并逻辑

新增 `src/ai_trader/strategies/symbol_config.py`：

```python
@dataclass
class SymbolStrategyConfig:
    symbol: str
    preset_name: str
    merged_config: StrategyPresetConfig  # preset.config | overrides

def merge_config(preset_config: dict, overrides: dict) -> dict:
    """overrides 中的字段覆盖 preset 默认值，其余继承"""
    merged = {**preset_config, **overrides}
    return merged

def load_symbol_configs(db_rows, presets) -> dict[str, SymbolStrategyConfig]:
    """从数据库加载所有 symbol 策略配置"""
    result = {}
    for row in db_rows:
        preset = presets[row.preset_name]
        merged = merge_config(preset.config.model_dump(), row.config_overrides)
        result[row.symbol] = SymbolStrategyConfig(
            symbol=row.symbol,
            preset_name=row.preset_name,
            merged_config=StrategyPresetConfig(**merged),
        )
    return result
```

### Scheduler 改造

`src/ai_trader/scheduler.py` 核心变更：

1. **启动时** — 从数据库加载所有 symbol 的策略配置
2. **构建 per-symbol selector** — `dict[str, StrategySelector]`，每个 symbol 用各自的 `enabled_strategies` 初始化
3. **决策循环** — 遍历 enabled symbols 时，取对应的 selector 和 merged config 传入 `HybridDecisionEngine`
4. **热更新** — 通过 Redis Pub/Sub channel `symbol_strategy_updated` 监听配置变更，收到消息后重新加载

```python
# 伪代码
class Scheduler:
    async def _load_symbol_strategies(self):
        """从数据库加载 symbol 策略映射"""
        rows = await self.db.fetch_all_symbol_strategies()
        self.symbol_configs = load_symbol_configs(rows, self.presets)
        self.symbol_selectors = {
            symbol: StrategySelector(cfg.merged_config.enabled_strategies)
            for symbol, cfg in self.symbol_configs.items()
        }

    async def _on_strategy_updated(self, message):
        """Redis Pub/Sub 回调，热更新策略配置"""
        await self._load_symbol_strategies()

    async def _make_decision(self, symbol: str, ...):
        cfg = self.symbol_configs[symbol]
        selector = self.symbol_selectors[symbol]
        # 用 cfg.merged_config 的 ai_weight, quant_weight 等参数
        engine = HybridDecisionEngine(config=cfg.merged_config, selector=selector)
        ...
```

### Dashboard API 路由

`dashboard/app/routes/api.symbols.ts` 改造：

- `loader`: JOIN `symbol_strategy` + `strategy_presets` 返回 configured 列表
- `action`: 接收 configured 数组，upsert `symbol_strategy` 表，未出现的标记 `enabled=false`
- 保存后 publish Redis 消息通知 trader 热更新

## 前端改造

### Symbols 页面（`dashboard/app/routes/dashboard.symbols.tsx`）

**数据结构变更：**

```ts
interface SymbolConfig {
  symbol: string;
  preset_name: string;
  preset_display_name: string;
  config_overrides: Record<string, number | boolean>;
  enabled: boolean;
}

interface SymbolsData {
  available: string[];
  configured: SymbolConfig[];
}

interface PresetOption {
  name: string;
  display_name: string;
  description: string;
  config: Record<string, any>;
}
```

**交互逻辑：**

1. 启用 symbol 开关 → 自动展开，必须选预设
2. 已配置 symbol 行显示预设标签（有 overrides 时标"已修改"黄色）
3. 点击行展开/收起内联参数面板
4. 展开面板：
   - 预设下拉框（加载 `/api/presets`）
   - 启用策略标签展示
   - 左栏：权重（ai_weight, quant_weight, sentiment_weight）
   - 右栏：风控（stop_loss_atr_multiplier, take_profit_atr_multiplier, max_position_pct）
   - 参数输入框旁显示预设默认值，修改过的黄色高亮
   - "重置为预设默认"按钮清除 overrides
5. 切换预设 → 清除所有 overrides
6. 页面级统一保存按钮

**UI 示意图：** `docs/plans/symbol-strategy-mockup.html`

## 可微调参数列表

| 参数 | 类型 | 说明 |
|------|------|------|
| ai_weight | float | AI 决策权重 |
| quant_weight | float | 量化策略权重 |
| sentiment_weight | float | 情绪分析权重 |
| stop_loss_atr_multiplier | float | 止损 ATR 倍数 |
| take_profit_atr_multiplier | float | 止盈 ATR 倍数 |
| max_position_pct | float | 最大仓位百分比 |

后续可按需扩展更多参数（如 `min_trade_interval_seconds`、`enable_pyramid` 等），前端只需在面板中添加对应输入框。

## 实施阶段

### Phase 1: 数据层
- 新增 `symbol_strategy` Drizzle schema + 迁移
- 新增 `src/ai_trader/strategies/symbol_config.py` 配置合并模块

### Phase 2: API 层
- 改造 `GET/POST /api/symbols` 端点
- 新增 `GET /api/presets` 端点

### Phase 3: 前端
- 改造 symbols 页面，内联展开面板，预设选择 + 参数微调

### Phase 4: Scheduler 集成
- Scheduler 启动加载 per-symbol 配置
- 决策循环按 symbol 使用各自策略
- Redis Pub/Sub 热更新

### Phase 5: 清理
- 废弃 `active_strategy` 相关代码
- `config.py` 全局策略参数降级为 fallback
