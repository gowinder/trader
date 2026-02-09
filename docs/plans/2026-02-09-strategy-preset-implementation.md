# 策略预设选择功能实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现 7 种预设策略模板，支持在 Dashboard 一键切换，PostgreSQL 持久化 + Redis 缓存，Scheduler 运行时动态加载。

**Architecture:** 后端新增 StrategyPreset 模型和持久化方法，Scheduler 每周期从 Redis 读取活跃策略配置并重建决策引擎参数。Dashboard 新增策略页面，通过 API 管理模板切换。

**Tech Stack:** Python/Pydantic (后端模型), asyncpg (数据库), redis (缓存), React Router v7 + Drizzle ORM + shadcn/ui (前端)

---

## Task 1: 后端 - StrategyPreset 数据模型

**Files:**
- Create: `src/ai_trader/models/strategy_preset.py`
- Modify: `src/ai_trader/models/__init__.py` (如果存在，添加导出)

**Step 1: 创建 StrategyPreset Pydantic 模型**

```python
# src/ai_trader/models/strategy_preset.py
"""策略预设模型"""

from typing import Optional
from pydantic import BaseModel, Field


class StrategyPresetConfig(BaseModel):
    """策略预设的完整配置参数"""

    # 策略组合
    enabled_strategies: list[str]
    strategy_weights: dict[str, float]

    # 决策权重
    ai_weight: float = Field(ge=0, le=1)
    quant_weight: float = Field(ge=0, le=1)
    sentiment_weight: float = Field(ge=0, le=1, default=0)

    # 周期和频率
    timeframes: list[str]
    min_trade_interval_seconds: int = Field(ge=60)

    # 风控参数
    stop_loss_atr_multiplier: float = Field(ge=0.5)
    take_profit_atr_multiplier: float = Field(ge=0.5)
    max_position_pct: float = Field(ge=1, le=100)
    enable_pyramid: bool = False
    max_pyramid_times: int = Field(ge=0, default=0)

    # 开关和特殊参数
    enable_sentiment: bool = False
    min_profit_threshold: float = Field(ge=0, default=0)
    use_market_order_only: bool = False


class StrategyPreset(BaseModel):
    """策略预设模板"""

    id: Optional[int] = None
    name: str
    display_name: str
    description: str
    category: str  # "trend" / "range" / "breakout" / "scalping" / "balanced"
    risk_level: str  # "lowest" / "low" / "medium_low" / "medium" / "medium_high"
    config: StrategyPresetConfig
    is_system: bool = True
```

**Step 2: 验证模块可导入**

Run: `cd /Users/gowinder/code/gowinder/trader && python -c "from ai_trader.models.strategy_preset import StrategyPreset, StrategyPresetConfig; print('OK')"`
Expected: OK

**Step 3: Commit**

```bash
git add src/ai_trader/models/strategy_preset.py
git commit -m "feat(strategy): add StrategyPreset pydantic model"
```

---

## Task 2: 后端 - 7 个预设模板定义

**Files:**
- Create: `src/ai_trader/strategies/presets.py`

**Step 1: 定义 7 个系统预设模板**

```python
# src/ai_trader/strategies/presets.py
"""系统内置策略预设模板"""

from ..models.strategy_preset import StrategyPreset, StrategyPresetConfig

SYSTEM_PRESETS: list[StrategyPreset] = [
    StrategyPreset(
        name="steady_trend",
        display_name="稳健趋势",
        description="跟随明确趋势，低频交易，严格风控",
        category="trend",
        risk_level="low",
        config=StrategyPresetConfig(
            enabled_strategies=["trend_following"],
            strategy_weights={"trend_following": 1.0},
            ai_weight=0.6,
            quant_weight=0.4,
            sentiment_weight=0.2,
            timeframes=["1h", "4h"],
            min_trade_interval_seconds=21600,  # 6h
            stop_loss_atr_multiplier=3.0,
            take_profit_atr_multiplier=8.0,
            max_position_pct=15.0,
            enable_pyramid=False,
            max_pyramid_times=0,
            enable_sentiment=True,
            min_profit_threshold=0,
            use_market_order_only=False,
        ),
    ),
    StrategyPreset(
        name="aggressive_trend",
        display_name="激进趋势",
        description="强趋势市场积极跟进，允许加仓放大收益",
        category="trend",
        risk_level="medium_high",
        config=StrategyPresetConfig(
            enabled_strategies=["trend_following", "breakout"],
            strategy_weights={"trend_following": 0.7, "breakout": 0.3},
            ai_weight=0.4,
            quant_weight=0.6,
            sentiment_weight=0,
            timeframes=["15m", "1h"],
            min_trade_interval_seconds=7200,  # 2h
            stop_loss_atr_multiplier=2.0,
            take_profit_atr_multiplier=5.0,
            max_position_pct=30.0,
            enable_pyramid=True,
            max_pyramid_times=2,
            enable_sentiment=False,
            min_profit_threshold=0,
            use_market_order_only=False,
        ),
    ),
    StrategyPreset(
        name="range_harvest",
        display_name="震荡收割",
        description="区间震荡市场高抛低吸，均值回归为主",
        category="range",
        risk_level="medium",
        config=StrategyPresetConfig(
            enabled_strategies=["mean_reversion", "trend_following"],
            strategy_weights={"mean_reversion": 0.8, "trend_following": 0.2},
            ai_weight=0.3,
            quant_weight=0.7,
            sentiment_weight=0.2,
            timeframes=["15m", "1h"],
            min_trade_interval_seconds=7200,  # 2h
            stop_loss_atr_multiplier=2.0,
            take_profit_atr_multiplier=3.0,
            max_position_pct=20.0,
            enable_pyramid=False,
            max_pyramid_times=0,
            enable_sentiment=True,
            min_profit_threshold=0,
            use_market_order_only=False,
        ),
    ),
    StrategyPreset(
        name="breakout_hunter",
        display_name="突破猎手",
        description="捕捉盘整后的突破行情，配合趋势确认",
        category="breakout",
        risk_level="medium",
        config=StrategyPresetConfig(
            enabled_strategies=["breakout", "trend_following"],
            strategy_weights={"breakout": 0.8, "trend_following": 0.2},
            ai_weight=0.4,
            quant_weight=0.6,
            sentiment_weight=0.2,
            timeframes=["1h", "4h"],
            min_trade_interval_seconds=14400,  # 4h
            stop_loss_atr_multiplier=2.5,
            take_profit_atr_multiplier=6.0,
            max_position_pct=25.0,
            enable_pyramid=True,
            max_pyramid_times=1,
            enable_sentiment=True,
            min_profit_threshold=0,
            use_market_order_only=False,
        ),
    ),
    StrategyPreset(
        name="mild_scalping",
        display_name="温和剥头皮",
        description="中频小利润交易，均值回归主导，适合震荡和趋势市",
        category="scalping",
        risk_level="medium_low",
        config=StrategyPresetConfig(
            enabled_strategies=["mean_reversion", "trend_following"],
            strategy_weights={"mean_reversion": 0.6, "trend_following": 0.4},
            ai_weight=0.25,
            quant_weight=0.75,
            sentiment_weight=0,
            timeframes=["5m", "15m"],
            min_trade_interval_seconds=900,  # 15min
            stop_loss_atr_multiplier=1.5,
            take_profit_atr_multiplier=2.0,
            max_position_pct=10.0,
            enable_pyramid=False,
            max_pyramid_times=0,
            enable_sentiment=False,
            min_profit_threshold=0.15,
            use_market_order_only=False,
        ),
    ),
    StrategyPreset(
        name="aggressive_scalping",
        display_name="激进剥头皮",
        description="高频快进快出，几乎纯量化驱动，薄利多销",
        category="scalping",
        risk_level="medium",
        config=StrategyPresetConfig(
            enabled_strategies=["mean_reversion", "trend_following", "breakout"],
            strategy_weights={"mean_reversion": 0.5, "trend_following": 0.3, "breakout": 0.2},
            ai_weight=0.1,
            quant_weight=0.9,
            sentiment_weight=0,
            timeframes=["1m", "5m"],
            min_trade_interval_seconds=300,  # 5min
            stop_loss_atr_multiplier=1.0,
            take_profit_atr_multiplier=1.5,
            max_position_pct=8.0,
            enable_pyramid=False,
            max_pyramid_times=0,
            enable_sentiment=False,
            min_profit_threshold=0.1,
            use_market_order_only=True,
        ),
    ),
    StrategyPreset(
        name="balanced_conservative",
        display_name="均衡保守",
        description="AI主导决策，低仓位低频率，适合不确定市场",
        category="balanced",
        risk_level="lowest",
        config=StrategyPresetConfig(
            enabled_strategies=["trend_following", "mean_reversion", "breakout"],
            strategy_weights={"trend_following": 0.5, "mean_reversion": 0.3, "breakout": 0.2},
            ai_weight=0.7,
            quant_weight=0.3,
            sentiment_weight=0.2,
            timeframes=["4h", "1d"],
            min_trade_interval_seconds=43200,  # 12h
            stop_loss_atr_multiplier=4.0,
            take_profit_atr_multiplier=6.0,
            max_position_pct=10.0,
            enable_pyramid=False,
            max_pyramid_times=0,
            enable_sentiment=True,
            min_profit_threshold=0,
            use_market_order_only=False,
        ),
    ),
]


def get_preset_by_name(name: str) -> StrategyPreset | None:
    """按名称获取预设模板"""
    for preset in SYSTEM_PRESETS:
        if preset.name == name:
            return preset
    return None


DEFAULT_PRESET_NAME = "steady_trend"
```

**Step 2: 验证预设定义**

Run: `cd /Users/gowinder/code/gowinder/trader && python -c "from ai_trader.strategies.presets import SYSTEM_PRESETS, DEFAULT_PRESET_NAME; print(f'{len(SYSTEM_PRESETS)} presets, default={DEFAULT_PRESET_NAME}')"`
Expected: `7 presets, default=steady_trend`

**Step 3: Commit**

```bash
git add src/ai_trader/strategies/presets.py
git commit -m "feat(strategy): define 7 system preset templates"
```

---

## Task 3: 数据库 - 新增 strategy_presets 和 active_strategy 表

**Files:**
- Modify: `dashboard/db/schema.ts` (添加两个新表定义)
- 新 migration 将通过 `drizzle-kit generate` 自动生成

**Step 1: 在 schema.ts 末尾添加新表定义**

在 `dashboard/db/schema.ts` 的 `operationLogs` 表之后、关系定义之前，添加：

```typescript
// ==================== 策略预设 ====================

export const strategyPresets = pgTable(
  "strategy_presets",
  {
    id: integer("id").primaryKey().generatedAlwaysAsIdentity(),
    name: varchar("name", { length: 50 }).unique().notNull(),
    displayName: varchar("display_name", { length: 100 }).notNull(),
    description: text("description"),
    category: varchar("category", { length: 20 }).notNull(),
    riskLevel: varchar("risk_level", { length: 20 }).notNull(),
    configJson: jsonb("config_json").notNull(),
    isSystem: boolean("is_system").default(true).notNull(),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
    updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => ({
    nameIdx: uniqueIndex("idx_strategy_presets_name").on(table.name),
  })
);

export const activeStrategy = pgTable(
  "active_strategy",
  {
    id: integer("id").primaryKey().generatedAlwaysAsIdentity(),
    presetId: integer("preset_id")
      .references(() => strategyPresets.id)
      .notNull(),
    activatedAt: timestamp("activated_at", { withTimezone: true }).notNull().defaultNow(),
    deactivatedAt: timestamp("deactivated_at", { withTimezone: true }),
  },
  (table) => ({
    activeIdx: index("idx_active_strategy_active").on(table.deactivatedAt),
  })
);
```

**Step 2: 生成 migration**

Run: `cd /Users/gowinder/code/gowinder/trader/dashboard && npx drizzle-kit generate`

**Step 3: 执行 migration**

Run: `cd /Users/gowinder/code/gowinder/trader/dashboard && npx drizzle-kit migrate`

**Step 4: Commit**

```bash
git add dashboard/db/schema.ts dashboard/db/migrations/
git commit -m "feat(db): add strategy_presets and active_strategy tables"
```

---

## Task 4: 后端 - 策略预设持久化服务

**Files:**
- Create: `src/ai_trader/persistence/strategy_service.py`
- Modify: `src/ai_trader/persistence/__init__.py` (添加导出)

**Step 1: 创建 StrategyPresetService**

```python
# src/ai_trader/persistence/strategy_service.py
"""策略预设持久化服务"""

import json
from typing import Optional
from datetime import datetime, timezone

from .database import DatabaseManager
from ..models.strategy_preset import StrategyPreset, StrategyPresetConfig
from ..strategies.presets import SYSTEM_PRESETS, DEFAULT_PRESET_NAME
from ..utils.logger import logger


class StrategyPresetService:
    """策略预设的数据库操作"""

    def __init__(self, db: DatabaseManager):
        self.db = db

    async def init_system_presets(self):
        """初始化系统预设模板（仅插入不存在的）"""
        for preset in SYSTEM_PRESETS:
            existing = await self.db.fetchval(
                "SELECT id FROM strategy_presets WHERE name = $1",
                preset.name,
            )
            if existing is None:
                await self.db.execute(
                    """INSERT INTO strategy_presets
                    (name, display_name, description, category, risk_level, config_json, is_system)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)""",
                    preset.name,
                    preset.display_name,
                    preset.description,
                    preset.category,
                    preset.risk_level,
                    json.dumps(preset.config.model_dump()),
                    True,
                )
                logger.info(f"Initialized system preset: {preset.name}")
            else:
                # 更新已有系统预设的配置
                await self.db.execute(
                    """UPDATE strategy_presets
                    SET display_name=$2, description=$3, category=$4, risk_level=$5,
                        config_json=$6, updated_at=NOW()
                    WHERE name=$1 AND is_system=TRUE""",
                    preset.name,
                    preset.display_name,
                    preset.description,
                    preset.category,
                    preset.risk_level,
                    json.dumps(preset.config.model_dump()),
                )

    async def get_all_presets(self) -> list[dict]:
        """获取所有预设模板"""
        rows = await self.db.fetch(
            "SELECT * FROM strategy_presets ORDER BY id"
        )
        return [dict(r) for r in rows]

    async def get_preset_by_id(self, preset_id: int) -> Optional[dict]:
        """按 ID 获取预设"""
        row = await self.db.fetchrow(
            "SELECT * FROM strategy_presets WHERE id = $1", preset_id
        )
        return dict(row) if row else None

    async def get_active_preset(self) -> Optional[dict]:
        """获取当前激活的策略预设"""
        row = await self.db.fetchrow(
            """SELECT sp.*, a.activated_at
            FROM active_strategy a
            JOIN strategy_presets sp ON sp.id = a.preset_id
            WHERE a.deactivated_at IS NULL
            ORDER BY a.activated_at DESC LIMIT 1"""
        )
        return dict(row) if row else None

    async def activate_preset(self, preset_id: int) -> bool:
        """激活指定预设（停用当前活跃的）"""
        # 验证预设存在
        preset = await self.get_preset_by_id(preset_id)
        if not preset:
            return False

        # 停用当前活跃预设
        await self.db.execute(
            """UPDATE active_strategy SET deactivated_at = NOW()
            WHERE deactivated_at IS NULL"""
        )

        # 激活新预设
        await self.db.execute(
            "INSERT INTO active_strategy (preset_id) VALUES ($1)",
            preset_id,
        )
        logger.info(f"Activated strategy preset: {preset['name']}")
        return True

    async def get_activation_history(self, limit: int = 20) -> list[dict]:
        """获取策略切换历史"""
        rows = await self.db.fetch(
            """SELECT a.*, sp.name, sp.display_name
            FROM active_strategy a
            JOIN strategy_presets sp ON sp.id = a.preset_id
            ORDER BY a.activated_at DESC LIMIT $1""",
            limit,
        )
        return [dict(r) for r in rows]

    async def get_preset_stats(self, preset_id: int) -> dict:
        """获取某个预设在激活期间的交易统计"""
        rows = await self.db.fetch(
            """SELECT a.activated_at, a.deactivated_at
            FROM active_strategy a WHERE a.preset_id = $1
            ORDER BY a.activated_at""",
            preset_id,
        )

        total_trades = 0
        total_pnl = 0.0
        wins = 0

        for r in rows:
            start = r["activated_at"]
            end = r["deactivated_at"] or datetime.now(timezone.utc)

            # 关联该时段的仓位记录
            stats = await self.db.fetchrow(
                """SELECT
                    COUNT(*) as trade_count,
                    COALESCE(SUM(realized_pnl), 0) as total_pnl,
                    COUNT(*) FILTER (WHERE realized_pnl > 0) as win_count
                FROM position_history
                WHERE closed_at BETWEEN $1 AND $2""",
                start, end,
            )
            if stats:
                total_trades += stats["trade_count"]
                total_pnl += float(stats["total_pnl"])
                wins += stats["win_count"]

        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

        return {
            "preset_id": preset_id,
            "total_trades": total_trades,
            "total_pnl": round(total_pnl, 2),
            "win_rate": round(win_rate, 1),
        }

    async def ensure_default_active(self):
        """确保有活跃策略，没有则激活默认"""
        active = await self.get_active_preset()
        if active is None:
            default = await self.db.fetchval(
                "SELECT id FROM strategy_presets WHERE name = $1",
                DEFAULT_PRESET_NAME,
            )
            if default:
                await self.activate_preset(default)
                logger.info(f"Activated default preset: {DEFAULT_PRESET_NAME}")
```

**Step 2: 更新 persistence/__init__.py**

在 `src/ai_trader/persistence/__init__.py` 中添加导出：
```python
from .strategy_service import StrategyPresetService
```

**Step 3: 验证导入**

Run: `cd /Users/gowinder/code/gowinder/trader && python -c "from ai_trader.persistence.strategy_service import StrategyPresetService; print('OK')"`
Expected: OK

**Step 4: Commit**

```bash
git add src/ai_trader/persistence/strategy_service.py src/ai_trader/persistence/__init__.py
git commit -m "feat(strategy): add StrategyPresetService for DB operations"
```

---

## Task 5: 后端 - Scheduler 集成策略预设

**Files:**
- Modify: `src/ai_trader/scheduler.py`
- Modify: `src/ai_trader/ai/hybrid_decision.py`
- Modify: `src/ai_trader/strategies/signal_filter.py`
- Modify: `src/ai_trader/config.py`

**Step 1: config.py 添加从预设配置覆盖参数的方法**

在 `TradingConfig` 类中添加方法：

```python
def apply_preset(self, config_json: dict):
    """从策略预设配置覆盖交易参数"""
    self.enabled_strategies = config_json.get("enabled_strategies", self.enabled_strategies)
    self.ai_weight = config_json.get("ai_weight", self.ai_weight)
    self.quant_weight = config_json.get("quant_weight", self.quant_weight)
    self.sentiment_weight = config_json.get("sentiment_weight", self.sentiment_weight)
    self.enable_sentiment_analysis = config_json.get("enable_sentiment", self.enable_sentiment_analysis)
```

**Step 2: scheduler.py 添加策略预设加载逻辑**

在 Scheduler 类中：

1. `__init__` 添加属性：
```python
self._active_preset_name: str | None = None
self._strategy_preset_service: StrategyPresetService | None = None
```

2. 在 `_init_persistence` 方法末尾添加策略预设初始化：
```python
# 初始化策略预设
self._strategy_preset_service = StrategyPresetService(self._db)
await self._strategy_preset_service.init_system_presets()
await self._strategy_preset_service.ensure_default_active()
await self._load_active_preset()
```

3. 新增 `_load_active_preset` 方法：
```python
async def _load_active_preset(self):
    """从 Redis 或 PG 加载活跃策略预设并应用到配置"""
    preset_config = None

    # 优先从 Redis 读取
    if self._redis:
        try:
            data = await self._redis.get("strategy:active_preset")
            if data:
                preset_config = json.loads(data)
        except Exception as e:
            logger.error(f"Failed to load preset from Redis: {e}")

    # Redis 没有则从 PG 读取
    if preset_config is None and self._strategy_preset_service:
        active = await self._strategy_preset_service.get_active_preset()
        if active:
            preset_config = json.loads(active["config_json"]) if isinstance(active["config_json"], str) else active["config_json"]
            self._active_preset_name = active["name"]
            # 写入 Redis 缓存
            if self._redis:
                await self._redis.set(
                    "strategy:active_preset",
                    json.dumps({"name": active["name"], "config": preset_config}),
                )

    if preset_config:
        config = preset_config.get("config", preset_config)
        self.config.apply_preset(config)
        # 重建决策引擎
        self._decision_engine = HybridDecisionEngine(self.config, self._llm_client)
        # 更新信号过滤器间隔
        interval_sec = config.get("min_trade_interval_seconds", 21600)
        self._decision_engine.signal_filter = SignalFilter(
            min_interval_hours=interval_sec / 3600
        )
        logger.info(f"Applied strategy preset: {self._active_preset_name}")
```

4. 在 `_config_listener` 中添加对策略预设更新的监听：
```python
# 在现有 pubsub.subscribe 后增加
await pubsub.subscribe("strategy:preset:updated")
```

在消息处理中添加分支：
```python
if message["channel"] == b"strategy:preset:updated":
    await self._load_active_preset()
```

**Step 3: Commit**

```bash
git add src/ai_trader/scheduler.py src/ai_trader/ai/hybrid_decision.py src/ai_trader/strategies/signal_filter.py src/ai_trader/config.py
git commit -m "feat(strategy): integrate preset loading into Scheduler"
```

---

## Task 6: Dashboard - 数据库 schema 和 API 路由

**Files:**
- Modify: `dashboard/db/schema.ts` (已在 Task 3 完成)
- Create: `dashboard/app/routes/api.strategy-presets.ts`
- Create: `dashboard/app/routes/api.strategy-presets.activate.ts`
- Create: `dashboard/app/routes/api.strategy-presets.history.ts`

**Step 1: 创建 GET /api/strategy-presets (列表 + 活跃)**

```typescript
// dashboard/app/routes/api.strategy-presets.ts
import { db } from "db";
import { strategyPresets, activeStrategy } from "db/schema";
import { desc, eq, isNull, sql } from "drizzle-orm";
import type { Route } from "./+types/api.strategy-presets";

export async function loader(_args: Route.LoaderArgs) {
  // 获取所有预设
  const presets = await db.select().from(strategyPresets).orderBy(strategyPresets.id);

  // 获取当前活跃预设
  const [active] = await db
    .select()
    .from(activeStrategy)
    .where(isNull(activeStrategy.deactivatedAt))
    .orderBy(desc(activeStrategy.activatedAt))
    .limit(1);

  // 获取每个预设的交易统计
  const presetsWithStats = await Promise.all(
    presets.map(async (preset) => {
      // 获取该预设所有激活时段
      const activations = await db
        .select()
        .from(activeStrategy)
        .where(eq(activeStrategy.presetId, preset.id));

      let totalTrades = 0;
      let totalPnl = 0;
      let wins = 0;

      for (const activation of activations) {
        const start = activation.activatedAt;
        const end = activation.deactivatedAt || new Date();

        const [stats] = await db.execute(sql`
          SELECT
            COUNT(*)::int as trade_count,
            COALESCE(SUM(realized_pnl), 0)::float as total_pnl,
            COUNT(*) FILTER (WHERE realized_pnl > 0)::int as win_count
          FROM position_history
          WHERE closed_at BETWEEN ${start} AND ${end}
        `);

        if (stats) {
          totalTrades += Number(stats.trade_count) || 0;
          totalPnl += Number(stats.total_pnl) || 0;
          wins += Number(stats.win_count) || 0;
        }
      }

      const winRate = totalTrades > 0 ? (wins / totalTrades) * 100 : 0;

      return {
        ...preset,
        stats: {
          totalTrades,
          totalPnl: Math.round(totalPnl * 100) / 100,
          winRate: Math.round(winRate * 10) / 10,
        },
      };
    })
  );

  return Response.json({
    presets: presetsWithStats,
    activePresetId: active?.presetId ?? null,
    activatedAt: active?.activatedAt ?? null,
  });
}
```

**Step 2: 创建 POST /api/strategy-presets/activate**

```typescript
// dashboard/app/routes/api.strategy-presets.activate.ts
import { db } from "db";
import { strategyPresets, activeStrategy } from "db/schema";
import { eq, isNull } from "drizzle-orm";
import { createClient } from "redis";
import type { Route } from "./+types/api.strategy-presets.activate";

export async function action({ request }: Route.ActionArgs) {
  const { presetId } = await request.json();

  // 验证预设存在
  const [preset] = await db
    .select()
    .from(strategyPresets)
    .where(eq(strategyPresets.id, presetId));

  if (!preset) {
    return Response.json({ error: "Preset not found" }, { status: 404 });
  }

  // 停用当前活跃预设
  await db
    .update(activeStrategy)
    .set({ deactivatedAt: new Date() })
    .where(isNull(activeStrategy.deactivatedAt));

  // 激活新预设
  await db.insert(activeStrategy).values({ presetId });

  // 更新 Redis 并通知 Scheduler
  const redis = createClient({ url: process.env.REDIS_URL || "redis://localhost:6379" });
  await redis.connect();
  await redis.set(
    "strategy:active_preset",
    JSON.stringify({ name: preset.name, config: preset.configJson })
  );
  await redis.publish(
    "strategy:preset:updated",
    JSON.stringify({ name: preset.name })
  );
  await redis.disconnect();

  return Response.json({ success: true, preset: preset.name });
}
```

**Step 3: 创建 GET /api/strategy-presets/history**

```typescript
// dashboard/app/routes/api.strategy-presets.history.ts
import { db } from "db";
import { activeStrategy, strategyPresets } from "db/schema";
import { desc, eq } from "drizzle-orm";
import type { Route } from "./+types/api.strategy-presets.history";

export async function loader(_args: Route.LoaderArgs) {
  const history = await db
    .select({
      id: activeStrategy.id,
      presetName: strategyPresets.name,
      displayName: strategyPresets.displayName,
      activatedAt: activeStrategy.activatedAt,
      deactivatedAt: activeStrategy.deactivatedAt,
    })
    .from(activeStrategy)
    .innerJoin(strategyPresets, eq(activeStrategy.presetId, strategyPresets.id))
    .orderBy(desc(activeStrategy.activatedAt))
    .limit(50);

  return Response.json(history);
}
```

**Step 4: Commit**

```bash
git add dashboard/app/routes/api.strategy-presets.ts dashboard/app/routes/api.strategy-presets.activate.ts dashboard/app/routes/api.strategy-presets.history.ts
git commit -m "feat(dashboard): add strategy preset API routes"
```

---

## Task 7: Dashboard - 策略选择页面 UI

**Files:**
- Create: `dashboard/app/routes/dashboard.strategy.tsx`
- Modify: `dashboard/app/components/layout/Sidebar.tsx` (添加导航项)

**Step 1: 创建策略页面**

创建 `dashboard/app/routes/dashboard.strategy.tsx`，包含：

1. **loader**: 调用 `/api/strategy-presets` 获取数据
2. **顶部活跃策略卡片**: 显示当前策略名称、风险等级、运行时长、关键参数
3. **策略卡片网格**: 7 张卡片，2 列布局
   - 每张卡片: 名称、描述、风险色标、关键指标、历史统计、激活按钮
4. **确认弹窗**: 使用 Radix AlertDialog，显示策略对比 + 确认/取消

关键组件结构：
- `RiskBadge` - 风险等级色标组件
- `PresetCard` - 策略模板卡片组件
- `ActivateDialog` - 确认切换弹窗

风险等级配色 (tailwind classes):
- `lowest`: `bg-green-500/20 text-green-400`
- `low`: `bg-emerald-500/20 text-emerald-400`
- `medium_low`: `bg-yellow-500/20 text-yellow-400`
- `medium`: `bg-orange-500/20 text-orange-400`
- `medium_high`: `bg-red-500/20 text-red-400`

**Step 2: 修改 Sidebar 添加导航项**

在 `dashboard/app/components/layout/Sidebar.tsx` 的 navItems 数组中添加：

```typescript
{ to: "/dashboard/strategy", icon: Layers, label: "策略" },
```

放在"回测设置"之后。导入 `Layers` from `lucide-react`。

**Step 3: 验证页面可访问**

Run: `cd /Users/gowinder/code/gowinder/trader/dashboard && npm run build`
Expected: 构建成功

**Step 4: Commit**

```bash
git add dashboard/app/routes/dashboard.strategy.tsx dashboard/app/components/layout/Sidebar.tsx
git commit -m "feat(dashboard): add strategy preset selection page"
```

---

## Task 8: 集成测试和验证

**Files:**
- 无新文件

**Step 1: 验证后端预设加载**

Run: `cd /Users/gowinder/code/gowinder/trader && python -c "
from ai_trader.strategies.presets import SYSTEM_PRESETS
for p in SYSTEM_PRESETS:
    c = p.config
    total = c.ai_weight + c.quant_weight
    print(f'{p.name}: ai={c.ai_weight} quant={c.quant_weight} total={total:.1f} strategies={c.enabled_strategies}')
    assert 0.9 <= total <= 1.1, f'Weight sum {total} out of range for {p.name}'
print('All presets valid')
"`

**Step 2: 验证 Dashboard 构建**

Run: `cd /Users/gowinder/code/gowinder/trader/dashboard && npm run build`
Expected: 构建成功无错误

**Step 3: 最终 Commit**

如有修复：
```bash
git add -A
git commit -m "fix(strategy): fix integration issues"
```

---

## 实现顺序总结

| Task | 内容 | 依赖 |
|------|------|------|
| 1 | StrategyPreset 数据模型 | 无 |
| 2 | 7 个预设模板定义 | Task 1 |
| 3 | 数据库表 (schema + migration) | 无 |
| 4 | 策略预设持久化服务 | Task 1, 2, 3 |
| 5 | Scheduler 集成 | Task 4 |
| 6 | Dashboard API 路由 | Task 3 |
| 7 | Dashboard 策略页面 UI | Task 6 |
| 8 | 集成测试验证 | Task 1-7 |

**可并行**: Task 1+2 (后端模型) 和 Task 3 (数据库) 可并行。Task 6 (API) 和 Task 5 (Scheduler) 可并行。
