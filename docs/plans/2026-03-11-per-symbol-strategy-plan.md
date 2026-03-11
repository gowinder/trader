# Per-Symbol 策略配置 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将策略配置从全局设置改为按交易对独立配置，每个 symbol 选择预设 + 可微调参数。

**Architecture:** 新增 `symbol_strategy` 数据库表存储每个 symbol 的预设关联和参数覆盖。Scheduler 启动时加载 per-symbol 配置，为每个 symbol 构建独立的 StrategySelector。前端 symbols 页面改为内联展开面板，支持选预设 + 微调参数。通过 Redis Pub/Sub 实现热更新。

**Tech Stack:** PostgreSQL (Drizzle ORM), Python (pydantic, asyncio), React 19, Redis Pub/Sub

**Worktree:** `.worktrees/per-symbol-strategy` (branch: `feature/per-symbol-strategy`)

**Design Doc:** `docs/plans/2026-03-10-per-symbol-strategy-design.md`

**UI Mockup:** `docs/plans/symbol-strategy-mockup.html`

---

## Task 1: 数据库 Schema — 新增 symbol_strategy 表

**Files:**
- Modify: `dashboard/db/schema.ts` (在 activeStrategy 表后新增)

**Step 1: 在 schema.ts 中新增 symbolStrategy 表定义**

在 `activeStrategy` 表定义后（约第 490 行后）添加：

```typescript
export const symbolStrategy = pgTable(
  "symbol_strategy",
  {
    id: integer("id").primaryKey().generatedAlwaysAsIdentity(),
    symbol: varchar("symbol", { length: 20 }).notNull(),
    presetId: integer("preset_id")
      .references(() => strategyPresets.id)
      .notNull(),
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

**Step 2: 运行数据库迁移**

```bash
cd dashboard && npm run db:push
```

Expected: 迁移成功，`symbol_strategy` 表创建。

**Step 3: Commit**

```bash
git add dashboard/db/schema.ts
git commit -m "feat: add symbol_strategy table schema"
```

---

## Task 2: Python 模型 — SymbolStrategyConfig

**Files:**
- Create: `src/ai_trader/models/symbol_strategy.py`
- Test: `tests/test_symbol_strategy_model.py`

**Step 1: 写测试**

```python
# tests/test_symbol_strategy_model.py
import pytest
from ai_trader.models.symbol_strategy import SymbolStrategyConfig, merge_preset_with_overrides
from ai_trader.models.strategy_preset import StrategyPresetConfig


class TestMergePresetWithOverrides:
    def test_no_overrides_returns_preset_config(self):
        preset_config = StrategyPresetConfig(
            enabled_strategies=["trend_following"],
            strategy_weights={"trend_following": 1.0},
            ai_weight=0.6,
            quant_weight=0.4,
        )
        result = merge_preset_with_overrides(preset_config, {})
        assert result.ai_weight == 0.6
        assert result.quant_weight == 0.4

    def test_overrides_replace_preset_values(self):
        preset_config = StrategyPresetConfig(
            enabled_strategies=["trend_following"],
            strategy_weights={"trend_following": 1.0},
            ai_weight=0.6,
            quant_weight=0.4,
        )
        overrides = {"ai_weight": 0.8, "stop_loss_atr_multiplier": 2.0}
        result = merge_preset_with_overrides(preset_config, overrides)
        assert result.ai_weight == 0.8
        assert result.stop_loss_atr_multiplier == 2.0
        assert result.quant_weight == 0.4  # unchanged

    def test_invalid_override_key_ignored(self):
        preset_config = StrategyPresetConfig(
            enabled_strategies=["trend_following"],
            strategy_weights={"trend_following": 1.0},
            ai_weight=0.6,
            quant_weight=0.4,
        )
        overrides = {"nonexistent_field": 999}
        result = merge_preset_with_overrides(preset_config, overrides)
        assert result.ai_weight == 0.6


class TestSymbolStrategyConfig:
    def test_create(self):
        preset_config = StrategyPresetConfig(
            enabled_strategies=["trend_following"],
            strategy_weights={"trend_following": 1.0},
            ai_weight=0.6,
            quant_weight=0.4,
        )
        cfg = SymbolStrategyConfig(
            symbol="BTC/USDT:USDT",
            preset_name="steady_trend",
            preset_config=preset_config,
            config_overrides={"ai_weight": 0.7},
        )
        assert cfg.symbol == "BTC/USDT:USDT"
        assert cfg.merged_config.ai_weight == 0.7
        assert cfg.merged_config.quant_weight == 0.4
```

**Step 2: 运行测试验证失败**

```bash
uv run pytest tests/test_symbol_strategy_model.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'ai_trader.models.symbol_strategy'`

**Step 3: 实现模型**

```python
# src/ai_trader/models/symbol_strategy.py
"""Per-symbol strategy configuration model."""

from dataclasses import dataclass, field

from .strategy_preset import StrategyPresetConfig


def merge_preset_with_overrides(
    preset_config: StrategyPresetConfig,
    overrides: dict,
) -> StrategyPresetConfig:
    """Merge preset config with per-symbol overrides.

    Only known fields from StrategyPresetConfig are applied.
    Unknown keys in overrides are ignored.
    """
    base = preset_config.model_dump()
    valid_fields = set(base.keys())
    filtered = {k: v for k, v in overrides.items() if k in valid_fields}
    base.update(filtered)
    return StrategyPresetConfig(**base)


@dataclass
class SymbolStrategyConfig:
    """Per-symbol strategy configuration."""

    symbol: str
    preset_name: str
    preset_config: StrategyPresetConfig
    config_overrides: dict = field(default_factory=dict)

    @property
    def merged_config(self) -> StrategyPresetConfig:
        return merge_preset_with_overrides(self.preset_config, self.config_overrides)
```

**Step 4: 运行测试验证通过**

```bash
uv run pytest tests/test_symbol_strategy_model.py -v
```

Expected: 5 passed

**Step 5: Commit**

```bash
git add src/ai_trader/models/symbol_strategy.py tests/test_symbol_strategy_model.py
git commit -m "feat: add SymbolStrategyConfig model with merge logic"
```

---

## Task 3: Python 持久化 — symbol_strategy 数据库读写

**Files:**
- Modify: `src/ai_trader/persistence/strategy_service.py`
- Test: `tests/test_symbol_strategy_service.py`

**Step 1: 写测试**

```python
# tests/test_symbol_strategy_service.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from ai_trader.persistence.strategy_service import StrategyPersistenceService


class TestSymbolStrategyService:
    @pytest.fixture
    def service(self):
        svc = StrategyPersistenceService.__new__(StrategyPersistenceService)
        svc.pool = AsyncMock()
        return svc

    @pytest.mark.asyncio
    async def test_get_all_symbol_strategies_empty(self, service):
        conn = AsyncMock()
        conn.fetch.return_value = []
        service.pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        service.pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await service.get_all_symbol_strategies()
        assert result == []

    @pytest.mark.asyncio
    async def test_get_all_symbol_strategies_returns_rows(self, service):
        row = {
            "symbol": "BTC/USDT:USDT",
            "preset_name": "steady_trend",
            "config_json": {"enabled_strategies": ["trend_following"], "ai_weight": 0.6, "quant_weight": 0.4, "strategy_weights": {"trend_following": 1.0}},
            "config_overrides": {"ai_weight": 0.7},
            "enabled": True,
        }
        conn = AsyncMock()
        conn.fetch.return_value = [row]
        service.pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        service.pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await service.get_all_symbol_strategies()
        assert len(result) == 1
        assert result[0].symbol == "BTC/USDT:USDT"
        assert result[0].merged_config.ai_weight == 0.7
```

**Step 2: 运行测试验证失败**

```bash
uv run pytest tests/test_symbol_strategy_service.py -v
```

Expected: FAIL — `AttributeError: 'StrategyPersistenceService' object has no attribute 'get_all_symbol_strategies'`

**Step 3: 实现 get_all_symbol_strategies 方法**

在 `src/ai_trader/persistence/strategy_service.py` 中添加方法：

```python
async def get_all_symbol_strategies(self) -> list["SymbolStrategyConfig"]:
    """Load all enabled symbol strategy configurations from database."""
    from ai_trader.models.symbol_strategy import SymbolStrategyConfig
    from ai_trader.models.strategy_preset import StrategyPresetConfig

    query = """
        SELECT ss.symbol, sp.name as preset_name, sp.config_json,
               ss.config_overrides, ss.enabled
        FROM symbol_strategy ss
        JOIN strategy_presets sp ON ss.preset_id = sp.id
        WHERE ss.enabled = true
        ORDER BY ss.symbol
    """
    async with self.pool.acquire() as conn:
        rows = await conn.fetch(query)

    results = []
    for row in rows:
        config_json = row["config_json"] if isinstance(row["config_json"], dict) else {}
        overrides = row["config_overrides"] if isinstance(row["config_overrides"], dict) else {}
        preset_config = StrategyPresetConfig(**config_json)
        results.append(
            SymbolStrategyConfig(
                symbol=row["symbol"],
                preset_name=row["preset_name"],
                preset_config=preset_config,
                config_overrides=overrides,
            )
        )
    return results
```

**Step 4: 运行测试验证通过**

```bash
uv run pytest tests/test_symbol_strategy_service.py -v
```

Expected: 2 passed

**Step 5: Commit**

```bash
git add src/ai_trader/persistence/strategy_service.py tests/test_symbol_strategy_service.py
git commit -m "feat: add get_all_symbol_strategies to persistence service"
```

---

## Task 4: Dashboard API — 改造 GET/POST /api/symbols

**Files:**
- Modify: `dashboard/app/routes/api.symbols.ts`
- Create: `dashboard/app/routes/api.presets-list.ts` (简化版预设列表 API)

**Step 1: 改造 api.symbols.ts loader**

将当前 loader 改为同时返回 `available` 和 `configured`（含 preset 信息和 overrides）：

```typescript
// dashboard/app/routes/api.symbols.ts
import { db } from "~/db/connection";
import { symbolStrategy, strategyPresets } from "~/db/schema";
import { eq } from "drizzle-orm";
import { getRedisClient } from "~/services/redis.server";

const AVAILABLE_SYMBOLS_KEY = "trading:available_symbols";
const CONFIG_KEY = "trading:config";

export async function loader() {
  const client = await getRedisClient();

  // 1. 从 Redis 获取交易所可用 symbols
  let available: string[] = [];
  try {
    const raw = await client.get(AVAILABLE_SYMBOLS_KEY);
    if (raw) available = JSON.parse(raw);
  } catch { /* ignore */ }

  // 2. 从数据库获取已配置的 symbol strategies
  const rows = await db
    .select({
      symbol: symbolStrategy.symbol,
      presetId: symbolStrategy.presetId,
      presetName: strategyPresets.name,
      presetDisplayName: strategyPresets.displayName,
      configOverrides: symbolStrategy.configOverrides,
      configJson: strategyPresets.configJson,
      enabled: symbolStrategy.enabled,
    })
    .from(symbolStrategy)
    .innerJoin(strategyPresets, eq(symbolStrategy.presetId, strategyPresets.id))
    .where(eq(symbolStrategy.enabled, true));

  const configured = rows.map((r) => ({
    symbol: r.symbol,
    preset_name: r.presetName,
    preset_display_name: r.presetDisplayName,
    config_overrides: r.configOverrides || {},
    preset_config: r.configJson || {},
    enabled: r.enabled,
  }));

  return Response.json({ available, configured });
}
```

**Step 2: 改造 api.symbols.ts action**

```typescript
export async function action({ request }: { request: Request }) {
  const body = await request.json();
  const { configured } = body as {
    configured: Array<{
      symbol: string;
      preset_name: string;
      config_overrides: Record<string, number | boolean>;
    }>;
  };

  if (!configured || !Array.isArray(configured)) {
    return Response.json({ error: "configured array required" }, { status: 400 });
  }

  // 1. 查找所有 preset name → id 映射
  const presets = await db.select({ id: strategyPresets.id, name: strategyPresets.name }).from(strategyPresets);
  const presetMap = new Map(presets.map((p) => [p.name, p.id]));

  // 2. 将所有现有记录标为 disabled
  await db.update(symbolStrategy).set({ enabled: false, updatedAt: new Date() });

  // 3. Upsert 每个 configured symbol
  for (const item of configured) {
    const presetId = presetMap.get(item.preset_name);
    if (!presetId) continue;

    await db
      .insert(symbolStrategy)
      .values({
        symbol: item.symbol,
        presetId,
        configOverrides: item.config_overrides || {},
        enabled: true,
        updatedAt: new Date(),
      })
      .onConflictDoUpdate({
        target: symbolStrategy.symbol,
        set: {
          presetId,
          configOverrides: item.config_overrides || {},
          enabled: true,
          updatedAt: new Date(),
        },
      });
  }

  // 4. 同步到 Redis（保持 trading:config 中 trading_symbols 的兼容性）
  const client = await getRedisClient();
  const enabledSymbols = configured.map((c) => c.symbol);
  try {
    const prev = await client.get(CONFIG_KEY);
    const prevConfig = prev ? JSON.parse(prev) : {};
    const newConfig = {
      ...prevConfig,
      trading_symbols: enabledSymbols.join(","),
      updatedAt: new Date().toISOString(),
    };
    await client.set(CONFIG_KEY, JSON.stringify(newConfig));
    await client.publish("trading:config:updated", JSON.stringify(newConfig));

    // 发布 symbol strategy 专用更新事件
    await client.publish("symbol_strategy:updated", JSON.stringify({ symbols: enabledSymbols }));
  } catch { /* ignore redis errors */ }

  return Response.json({ success: true, count: configured.length });
}
```

**Step 3: 创建简化版预设列表 API**

```typescript
// dashboard/app/routes/api.presets-list.ts
import { db } from "~/db/connection";
import { strategyPresets } from "~/db/schema";

export async function loader() {
  const presets = await db
    .select({
      id: strategyPresets.id,
      name: strategyPresets.name,
      displayName: strategyPresets.displayName,
      description: strategyPresets.description,
      category: strategyPresets.category,
      riskLevel: strategyPresets.riskLevel,
      configJson: strategyPresets.configJson,
    })
    .from(strategyPresets)
    .orderBy(strategyPresets.id);

  return Response.json(
    presets.map((p) => ({
      name: p.name,
      display_name: p.displayName,
      description: p.description,
      category: p.category,
      risk_level: p.riskLevel,
      config: p.configJson,
    }))
  );
}
```

**Step 4: 注册路由**

在 `dashboard/app/routes.ts` 中确认 `api.presets-list` 路由已注册（React Router v7 文件路由应自动注册）。

**Step 5: Commit**

```bash
git add dashboard/app/routes/api.symbols.ts dashboard/app/routes/api.presets-list.ts
git commit -m "feat: per-symbol strategy API endpoints"
```

---

## Task 5: 前端 — 改造 Symbols 页面

**Files:**
- Modify: `dashboard/app/routes/dashboard.symbols.tsx`

**Step 1: 重写 symbols 页面**

完整重写 `dashboard.symbols.tsx`，核心变更：

1. **数据结构** — 从 `{ available, enabled }` 改为 `{ available, configured }`
2. **状态管理** — `Map<string, SymbolConfig>` 替代 `Set<string>`
3. **内联展开** — 每个 enabled symbol 行可展开显示预设选择 + 参数微调
4. **预设加载** — fetch `/api/presets-list` 获取所有可用预设

关键接口定义：

```typescript
interface SymbolConfig {
  symbol: string;
  preset_name: string;
  preset_display_name: string;
  config_overrides: Record<string, number>;
  preset_config: Record<string, any>;
}

interface PresetOption {
  name: string;
  display_name: string;
  description: string;
  category: string;
  risk_level: string;
  config: Record<string, any>;
}

// 可微调参数定义
const TUNABLE_PARAMS = {
  weights: [
    { key: "ai_weight", label: "AI 权重", min: 0, max: 1, step: 0.05 },
    { key: "quant_weight", label: "量化权重", min: 0, max: 1, step: 0.05 },
    { key: "sentiment_weight", label: "情绪权重", min: 0, max: 1, step: 0.05 },
  ],
  risk: [
    { key: "stop_loss_atr_multiplier", label: "止损 ATR 倍数", min: 0.5, max: 10, step: 0.5 },
    { key: "take_profit_atr_multiplier", label: "止盈 ATR 倍数", min: 1, max: 20, step: 0.5 },
    { key: "max_position_pct", label: "最大仓位 %", min: 1, max: 50, step: 1 },
  ],
} as const;
```

核心组件结构：
- `SymbolsPage` — 主页面，管理状态和保存
- `SymbolRow` — 单个 symbol 行（含展开/收起）
- `StrategyPanel` — 展开面板（预设下拉 + 参数微调）

参考 UI mockup: `docs/plans/symbol-strategy-mockup.html`

**Step 2: 验证前端构建**

```bash
cd dashboard && npm run build
```

Expected: 构建成功

**Step 3: Commit**

```bash
git add dashboard/app/routes/dashboard.symbols.tsx
git commit -m "feat: symbols page with per-symbol strategy config UI"
```

---

## Task 6: Scheduler — 加载 per-symbol 策略配置

**Files:**
- Modify: `src/ai_trader/scheduler.py`
- Modify: `src/ai_trader/ai/hybrid_decision.py`

**Step 1: 修改 HybridDecisionEngine 支持外部传入策略配置**

当前 `HybridDecisionEngine.__init__` 从全局 `config` 读取 `enabled_strategies`。
改为支持传入 per-symbol 配置：

在 `src/ai_trader/ai/hybrid_decision.py` 第 39-50 行区域，修改构造函数：

```python
def __init__(self, llm_client: LLMClient, symbol_strategy_config: "StrategyPresetConfig | None" = None):
    """Initialize hybrid decision engine.

    Args:
        llm_client: LLM client
        symbol_strategy_config: Per-symbol strategy config. If None, falls back to global config.
    """
    super().__init__(llm_client)

    if symbol_strategy_config:
        enabled = symbol_strategy_config.enabled_strategies
        self._symbol_config = symbol_strategy_config
    else:
        enabled = config.enabled_strategies if config.enable_quant_strategies else []
        self._symbol_config = None

    if enabled:
        self.market_classifier = MarketClassifier()
        self.strategy_selector = StrategySelector(enabled)
    else:
        self.market_classifier = None
        self.strategy_selector = None
```

同时修改 `hybrid_decision.py` 中使用 `config.ai_weight` / `config.quant_weight` 的地方，优先使用 `self._symbol_config`。

**Step 2: 修改 scheduler.py — 加载 per-symbol 配置**

在 `Scheduler.__init__`（约第 65-75 行区域）添加：

```python
self._symbol_strategy_configs: dict[str, SymbolStrategyConfig] = {}
self._symbol_engines: dict[str, HybridDecisionEngine] = {}
```

新增方法（在 `_init_redis` 附近）：

```python
async def _load_symbol_strategies(self):
    """从数据库加载所有 symbol 的策略配置，构建 per-symbol decision engine。"""
    from ai_trader.models.symbol_strategy import SymbolStrategyConfig
    from ai_trader.persistence.strategy_service import StrategyPersistenceService

    if not self._strategy_service:
        return

    try:
        configs = await self._strategy_service.get_all_symbol_strategies()
        new_configs = {cfg.symbol: cfg for cfg in configs}
        new_engines = {}

        for symbol, cfg in new_configs.items():
            merged = cfg.merged_config
            new_engines[symbol] = HybridDecisionEngine(self.llm, symbol_strategy_config=merged)

        self._symbol_strategy_configs = new_configs
        self._symbol_engines = new_engines
        logger.info(f"Loaded per-symbol strategies for {len(new_configs)} symbols")
    except Exception as e:
        logger.error(f"Failed to load symbol strategies: {e}")
```

**Step 3: 修改决策循环**

在 `_run_cycle_for_symbol_impl`（约第 2198 行）中，将：
```python
decision, tech, risk = await self.decision_engine.analyze_and_decide(...)
```

改为：
```python
engine = self._symbol_engines.get(symbol, self.decision_engine)
decision, tech, risk = await engine.analyze_and_decide(...)
```

**Step 4: 添加 Redis 热更新监听**

在 `_config_listener`（约第 287 行区域）的 pubsub 订阅中，添加对 `symbol_strategy:updated` channel 的监听：

```python
# 在 pubsub.subscribe 中添加 channel
await pubsub.subscribe("trading:config:updated", "symbol_strategy:updated")

# 在消息处理中添加
if channel == "symbol_strategy:updated":
    logger.info("Symbol strategy config updated, reloading...")
    await self._load_symbol_strategies()
```

**Step 5: 在启动流程中调用加载**

在 `_init_redis` 完成后（约第 384 行之后），调用：

```python
await self._load_symbol_strategies()
```

**Step 6: 运行测试**

```bash
uv run pytest tests/ -v
```

Expected: 所有现有测试通过（655+），无回归

**Step 7: Commit**

```bash
git add src/ai_trader/ai/hybrid_decision.py src/ai_trader/scheduler.py
git commit -m "feat: scheduler loads per-symbol strategy configs with hot reload"
```

---

## Task 7: Scheduler — EventDetector per-symbol 策略

**Files:**
- Modify: `src/ai_trader/scheduler.py` (行 371 区域)

**Step 1: 修改 EventDetector 初始化**

当前代码（约第 371 行）：
```python
self._event_detectors[symbol] = EventDetector(
    event_config=self._event_trigger_config,
    enabled_strategies=config.enabled_strategies,
)
```

改为：
```python
symbol_cfg = self._symbol_strategy_configs.get(symbol)
enabled_strats = symbol_cfg.merged_config.enabled_strategies if symbol_cfg else config.enabled_strategies
self._event_detectors[symbol] = EventDetector(
    event_config=self._event_trigger_config,
    enabled_strategies=enabled_strats,
)
```

**Step 2: 在热更新回调中重建 EventDetector**

在 `_load_symbol_strategies` 末尾添加：

```python
# 重建受影响 symbol 的 EventDetector
for symbol, cfg in self._symbol_strategy_configs.items():
    if symbol in self._event_detectors:
        self._event_detectors[symbol] = EventDetector(
            event_config=self._event_trigger_config,
            enabled_strategies=cfg.merged_config.enabled_strategies,
        )
```

**Step 3: 运行测试**

```bash
uv run pytest tests/ -v
```

Expected: 全部通过

**Step 4: Commit**

```bash
git add src/ai_trader/scheduler.py
git commit -m "feat: EventDetector uses per-symbol strategy config"
```

---

## Task 8: 清理 — 废弃全局 active_strategy

**Files:**
- Modify: `src/ai_trader/scheduler.py` (移除全局预设切换相关代码)

**Step 1: 查找并标记废弃代码**

在 scheduler.py 中找到使用全局 `active_strategy` / 全局预设切换的代码（约第 429 行 `self.decision_engine = HybridDecisionEngine(self.llm)` 的重建逻辑）。

不删除代码，而是添加注释标记为 deprecated，后续版本移除：

```python
# DEPRECATED: Global preset switching. Per-symbol config now handled by _symbol_engines.
# This remains as fallback for symbols without per-symbol config.
```

**Step 2: 运行完整测试**

```bash
uv run pytest tests/ -v
```

Expected: 全部通过

**Step 3: 前端构建验证**

```bash
cd dashboard && npm run build
```

Expected: 构建成功

**Step 4: Commit**

```bash
git add -A
git commit -m "chore: mark global active_strategy as deprecated, per-symbol config is primary"
```

---

## Task 9: 集成测试

**Files:**
- Create: `tests/test_per_symbol_integration.py`

**Step 1: 写集成测试**

```python
# tests/test_per_symbol_integration.py
"""Integration tests for per-symbol strategy configuration."""
import pytest
from ai_trader.models.symbol_strategy import SymbolStrategyConfig, merge_preset_with_overrides
from ai_trader.models.strategy_preset import StrategyPresetConfig
from ai_trader.strategies.strategy_selector import StrategySelector
from ai_trader.strategies.presets import SYSTEM_PRESETS, get_preset_by_name


class TestPerSymbolIntegration:
    """Test that different symbols can use different strategies."""

    def test_btc_uses_trend_following(self):
        preset = get_preset_by_name("steady_trend")
        cfg = SymbolStrategyConfig(
            symbol="BTC/USDT:USDT",
            preset_name="steady_trend",
            preset_config=preset.config,
            config_overrides={},
        )
        selector = StrategySelector(cfg.merged_config.enabled_strategies)
        assert "trend_following" in selector.strategies

    def test_doge_uses_scalping(self):
        preset = get_preset_by_name("mild_scalping")
        cfg = SymbolStrategyConfig(
            symbol="DOGE/USDT:USDT",
            preset_name="mild_scalping",
            preset_config=preset.config,
            config_overrides={},
        )
        selector = StrategySelector(cfg.merged_config.enabled_strategies)
        assert "mean_reversion" in selector.strategies
        assert "trend_following" in selector.strategies

    def test_override_weights(self):
        preset = get_preset_by_name("steady_trend")
        cfg = SymbolStrategyConfig(
            symbol="ETH/USDT:USDT",
            preset_name="steady_trend",
            preset_config=preset.config,
            config_overrides={"ai_weight": 0.8, "quant_weight": 0.2},
        )
        merged = cfg.merged_config
        assert merged.ai_weight == 0.8
        assert merged.quant_weight == 0.2
        # Unchanged params
        assert merged.stop_loss_atr_multiplier == preset.config.stop_loss_atr_multiplier

    def test_different_selectors_independent(self):
        """Two symbols should have independent StrategySelector instances."""
        btc_preset = get_preset_by_name("steady_trend")
        doge_preset = get_preset_by_name("aggressive_scalping")

        btc_selector = StrategySelector(btc_preset.config.enabled_strategies)
        doge_selector = StrategySelector(doge_preset.config.enabled_strategies)

        assert set(btc_selector.strategies.keys()) != set(doge_selector.strategies.keys()) or \
               len(btc_selector.strategies) != len(doge_selector.strategies)

    def test_all_presets_produce_valid_selector(self):
        """Every system preset should produce a working StrategySelector."""
        for preset in SYSTEM_PRESETS:
            selector = StrategySelector(preset.config.enabled_strategies)
            assert len(selector.strategies) > 0, f"Preset {preset.name} has no strategies"
```

**Step 2: 运行测试**

```bash
uv run pytest tests/test_per_symbol_integration.py -v
```

Expected: 5 passed

**Step 3: 运行全部测试确认无回归**

```bash
uv run pytest tests/ -v
```

Expected: 660+ passed, 5 skipped

**Step 4: Commit**

```bash
git add tests/test_per_symbol_integration.py
git commit -m "test: add per-symbol strategy integration tests"
```

---

## 实施顺序总结

| Task | 内容 | 依赖 |
|------|------|------|
| 1 | DB Schema: symbol_strategy 表 | 无 |
| 2 | Python Model: SymbolStrategyConfig | 无 |
| 3 | Python Persistence: 数据库读写 | Task 1, 2 |
| 4 | Dashboard API: GET/POST /api/symbols | Task 1, 3 |
| 5 | Frontend: symbols 页面改造 | Task 4 |
| 6 | Scheduler: per-symbol engine 加载 | Task 2, 3 |
| 7 | Scheduler: EventDetector per-symbol | Task 6 |
| 8 | 清理: 废弃全局 active_strategy | Task 6, 7 |
| 9 | 集成测试 | Task 2 |

可并行: Task 1+2, Task 4+6+9, Task 5(等 Task 4), Task 7(等 Task 6), Task 8(等 Task 7)
