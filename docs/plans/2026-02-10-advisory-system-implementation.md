# AI Advisory System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an independent AI advisory service that proactively monitors trading history, market conditions, and portfolio status, generates actionable suggestions, and delivers them via Dashboard + Telegram for user approval and execution.

**Architecture:** A new `advisory/` package under `src/ai_trader/` containing trigger management, context collection, LLM advice generation, notification dispatch, and execution engine. Dashboard gets two new pages (advisory list + settings). Telegram bot runs as a background asyncio task.

**Tech Stack:** Python (pydantic, httpx, redis.asyncio, asyncpg), React 19 + Radix UI + Tailwind, Drizzle ORM, python-telegram-bot

---

## Phase 1: Data Models & Database Schema

### Task 1.1: Advisory Python Models

**Files:**
- Create: `src/ai_trader/models/advisory.py`
- Test: `tests/advisory/__init__.py`, `tests/advisory/test_models.py`

**Step 1: Create test directory and write failing test**

```bash
mkdir -p tests/advisory
touch tests/advisory/__init__.py
```

```python
# tests/advisory/test_models.py
import pytest
from ai_trader.models.advisory import (
    AdvisoryResult,
    Suggestion,
    SuggestionType,
    SuggestionStatus,
    AdvisoryStatus,
    Urgency,
)


def test_suggestion_model():
    s = Suggestion(
        type=SuggestionType.PARAM_ADJUST,
        target="global",
        action="reduce_leverage",
        detail={"leverage_max": 5},
        reasoning="市场波动加剧，建议降低最大杠杆",
        risk_note="可能错过高杠杆带来的收益",
    )
    assert s.type == SuggestionType.PARAM_ADJUST
    assert s.status == SuggestionStatus.PENDING


def test_advisory_result_model():
    s = Suggestion(
        type=SuggestionType.POSITION_ACTION,
        target="BTC/USDT:USDT",
        action="close_position",
        detail={"reason": "止损"},
        reasoning="浮亏超过阈值",
        risk_note="可能错过反弹",
    )
    result = AdvisoryResult(
        urgency=Urgency.HIGH,
        suggestions=[s],
        market_summary="BTC 短时间内大幅下跌",
    )
    assert result.urgency == Urgency.HIGH
    assert len(result.suggestions) == 1


def test_suggestion_status_flow():
    s = Suggestion(
        type=SuggestionType.SYMBOL_CHANGE,
        target="ETH/USDT:USDT",
        action="add_symbol",
        detail={},
        reasoning="ETH 趋势明确",
        risk_note="增加持仓风险",
    )
    assert s.status == SuggestionStatus.PENDING
    s.status = SuggestionStatus.ACCEPTED
    assert s.status == SuggestionStatus.ACCEPTED
```

**Step 2: Run test to verify it fails**

```bash
cd /Users/gowinder/code/gowinder/trader && python -m pytest tests/advisory/test_models.py -v
```
Expected: FAIL (ImportError)

**Step 3: Implement models**

```python
# src/ai_trader/models/advisory.py
"""AI Advisory 模型"""

from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class Urgency(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SuggestionType(str, Enum):
    PARAM_ADJUST = "param_adjust"
    POSITION_ACTION = "position_action"
    SYMBOL_CHANGE = "symbol_change"


class SuggestionStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CONFIRMED = "confirmed"
    EXECUTED = "executed"
    FAILED = "failed"


class AdvisoryStatus(str, Enum):
    PENDING = "pending"
    RESOLVED = "resolved"


class TriggerType(str, Enum):
    SCHEDULED = "scheduled"
    PRICE_VOLATILITY = "price_volatility"
    CONSECUTIVE_LOSS = "consecutive_loss"
    UNREALIZED_PNL = "unrealized_pnl"
    SENTIMENT_SHIFT = "sentiment_shift"


class Suggestion(BaseModel):
    """单条建议"""
    type: SuggestionType
    target: str  # symbol or "global"
    action: str
    detail: Dict[str, Any] = Field(default_factory=dict)
    reasoning: str
    risk_note: str
    status: SuggestionStatus = SuggestionStatus.PENDING


class AdvisoryResult(BaseModel):
    """Advisory LLM 输出结果"""
    urgency: Urgency
    suggestions: List[Suggestion]
    market_summary: str
```

**Step 4: Run test to verify it passes**

```bash
cd /Users/gowinder/code/gowinder/trader && python -m pytest tests/advisory/test_models.py -v
```
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add src/ai_trader/models/advisory.py tests/advisory/
git commit -m "feat(advisory): add advisory data models"
```

---

### Task 1.2: Dashboard Database Schema

**Files:**
- Modify: `dashboard/db/schema.ts` (append after line 445)

**Step 1: Add advisory tables to Drizzle schema**

Append to `dashboard/db/schema.ts`:

```typescript
// ==================== AI Advisory ====================

export const advisories = pgTable(
  "advisories",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),

    triggerType: varchar("trigger_type", { length: 30 }).notNull(),
    triggerDetail: jsonb("trigger_detail"),
    urgency: varchar("urgency", { length: 10 }).notNull(),
    marketSummary: text("market_summary"),
    status: varchar("status", { length: 20 }).notNull().default("pending"),

    llmProvider: varchar("llm_provider", { length: 30 }),
    llmModel: varchar("llm_model", { length: 100 }),
    tokensUsed: integer("tokens_used"),

    resolvedAt: timestamp("resolved_at", { withTimezone: true }),
  },
  (table) => ({
    timeIdx: index("idx_advisories_time").on(table.createdAt),
    statusIdx: index("idx_advisories_status").on(table.status),
  })
);

export const advisorySuggestions = pgTable(
  "advisory_suggestions",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    advisoryId: uuid("advisory_id")
      .notNull()
      .references(() => advisories.id, { onDelete: "cascade" }),

    type: varchar("type", { length: 20 }).notNull(),
    target: varchar("target", { length: 30 }).notNull(),
    action: varchar("action", { length: 50 }).notNull(),
    detail: jsonb("detail"),
    reasoning: text("reasoning"),
    riskNote: text("risk_note"),

    status: varchar("status", { length: 20 }).notNull().default("pending"),
    executionResult: jsonb("execution_result"),
    rejectionReason: text("rejection_reason"),

    updatedAt: timestamp("updated_at", { withTimezone: true }),
  },
  (table) => ({
    advisoryIdx: index("idx_advisory_suggestions_advisory").on(table.advisoryId),
    statusIdx: index("idx_advisory_suggestions_status").on(table.status),
  })
);

export const advisoriesRelations = relations(advisories, ({ many }) => ({
  suggestions: many(advisorySuggestions),
}));

export const advisorySuggestionsRelations = relations(advisorySuggestions, ({ one }) => ({
  advisory: one(advisories, {
    fields: [advisorySuggestions.advisoryId],
    references: [advisories.id],
  }),
}));
```

**Step 2: Generate and apply migration**

```bash
cd /Users/gowinder/code/gowinder/trader/dashboard && npx drizzle-kit generate
cd /Users/gowinder/code/gowinder/trader/dashboard && npx drizzle-kit push
```

**Step 3: Commit**

```bash
git add dashboard/db/schema.ts dashboard/drizzle/
git commit -m "feat(advisory): add advisories and advisory_suggestions tables"
```

---

### Task 1.3: Advisory Persistence Service (Python)

**Files:**
- Create: `src/ai_trader/advisory/__init__.py`
- Create: `src/ai_trader/advisory/persistence.py`
- Test: `tests/advisory/test_persistence.py`

**Step 1: Write failing test**

```python
# tests/advisory/test_persistence.py
import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from ai_trader.advisory.persistence import AdvisoryPersistenceService
from ai_trader.models.advisory import (
    AdvisoryResult, Suggestion, SuggestionType, Urgency, TriggerType,
)


@pytest.fixture
def mock_db():
    db = AsyncMock()
    mock_conn = AsyncMock()
    mock_conn.fetchval = AsyncMock(return_value=uuid4())
    mock_conn.execute = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=[])
    db.transaction.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    db.transaction.return_value.__aexit__ = AsyncMock(return_value=False)
    db.pool = AsyncMock()
    db.pool.fetchrow = AsyncMock(return_value=None)
    db.pool.fetch = AsyncMock(return_value=[])
    return db


@pytest.mark.asyncio
async def test_save_advisory(mock_db):
    service = AdvisoryPersistenceService(mock_db)
    result = AdvisoryResult(
        urgency=Urgency.HIGH,
        suggestions=[
            Suggestion(
                type=SuggestionType.PARAM_ADJUST,
                target="global",
                action="reduce_leverage",
                detail={"leverage_max": 5},
                reasoning="降低风险",
                risk_note="可能影响收益",
            )
        ],
        market_summary="市场波动加剧",
    )
    advisory_id = await service.save_advisory(
        result=result,
        trigger_type=TriggerType.PRICE_VOLATILITY,
        trigger_detail={"symbol": "BTC/USDT", "change_pct": 6.5},
        llm_provider="openrouter",
        llm_model="deepseek/deepseek-chat",
        tokens_used=1500,
    )
    assert advisory_id is not None


@pytest.mark.asyncio
async def test_update_suggestion_status(mock_db):
    service = AdvisoryPersistenceService(mock_db)
    mock_db.pool.execute = AsyncMock()
    suggestion_id = uuid4()
    await service.update_suggestion_status(suggestion_id, "accepted")
    mock_db.pool.execute.assert_called_once()
```

**Step 2: Run test to verify it fails**

```bash
cd /Users/gowinder/code/gowinder/trader && python -m pytest tests/advisory/test_persistence.py -v
```
Expected: FAIL (ImportError)

**Step 3: Implement persistence service**

```python
# src/ai_trader/advisory/__init__.py
"""AI Advisory System"""

# src/ai_trader/advisory/persistence.py
"""Advisory 持久化服务"""

import json
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime

from ..persistence.database import DatabaseManager
from ..models.advisory import (
    AdvisoryResult, TriggerType,
)
from ..utils.logger import logger


class AdvisoryPersistenceService:
    """Advisory 数据持久化"""

    def __init__(self, db: DatabaseManager):
        self.db = db

    async def save_advisory(
        self,
        result: AdvisoryResult,
        trigger_type: TriggerType,
        trigger_detail: Dict[str, Any],
        llm_provider: str,
        llm_model: str,
        tokens_used: int,
    ) -> UUID:
        """保存 advisory 及其 suggestions"""
        async with self.db.transaction() as conn:
            advisory_id = await conn.fetchval(
                """
                INSERT INTO advisories (
                    trigger_type, trigger_detail, urgency, market_summary,
                    status, llm_provider, llm_model, tokens_used
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING id
                """,
                trigger_type.value,
                json.dumps(trigger_detail),
                result.urgency.value,
                result.market_summary,
                "pending",
                llm_provider,
                llm_model,
                tokens_used,
            )

            for s in result.suggestions:
                await conn.execute(
                    """
                    INSERT INTO advisory_suggestions (
                        advisory_id, type, target, action, detail,
                        reasoning, risk_note, status
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    """,
                    advisory_id,
                    s.type.value,
                    s.target,
                    s.action,
                    json.dumps(s.detail),
                    s.reasoning,
                    s.risk_note,
                    "pending",
                )

            return advisory_id

    async def update_suggestion_status(
        self,
        suggestion_id: UUID,
        status: str,
        execution_result: Optional[Dict] = None,
        rejection_reason: Optional[str] = None,
    ):
        """更新建议状态"""
        await self.db.pool.execute(
            """
            UPDATE advisory_suggestions
            SET status = $1, execution_result = $2, rejection_reason = $3,
                updated_at = NOW()
            WHERE id = $4
            """,
            status,
            json.dumps(execution_result) if execution_result else None,
            rejection_reason,
            suggestion_id,
        )

    async def get_pending_advisories(self, limit: int = 50) -> List[Dict]:
        """获取待处理的 advisories"""
        rows = await self.db.pool.fetch(
            """
            SELECT a.*, json_agg(
                json_build_object(
                    'id', s.id, 'type', s.type, 'target', s.target,
                    'action', s.action, 'detail', s.detail,
                    'reasoning', s.reasoning, 'risk_note', s.risk_note,
                    'status', s.status
                )
            ) as suggestions
            FROM advisories a
            LEFT JOIN advisory_suggestions s ON s.advisory_id = a.id
            WHERE a.status = 'pending'
            GROUP BY a.id
            ORDER BY a.created_at DESC
            LIMIT $1
            """,
            limit,
        )
        return [dict(r) for r in rows]

    async def resolve_advisory(self, advisory_id: UUID):
        """标记 advisory 为已处理"""
        await self.db.pool.execute(
            """
            UPDATE advisories SET status = 'resolved', resolved_at = NOW()
            WHERE id = $1
            """,
            advisory_id,
        )
```

**Step 4: Run test to verify it passes**

```bash
cd /Users/gowinder/code/gowinder/trader && python -m pytest tests/advisory/test_persistence.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add src/ai_trader/advisory/ tests/advisory/test_persistence.py
git commit -m "feat(advisory): add advisory persistence service"
```

---

## Phase 2: Configuration & Advisory LLM Client

### Task 2.1: Add Advisory Config Fields

**Files:**
- Modify: `src/ai_trader/config.py` (add fields after line 188)
- Modify: `tests/test_config.py` (add test)

**Step 1: Write failing test**

Add to `tests/test_config.py`:

```python
def test_advisory_config_defaults():
    """Test advisory config default values"""
    from ai_trader.config import TradingConfig
    cfg = TradingConfig()
    assert cfg.advisory_enabled is False
    assert cfg.advisory_interval_minutes == 60
    assert cfg.advisory_llm_provider == "openrouter"
    assert cfg.advisory_llm_model == "deepseek/deepseek-chat"
    assert cfg.advisory_llm_timeout == 120.0
    assert cfg.telegram_bot_token == ""
    assert cfg.telegram_chat_id == ""
```

**Step 2: Run test to verify it fails**

```bash
cd /Users/gowinder/code/gowinder/trader && python -m pytest tests/test_config.py::test_advisory_config_defaults -v
```
Expected: FAIL (AttributeError)

**Step 3: Add config fields to `config.py`**

Add after the `redis_url` field (around line 188):

```python
    # ============= AI Advisory 配置 =============
    advisory_enabled: bool = Field(
        default=False, validation_alias="ADVISORY_ENABLED",
        description="启用 AI 顾问系统"
    )
    advisory_interval_minutes: int = Field(
        default=60, validation_alias="ADVISORY_INTERVAL_MINUTES",
        description="定时检查间隔（分钟）"
    )

    # Advisory LLM (独立配置)
    advisory_llm_provider: str = Field(
        default="openrouter", validation_alias="ADVISORY_LLM_PROVIDER"
    )
    advisory_llm_api_key: str = Field(
        default="", validation_alias="ADVISORY_LLM_API_KEY"
    )
    advisory_llm_model: str = Field(
        default="deepseek/deepseek-chat", validation_alias="ADVISORY_LLM_MODEL"
    )
    advisory_llm_base_url: Optional[str] = Field(
        default=None, validation_alias="ADVISORY_LLM_BASE_URL"
    )
    advisory_llm_timeout: float = Field(
        default=120.0, validation_alias="ADVISORY_LLM_TIMEOUT"
    )

    # Telegram 通知
    telegram_bot_token: str = Field(
        default="", validation_alias="TELEGRAM_BOT_TOKEN"
    )
    telegram_chat_id: str = Field(
        default="", validation_alias="TELEGRAM_CHAT_ID"
    )
```

**Step 4: Run test to verify it passes**

```bash
cd /Users/gowinder/code/gowinder/trader && python -m pytest tests/test_config.py::test_advisory_config_defaults -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add src/ai_trader/config.py tests/test_config.py
git commit -m "feat(advisory): add advisory and telegram config fields"
```

---

### Task 2.2: Advisory LLM Client

**Files:**
- Create: `src/ai_trader/advisory/llm_client.py`
- Test: `tests/advisory/test_llm_client.py`

**Step 1: Write failing test**

```python
# tests/advisory/test_llm_client.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_advisory_llm_client_chat():
    """Test advisory LLM client makes correct API call"""
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '{"urgency":"high","suggestions":[],"market_summary":"test"}'}}]
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        from ai_trader.advisory.llm_client import AdvisoryLLMClient

        client = AdvisoryLLMClient(
            provider="openrouter",
            api_key="test_key",
            model="deepseek/deepseek-chat",
            base_url="https://openrouter.ai/api/v1",
        )
        result = await client.chat(
            messages=[{"role": "user", "content": "test"}],
            schema={"type": "object"},
        )
        assert result["urgency"] == "high"
        await client.close()
```

**Step 2: Run test to verify it fails**

```bash
cd /Users/gowinder/code/gowinder/trader && python -m pytest tests/advisory/test_llm_client.py -v
```
Expected: FAIL (ImportError)

**Step 3: Implement advisory LLM client**

```python
# src/ai_trader/advisory/llm_client.py
"""Advisory 专用 LLM 客户端"""

from typing import Optional, Dict, List, Any
from ..ai.providers.base import HTTPBasedProvider
from ..config import config
from ..utils.logger import logger


class AdvisoryLLMClient:
    """Advisory 独立 LLM 客户端 - 不使用 LLMManager 调度"""

    def __init__(
        self,
        provider: str = "",
        api_key: str = "",
        model: str = "",
        base_url: Optional[str] = None,
        timeout: float = 120.0,
    ):
        self._provider_name = provider or config.advisory_llm_provider
        self._api_key = api_key or config.advisory_llm_api_key or config.llm_api_key
        self._model = model or config.advisory_llm_model
        self._base_url = base_url or config.advisory_llm_base_url or "https://openrouter.ai/api/v1"
        self._timeout = timeout or config.advisory_llm_timeout

        # 使用 HTTPBasedProvider 复用现有的 HTTP 请求逻辑
        self._provider = HTTPBasedProvider(
            api_key=self._api_key,
            model=self._model,
            base_url=self._base_url,
            timeout=self._timeout,
        )

    async def chat(
        self,
        messages: List[Dict[str, str]],
        schema: Optional[Dict[str, Any]] = None,
        max_tokens: int = 4000,
        temperature: float = 0.3,
    ) -> Dict[str, Any]:
        """发送请求到 advisory LLM"""
        return await self._provider.chat(
            messages=messages,
            schema=schema,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    async def close(self):
        await self._provider.close()

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def model_name(self) -> str:
        return self._model
```

**Step 4: Run test to verify it passes**

```bash
cd /Users/gowinder/code/gowinder/trader && python -m pytest tests/advisory/test_llm_client.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add src/ai_trader/advisory/llm_client.py tests/advisory/test_llm_client.py
git commit -m "feat(advisory): add independent advisory LLM client"
```

---

## Phase 3: Trigger System

### Task 3.1: Trigger Detectors

**Files:**
- Create: `src/ai_trader/advisory/triggers.py`
- Test: `tests/advisory/test_triggers.py`

**Step 1: Write failing test**

```python
# tests/advisory/test_triggers.py
import pytest
from unittest.mock import AsyncMock
from datetime import datetime, timedelta

from ai_trader.advisory.triggers import (
    TriggerManager,
    PriceVolatilityTrigger,
    ConsecutiveLossTrigger,
    UnrealizedPnLTrigger,
    SentimentShiftTrigger,
    TriggerConfig,
)


def test_trigger_config_defaults():
    cfg = TriggerConfig()
    assert cfg.price_volatility_enabled is True
    assert cfg.price_volatility_threshold == 5.0
    assert cfg.consecutive_loss_threshold == 3
    assert cfg.unrealized_pnl_threshold == -5.0
    assert cfg.cooldown_minutes == 30


@pytest.mark.asyncio
async def test_price_volatility_trigger_fires():
    trigger = PriceVolatilityTrigger(threshold=5.0, cooldown_minutes=30)
    # Simulate 6% drop
    result = trigger.check(current_price=94.0, previous_price=100.0, interval_minutes=5)
    assert result is not None
    assert result["change_pct"] == pytest.approx(-6.0, abs=0.1)


@pytest.mark.asyncio
async def test_price_volatility_trigger_no_fire():
    trigger = PriceVolatilityTrigger(threshold=5.0, cooldown_minutes=30)
    # Only 2% drop - should not fire
    result = trigger.check(current_price=98.0, previous_price=100.0, interval_minutes=5)
    assert result is None


@pytest.mark.asyncio
async def test_consecutive_loss_trigger():
    trigger = ConsecutiveLossTrigger(threshold=3, cooldown_minutes=30)
    result = trigger.check(consecutive_losses=4)
    assert result is not None
    assert result["consecutive_losses"] == 4


@pytest.mark.asyncio
async def test_unrealized_pnl_trigger():
    trigger = UnrealizedPnLTrigger(threshold=-5.0, cooldown_minutes=30)
    result = trigger.check(unrealized_pnl_pct=-7.0)
    assert result is not None


@pytest.mark.asyncio
async def test_cooldown_prevents_duplicate():
    trigger = PriceVolatilityTrigger(threshold=5.0, cooldown_minutes=30)
    result1 = trigger.check(current_price=94.0, previous_price=100.0, interval_minutes=5)
    assert result1 is not None
    # Second call within cooldown should not fire
    result2 = trigger.check(current_price=93.0, previous_price=100.0, interval_minutes=5)
    assert result2 is None


@pytest.mark.asyncio
async def test_trigger_manager_scheduled():
    mgr = TriggerManager(TriggerConfig(interval_minutes=60))
    assert mgr.should_run_scheduled() is True
    mgr.mark_scheduled_run()
    assert mgr.should_run_scheduled() is False
```

**Step 2: Run test to verify it fails**

```bash
cd /Users/gowinder/code/gowinder/trader && python -m pytest tests/advisory/test_triggers.py -v
```
Expected: FAIL (ImportError)

**Step 3: Implement triggers**

```python
# src/ai_trader/advisory/triggers.py
"""Advisory 触发器系统"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from ..utils.logger import logger


@dataclass
class TriggerConfig:
    """触发器配置 - 可从 Redis 动态加载"""
    interval_minutes: int = 60
    price_volatility_enabled: bool = True
    price_volatility_threshold: float = 5.0  # %
    consecutive_loss_enabled: bool = True
    consecutive_loss_threshold: int = 3
    unrealized_pnl_enabled: bool = True
    unrealized_pnl_threshold: float = -5.0  # %
    sentiment_shift_enabled: bool = True
    cooldown_minutes: int = 30


class BaseTrigger:
    """触发器基类"""

    def __init__(self, cooldown_minutes: int = 30):
        self.cooldown_minutes = cooldown_minutes
        self._last_fired: Optional[datetime] = None

    def _is_cooldown(self) -> bool:
        if self._last_fired is None:
            return False
        return datetime.now() - self._last_fired < timedelta(minutes=self.cooldown_minutes)

    def _mark_fired(self):
        self._last_fired = datetime.now()


class PriceVolatilityTrigger(BaseTrigger):
    """价格波动触发器"""

    def __init__(self, threshold: float = 5.0, cooldown_minutes: int = 30):
        super().__init__(cooldown_minutes)
        self.threshold = threshold

    def check(
        self, current_price: float, previous_price: float, interval_minutes: int = 5
    ) -> Optional[Dict[str, Any]]:
        if self._is_cooldown():
            return None
        if previous_price == 0:
            return None
        change_pct = ((current_price - previous_price) / previous_price) * 100
        if abs(change_pct) >= self.threshold:
            self._mark_fired()
            return {
                "change_pct": round(change_pct, 2),
                "current_price": current_price,
                "previous_price": previous_price,
                "interval_minutes": interval_minutes,
            }
        return None


class ConsecutiveLossTrigger(BaseTrigger):
    """连续亏损触发器"""

    def __init__(self, threshold: int = 3, cooldown_minutes: int = 30):
        super().__init__(cooldown_minutes)
        self.threshold = threshold

    def check(self, consecutive_losses: int) -> Optional[Dict[str, Any]]:
        if self._is_cooldown():
            return None
        if consecutive_losses >= self.threshold:
            self._mark_fired()
            return {"consecutive_losses": consecutive_losses}
        return None


class UnrealizedPnLTrigger(BaseTrigger):
    """浮亏触发器"""

    def __init__(self, threshold: float = -5.0, cooldown_minutes: int = 30):
        super().__init__(cooldown_minutes)
        self.threshold = threshold

    def check(self, unrealized_pnl_pct: float) -> Optional[Dict[str, Any]]:
        if self._is_cooldown():
            return None
        if unrealized_pnl_pct <= self.threshold:
            self._mark_fired()
            return {"unrealized_pnl_pct": round(unrealized_pnl_pct, 2)}
        return None


class SentimentShiftTrigger(BaseTrigger):
    """情绪突变触发器"""

    def __init__(self, cooldown_minutes: int = 30):
        super().__init__(cooldown_minutes)

    def check(
        self, extreme_fear: bool = False, extreme_greed: bool = False
    ) -> Optional[Dict[str, Any]]:
        if self._is_cooldown():
            return None
        if extreme_fear or extreme_greed:
            self._mark_fired()
            return {
                "extreme_fear": extreme_fear,
                "extreme_greed": extreme_greed,
            }
        return None


class TriggerManager:
    """触发器管理器"""

    def __init__(self, config: Optional[TriggerConfig] = None):
        self.config = config or TriggerConfig()
        self._last_scheduled: Optional[datetime] = None

        self.price_volatility = PriceVolatilityTrigger(
            threshold=self.config.price_volatility_threshold,
            cooldown_minutes=self.config.cooldown_minutes,
        )
        self.consecutive_loss = ConsecutiveLossTrigger(
            threshold=self.config.consecutive_loss_threshold,
            cooldown_minutes=self.config.cooldown_minutes,
        )
        self.unrealized_pnl = UnrealizedPnLTrigger(
            threshold=self.config.unrealized_pnl_threshold,
            cooldown_minutes=self.config.cooldown_minutes,
        )
        self.sentiment_shift = SentimentShiftTrigger(
            cooldown_minutes=self.config.cooldown_minutes,
        )

    def should_run_scheduled(self) -> bool:
        if self._last_scheduled is None:
            return True
        return datetime.now() - self._last_scheduled >= timedelta(
            minutes=self.config.interval_minutes
        )

    def mark_scheduled_run(self):
        self._last_scheduled = datetime.now()

    def update_config(self, new_config: TriggerConfig):
        """热更新触发器配置"""
        self.config = new_config
        self.price_volatility.threshold = new_config.price_volatility_threshold
        self.price_volatility.cooldown_minutes = new_config.cooldown_minutes
        self.consecutive_loss.threshold = new_config.consecutive_loss_threshold
        self.consecutive_loss.cooldown_minutes = new_config.cooldown_minutes
        self.unrealized_pnl.threshold = new_config.unrealized_pnl_threshold
        self.unrealized_pnl.cooldown_minutes = new_config.cooldown_minutes
        self.sentiment_shift.cooldown_minutes = new_config.cooldown_minutes
```

**Step 4: Run test to verify it passes**

```bash
cd /Users/gowinder/code/gowinder/trader && python -m pytest tests/advisory/test_triggers.py -v
```
Expected: PASS (7 tests)

**Step 5: Commit**

```bash
git add src/ai_trader/advisory/triggers.py tests/advisory/test_triggers.py
git commit -m "feat(advisory): add trigger system with cooldown mechanism"
```

---

## Phase 4: Advisory Engine (Core)

### Task 4.1: Prompt & Context Builder

**Files:**
- Create: `src/ai_trader/advisory/prompts.py`
- Create: `src/ai_trader/advisory/context.py`
- Test: `tests/advisory/test_context.py`

**Step 1: Write failing test**

```python
# tests/advisory/test_context.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from ai_trader.advisory.context import AdvisoryContextBuilder


@pytest.mark.asyncio
async def test_context_builder_builds_prompt():
    mock_db = AsyncMock()
    mock_db.pool = AsyncMock()
    # Mock recent trades
    mock_db.pool.fetch = AsyncMock(return_value=[
        {"symbol": "BTC/USDT", "action": "open_long", "realized_pnl": -50.0,
         "pnl_percent": -2.5, "entry_price": 50000.0, "exit_price": 48750.0},
    ])

    builder = AdvisoryContextBuilder(db=mock_db)
    context = await builder.build(
        symbols=["BTC/USDT:USDT"],
        positions=[],
        market_data={"BTC/USDT:USDT": {"current_price": 48000.0, "change_24h": -5.2}},
        sentiment=None,
        trigger_reason="scheduled",
        current_config={"stop_loss_percent": 5.0, "leverage_max": 10},
    )

    assert "BTC/USDT" in context
    assert "scheduled" in context
    assert "-50.0" in context or "-50" in context
```

**Step 2: Run test to verify it fails**

```bash
cd /Users/gowinder/code/gowinder/trader && python -m pytest tests/advisory/test_context.py -v
```
Expected: FAIL (ImportError)

**Step 3: Implement prompts and context builder**

```python
# src/ai_trader/advisory/prompts.py
"""Advisory System Prompts"""

ADVISORY_SYSTEM = """You are a senior AI trading advisor conducting a comprehensive portfolio review.
Your role is to analyze the current trading state and provide actionable suggestions.

## Your Capabilities
1. **Parameter Adjustment**: Suggest changes to stop-loss, take-profit, leverage, strategy weights
2. **Position Actions**: Recommend closing, reducing, or adding to positions
3. **Symbol Management**: Suggest adding or removing trading pairs

## Output Rules
- Output valid JSON matching the schema exactly
- reasoning: Must be in Chinese (中文)
- risk_note: Must be in Chinese (中文)
- Be specific with numbers and targets
- Only suggest changes when there's clear evidence
- If everything looks fine, return empty suggestions with appropriate market_summary

## Urgency Levels
- **high**: Immediate action recommended (large losses, extreme volatility, critical risk)
- **medium**: Action recommended within next few hours
- **low**: Informational, can be reviewed at convenience"""

ADVISORY_USER = """## 触发原因
{trigger_reason}

## 最近交易记录 (最近 {trade_count} 笔)
{recent_trades}

## 当前持仓状态
{positions}

## 实时行情数据
{market_data}

## 情绪分析
{sentiment}

## 当前策略配置
{current_config}

## 账户概况
{account_summary}

请综合分析以上信息，给出交易建议。如果一切正常无需调整，suggestions 可以为空。"""

ADVISORY_SCHEMA = {
    "type": "object",
    "properties": {
        "urgency": {
            "type": "string",
            "enum": ["high", "medium", "low"],
        },
        "market_summary": {
            "type": "string",
            "description": "当前市场概况 (中文, 100字以内)",
        },
        "suggestions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["param_adjust", "position_action", "symbol_change"],
                    },
                    "target": {
                        "type": "string",
                        "description": "交易对或 'global'",
                    },
                    "action": {
                        "type": "string",
                        "description": "具体动作，如 reduce_leverage, close_position, add_symbol",
                    },
                    "detail": {
                        "type": "object",
                        "description": "具体参数",
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "中文理由",
                    },
                    "risk_note": {
                        "type": "string",
                        "description": "中文风险提示",
                    },
                },
                "required": ["type", "target", "action", "detail", "reasoning", "risk_note"],
            },
        },
    },
    "required": ["urgency", "market_summary", "suggestions"],
    "additionalProperties": False,
}
```

```python
# src/ai_trader/advisory/context.py
"""Advisory 上下文构建"""

from typing import Optional, List, Dict, Any

from ..persistence.database import DatabaseManager
from ..utils.logger import logger


class AdvisoryContextBuilder:
    """构建 Advisory LLM 的上下文"""

    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db

    async def build(
        self,
        symbols: List[str],
        positions: List[Dict],
        market_data: Dict[str, Dict],
        sentiment: Optional[Dict],
        trigger_reason: str,
        current_config: Dict[str, Any],
        account_summary: Optional[Dict] = None,
    ) -> str:
        """构建完整的上下文文本"""
        # 获取最近交易
        recent_trades = await self._get_recent_trades(limit=20)

        # 格式化各部分
        trades_text = self._format_trades(recent_trades)
        positions_text = self._format_positions(positions)
        market_text = self._format_market_data(market_data)
        sentiment_text = self._format_sentiment(sentiment)
        config_text = self._format_config(current_config)
        account_text = self._format_account(account_summary)

        from .prompts import ADVISORY_USER
        return ADVISORY_USER.format(
            trigger_reason=trigger_reason,
            trade_count=len(recent_trades),
            recent_trades=trades_text,
            positions=positions_text,
            market_data=market_text,
            sentiment=sentiment_text,
            current_config=config_text,
            account_summary=account_text,
        )

    async def _get_recent_trades(self, limit: int = 20) -> List[Dict]:
        if not self.db:
            return []
        try:
            rows = await self.db.pool.fetch(
                """
                SELECT ph.symbol, d.action,
                       ph.realized_pnl, ph.pnl_percent,
                       ph.entry_price, ph.exit_price,
                       ph.entry_time, ph.exit_time, ph.leverage
                FROM position_history ph
                LEFT JOIN decisions d ON d.id = ph.entry_decision_id
                WHERE ph.status = 'closed'
                ORDER BY ph.exit_time DESC
                LIMIT $1
                """,
                limit,
            )
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"Failed to get recent trades: {e}")
            return []

    def _format_trades(self, trades: List[Dict]) -> str:
        if not trades:
            return "无近期交易记录"
        lines = []
        total_pnl = 0
        wins = 0
        for t in trades:
            pnl = float(t.get("realized_pnl", 0) or 0)
            total_pnl += pnl
            if pnl > 0:
                wins += 1
            lines.append(
                f"- {t.get('symbol', '?')}: {t.get('action', '?')}, "
                f"PnL: {pnl:+.2f} USDT ({float(t.get('pnl_percent', 0) or 0):+.2f}%), "
                f"杠杆: {t.get('leverage', '?')}x"
            )
        win_rate = (wins / len(trades) * 100) if trades else 0
        summary = f"总计 {len(trades)} 笔, 总PnL: {total_pnl:+.2f} USDT, 胜率: {win_rate:.0f}%\n"
        return summary + "\n".join(lines)

    def _format_positions(self, positions: List[Dict]) -> str:
        if not positions:
            return "当前无持仓"
        lines = []
        for p in positions:
            lines.append(
                f"- {p.get('symbol', '?')}: {p.get('side', '?')}, "
                f"入场价: {p.get('entry_price', '?')}, "
                f"浮动PnL: {p.get('unrealized_pnl', '?')} USDT, "
                f"ROI: {p.get('roi', '?')}%, "
                f"杠杆: {p.get('leverage', '?')}x"
            )
        return "\n".join(lines)

    def _format_market_data(self, market_data: Dict[str, Dict]) -> str:
        if not market_data:
            return "无行情数据"
        lines = []
        for symbol, data in market_data.items():
            lines.append(
                f"- {symbol}: 价格 {data.get('current_price', '?')} USDT, "
                f"24h变化: {data.get('change_24h', '?')}%"
            )
        return "\n".join(lines)

    def _format_sentiment(self, sentiment: Optional[Dict]) -> str:
        if not sentiment:
            return "情绪分析未启用"
        return (
            f"情绪评分: {sentiment.get('score', '?')}, "
            f"置信度: {sentiment.get('confidence', '?')}, "
            f"极度恐惧: {sentiment.get('extreme_fear', False)}, "
            f"极度贪婪: {sentiment.get('extreme_greed', False)}"
        )

    def _format_config(self, config: Dict[str, Any]) -> str:
        lines = [f"- {k}: {v}" for k, v in config.items()]
        return "\n".join(lines) if lines else "无配置信息"

    def _format_account(self, account: Optional[Dict]) -> str:
        if not account:
            return "无账户信息"
        return (
            f"总权益: {account.get('total_equity', '?')} USDT, "
            f"可用余额: {account.get('available_balance', '?')} USDT, "
            f"已用保证金: {account.get('margin_used', '?')} USDT"
        )
```

**Step 4: Run test to verify it passes**

```bash
cd /Users/gowinder/code/gowinder/trader && python -m pytest tests/advisory/test_context.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add src/ai_trader/advisory/prompts.py src/ai_trader/advisory/context.py tests/advisory/test_context.py
git commit -m "feat(advisory): add prompts and context builder"
```

---

### Task 4.2: Advisory Engine

**Files:**
- Create: `src/ai_trader/advisory/engine.py`
- Test: `tests/advisory/test_engine.py`

**Step 1: Write failing test**

```python
# tests/advisory/test_engine.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from ai_trader.advisory.engine import AdvisoryEngine
from ai_trader.models.advisory import TriggerType


@pytest.fixture
def mock_deps():
    llm = AsyncMock()
    llm.chat = AsyncMock(return_value={
        "urgency": "medium",
        "market_summary": "市场平稳",
        "suggestions": [
            {
                "type": "param_adjust",
                "target": "global",
                "action": "reduce_leverage",
                "detail": {"leverage_max": 5},
                "reasoning": "波动加剧，降低杠杆",
                "risk_note": "可能影响收益",
            }
        ],
    })
    llm.provider_name = "openrouter"
    llm.model_name = "deepseek/deepseek-chat"

    persistence = AsyncMock()
    persistence.save_advisory = AsyncMock(return_value=uuid4())

    context_builder = AsyncMock()
    context_builder.build = AsyncMock(return_value="test context")

    return llm, persistence, context_builder


@pytest.mark.asyncio
async def test_engine_generate_advisory(mock_deps):
    llm, persistence, context_builder = mock_deps

    engine = AdvisoryEngine(
        llm_client=llm,
        persistence=persistence,
        context_builder=context_builder,
    )

    advisory_id = await engine.generate_advisory(
        trigger_type=TriggerType.SCHEDULED,
        trigger_detail={},
        symbols=["BTC/USDT:USDT"],
        positions=[],
        market_data={},
        sentiment=None,
        current_config={},
    )

    assert advisory_id is not None
    llm.chat.assert_called_once()
    persistence.save_advisory.assert_called_once()


@pytest.mark.asyncio
async def test_engine_handles_llm_error(mock_deps):
    llm, persistence, context_builder = mock_deps
    llm.chat.side_effect = Exception("LLM timeout")

    engine = AdvisoryEngine(
        llm_client=llm,
        persistence=persistence,
        context_builder=context_builder,
    )

    advisory_id = await engine.generate_advisory(
        trigger_type=TriggerType.SCHEDULED,
        trigger_detail={},
        symbols=["BTC/USDT:USDT"],
        positions=[],
        market_data={},
        sentiment=None,
        current_config={},
    )

    assert advisory_id is None
```

**Step 2: Run test to verify it fails**

```bash
cd /Users/gowinder/code/gowinder/trader && python -m pytest tests/advisory/test_engine.py -v
```
Expected: FAIL (ImportError)

**Step 3: Implement engine**

```python
# src/ai_trader/advisory/engine.py
"""Advisory 引擎 - 核心决策生成"""

from typing import Optional, List, Dict, Any
from uuid import UUID

from .llm_client import AdvisoryLLMClient
from .persistence import AdvisoryPersistenceService
from .context import AdvisoryContextBuilder
from .prompts import ADVISORY_SYSTEM, ADVISORY_SCHEMA
from ..models.advisory import AdvisoryResult, Suggestion, TriggerType, SuggestionType, Urgency
from ..utils.logger import logger


class AdvisoryEngine:
    """Advisory 引擎"""

    def __init__(
        self,
        llm_client: AdvisoryLLMClient,
        persistence: AdvisoryPersistenceService,
        context_builder: AdvisoryContextBuilder,
    ):
        self.llm = llm_client
        self.persistence = persistence
        self.context_builder = context_builder

    async def generate_advisory(
        self,
        trigger_type: TriggerType,
        trigger_detail: Dict[str, Any],
        symbols: List[str],
        positions: List[Dict],
        market_data: Dict[str, Dict],
        sentiment: Optional[Dict],
        current_config: Dict[str, Any],
        account_summary: Optional[Dict] = None,
    ) -> Optional[UUID]:
        """生成一次 advisory"""
        try:
            # 1. 构建上下文
            trigger_reason = f"{trigger_type.value}: {trigger_detail}" if trigger_detail else trigger_type.value
            context = await self.context_builder.build(
                symbols=symbols,
                positions=positions,
                market_data=market_data,
                sentiment=sentiment,
                trigger_reason=trigger_reason,
                current_config=current_config,
                account_summary=account_summary,
            )

            # 2. 调用 LLM
            messages = [
                {"role": "system", "content": ADVISORY_SYSTEM},
                {"role": "user", "content": context},
            ]
            raw_result = await self.llm.chat(
                messages=messages,
                schema=ADVISORY_SCHEMA,
                max_tokens=4000,
                temperature=0.3,
            )

            # 3. 解析结果
            result = self._parse_result(raw_result)

            # 4. 持久化
            advisory_id = await self.persistence.save_advisory(
                result=result,
                trigger_type=trigger_type,
                trigger_detail=trigger_detail,
                llm_provider=getattr(self.llm, "provider_name", "unknown"),
                llm_model=getattr(self.llm, "model_name", "unknown"),
                tokens_used=raw_result.get("usage", {}).get("total_tokens", 0) if isinstance(raw_result, dict) else 0,
            )

            logger.info(
                f"Advisory generated: id={advisory_id}, urgency={result.urgency.value}, "
                f"suggestions={len(result.suggestions)}"
            )
            return advisory_id

        except Exception as e:
            logger.error(f"Failed to generate advisory: {e}")
            return None

    def _parse_result(self, raw: Dict[str, Any]) -> AdvisoryResult:
        """将 LLM 原始输出转为 AdvisoryResult"""
        suggestions = []
        for s in raw.get("suggestions", []):
            suggestions.append(Suggestion(
                type=SuggestionType(s["type"]),
                target=s["target"],
                action=s["action"],
                detail=s.get("detail", {}),
                reasoning=s["reasoning"],
                risk_note=s["risk_note"],
            ))

        return AdvisoryResult(
            urgency=Urgency(raw["urgency"]),
            suggestions=suggestions,
            market_summary=raw["market_summary"],
        )
```

**Step 4: Run test to verify it passes**

```bash
cd /Users/gowinder/code/gowinder/trader && python -m pytest tests/advisory/test_engine.py -v
```
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add src/ai_trader/advisory/engine.py tests/advisory/test_engine.py
git commit -m "feat(advisory): add advisory engine with LLM integration"
```

---

## Phase 5: Execution Engine

### Task 5.1: Suggestion Executors

**Files:**
- Create: `src/ai_trader/advisory/executors.py`
- Test: `tests/advisory/test_executors.py`

**Step 1: Write failing test**

```python
# tests/advisory/test_executors.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ai_trader.advisory.executors import (
    ConfigExecutor,
    TradeExecutor,
    SymbolExecutor,
    ExecutionResult,
)


@pytest.mark.asyncio
async def test_config_executor_reduce_leverage():
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value='{"enabled": true, "decisionInterval": 1}')
    mock_redis.set = AsyncMock()
    mock_redis.publish = AsyncMock()

    executor = ConfigExecutor(redis_client=mock_redis)
    result = await executor.execute(
        action="reduce_leverage",
        target="global",
        detail={"leverage_max": 5},
    )
    assert result.success is True
    assert "leverage" in result.message.lower()


@pytest.mark.asyncio
async def test_config_executor_adjust_stop_loss():
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value='{}')
    mock_redis.set = AsyncMock()
    mock_redis.publish = AsyncMock()

    executor = ConfigExecutor(redis_client=mock_redis)
    result = await executor.execute(
        action="adjust_stop_loss",
        target="global",
        detail={"stop_loss_percent": 3.0},
    )
    assert result.success is True


@pytest.mark.asyncio
async def test_trade_executor_close_position():
    mock_order_mgr = AsyncMock()
    mock_position_mgr = AsyncMock()
    mock_position = MagicMock()
    mock_position.size = 0.001
    mock_position.side = "long"
    mock_position_mgr.get_position = AsyncMock(return_value=mock_position)

    executor = TradeExecutor(
        order_manager=mock_order_mgr,
        position_manager=mock_position_mgr,
    )
    result = await executor.execute(
        action="close_position",
        target="BTC/USDT:USDT",
        detail={},
    )
    assert result.success is True


@pytest.mark.asyncio
async def test_trade_executor_no_position():
    mock_order_mgr = AsyncMock()
    mock_position_mgr = AsyncMock()
    mock_position_mgr.get_position = AsyncMock(return_value=None)

    executor = TradeExecutor(
        order_manager=mock_order_mgr,
        position_manager=mock_position_mgr,
    )
    result = await executor.execute(
        action="close_position",
        target="BTC/USDT:USDT",
        detail={},
    )
    assert result.success is False
    assert "不存在" in result.message or "no position" in result.message.lower()
```

**Step 2: Run test to verify it fails**

```bash
cd /Users/gowinder/code/gowinder/trader && python -m pytest tests/advisory/test_executors.py -v
```
Expected: FAIL (ImportError)

**Step 3: Implement executors**

```python
# src/ai_trader/advisory/executors.py
"""Advisory 建议执行器"""

import json
from dataclasses import dataclass
from typing import Optional, Dict, Any

from ..utils.logger import logger


@dataclass
class ExecutionResult:
    success: bool
    message: str
    detail: Optional[Dict[str, Any]] = None


class ConfigExecutor:
    """参数调整执行器"""

    def __init__(self, redis_client):
        self._redis = redis_client

    async def execute(self, action: str, target: str, detail: Dict[str, Any]) -> ExecutionResult:
        try:
            if action == "reduce_leverage":
                return await self._adjust_leverage(detail)
            elif action == "increase_leverage":
                return await self._adjust_leverage(detail)
            elif action == "adjust_stop_loss":
                return await self._adjust_param("stop_loss_percent", detail.get("stop_loss_percent"))
            elif action == "adjust_take_profit":
                return await self._adjust_param("take_profit_percent", detail.get("take_profit_percent"))
            elif action == "adjust_weights":
                return await self._adjust_weights(detail)
            else:
                return ExecutionResult(success=False, message=f"未知的配置操作: {action}")
        except Exception as e:
            logger.error(f"Config execution failed: {e}")
            return ExecutionResult(success=False, message=str(e))

    async def _adjust_leverage(self, detail: Dict) -> ExecutionResult:
        new_max = detail.get("leverage_max")
        if new_max is None:
            return ExecutionResult(success=False, message="缺少 leverage_max 参数")

        # 通过 Redis 发布配置更新
        config_data = await self._redis.get("trading:config")
        config = json.loads(config_data) if config_data else {}
        config["leverage_max"] = new_max
        await self._redis.set("trading:config", json.dumps(config))
        await self._redis.publish("trading:config:updated", json.dumps(config))

        return ExecutionResult(
            success=True,
            message=f"Leverage max 已调整为 {new_max}x",
            detail={"leverage_max": new_max},
        )

    async def _adjust_param(self, param_name: str, value: Any) -> ExecutionResult:
        if value is None:
            return ExecutionResult(success=False, message=f"缺少 {param_name} 参数")

        config_data = await self._redis.get("trading:config")
        config = json.loads(config_data) if config_data else {}
        config[param_name] = value
        await self._redis.set("trading:config", json.dumps(config))
        await self._redis.publish("trading:config:updated", json.dumps(config))

        return ExecutionResult(
            success=True,
            message=f"{param_name} 已调整为 {value}",
            detail={param_name: value},
        )

    async def _adjust_weights(self, detail: Dict) -> ExecutionResult:
        config_data = await self._redis.get("trading:config")
        config = json.loads(config_data) if config_data else {}
        updated = {}
        for key in ["quant_weight", "ai_weight", "sentiment_weight"]:
            if key in detail:
                config[key] = detail[key]
                updated[key] = detail[key]
        await self._redis.set("trading:config", json.dumps(config))
        await self._redis.publish("trading:config:updated", json.dumps(config))
        return ExecutionResult(success=True, message=f"权重已调整: {updated}", detail=updated)


class TradeExecutor:
    """仓位操作执行器"""

    def __init__(self, order_manager, position_manager):
        self._order_mgr = order_manager
        self._position_mgr = position_manager

    async def execute(self, action: str, target: str, detail: Dict[str, Any]) -> ExecutionResult:
        try:
            if action == "close_position":
                return await self._close_position(target)
            elif action == "reduce_position":
                return await self._reduce_position(target, detail)
            else:
                return ExecutionResult(success=False, message=f"未知的仓位操作: {action}")
        except Exception as e:
            logger.error(f"Trade execution failed: {e}")
            return ExecutionResult(success=False, message=str(e))

    async def _close_position(self, symbol: str) -> ExecutionResult:
        position = await self._position_mgr.get_position(symbol)
        if not position:
            return ExecutionResult(success=False, message=f"仓位不存在: {symbol}")

        from ..models.decision import TradingDecision
        close_action = "close_long" if position.side == "long" else "close_short"
        decision = TradingDecision(
            action=close_action,
            confidence=100,
            leverage=position.leverage or 1,
            position_size_percent=100,
            reasoning="Advisory system recommended close",
            reasoning_zh="AI顾问系统建议平仓",
        )
        await self._order_mgr.execute_order(decision, symbol, position.size)
        return ExecutionResult(
            success=True,
            message=f"已平仓 {symbol} ({position.side}, {position.size})",
        )

    async def _reduce_position(self, symbol: str, detail: Dict) -> ExecutionResult:
        position = await self._position_mgr.get_position(symbol)
        if not position:
            return ExecutionResult(success=False, message=f"仓位不存在: {symbol}")

        reduce_pct = detail.get("reduce_percent", 50) / 100
        reduce_size = position.size * reduce_pct

        from ..models.decision import TradingDecision
        reduce_action = "reduce_long" if position.side == "long" else "reduce_short"
        decision = TradingDecision(
            action=reduce_action,
            confidence=100,
            leverage=position.leverage or 1,
            position_size_percent=reduce_pct * 100,
            reasoning="Advisory system recommended reduce",
            reasoning_zh="AI顾问系统建议减仓",
        )
        await self._order_mgr.execute_order(decision, symbol, reduce_size)
        return ExecutionResult(
            success=True,
            message=f"已减仓 {symbol} {reduce_pct*100:.0f}% ({reduce_size})",
        )


class SymbolExecutor:
    """交易对增减执行器"""

    def __init__(self, redis_client):
        self._redis = redis_client

    async def execute(self, action: str, target: str, detail: Dict[str, Any]) -> ExecutionResult:
        try:
            if action == "add_symbol":
                return await self._add_symbol(target)
            elif action == "remove_symbol":
                return await self._remove_symbol(target)
            else:
                return ExecutionResult(success=False, message=f"未知的交易对操作: {action}")
        except Exception as e:
            logger.error(f"Symbol execution failed: {e}")
            return ExecutionResult(success=False, message=str(e))

    async def _add_symbol(self, symbol: str) -> ExecutionResult:
        config_data = await self._redis.get("trading:config")
        config = json.loads(config_data) if config_data else {}
        symbols = config.get("trading_symbols", "").split(",")
        symbols = [s.strip() for s in symbols if s.strip()]
        if symbol in symbols:
            return ExecutionResult(success=False, message=f"{symbol} 已在监控列表中")
        symbols.append(symbol)
        config["trading_symbols"] = ",".join(symbols)
        await self._redis.set("trading:config", json.dumps(config))
        await self._redis.publish("trading:config:updated", json.dumps(config))
        return ExecutionResult(success=True, message=f"已添加交易对: {symbol}")

    async def _remove_symbol(self, symbol: str) -> ExecutionResult:
        config_data = await self._redis.get("trading:config")
        config = json.loads(config_data) if config_data else {}
        symbols = config.get("trading_symbols", "").split(",")
        symbols = [s.strip() for s in symbols if s.strip()]
        if symbol not in symbols:
            return ExecutionResult(success=False, message=f"{symbol} 不在监控列表中")
        symbols.remove(symbol)
        config["trading_symbols"] = ",".join(symbols)
        await self._redis.set("trading:config", json.dumps(config))
        await self._redis.publish("trading:config:updated", json.dumps(config))
        return ExecutionResult(success=True, message=f"已移除交易对: {symbol}")
```

**Step 4: Run test to verify it passes**

```bash
cd /Users/gowinder/code/gowinder/trader && python -m pytest tests/advisory/test_executors.py -v
```
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add src/ai_trader/advisory/executors.py tests/advisory/test_executors.py
git commit -m "feat(advisory): add config, trade, and symbol executors"
```

---

## Phase 6: Telegram Notification

### Task 6.1: Telegram Bot

**Files:**
- Create: `src/ai_trader/advisory/telegram.py`
- Test: `tests/advisory/test_telegram.py`

**Step 1: Add python-telegram-bot dependency**

```bash
cd /Users/gowinder/code/gowinder/trader && pip install python-telegram-bot
```

Add `python-telegram-bot` to `requirements.txt` or `pyproject.toml`.

**Step 2: Write failing test**

```python
# tests/advisory/test_telegram.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ai_trader.advisory.telegram import TelegramNotifier, format_advisory_message
from ai_trader.models.advisory import (
    AdvisoryResult, Suggestion, SuggestionType, Urgency,
)


def test_format_advisory_message():
    result = AdvisoryResult(
        urgency=Urgency.HIGH,
        suggestions=[
            Suggestion(
                type=SuggestionType.PARAM_ADJUST,
                target="global",
                action="reduce_leverage",
                detail={"leverage_max": 5},
                reasoning="市场波动加剧",
                risk_note="可能影响收益",
            ),
        ],
        market_summary="BTC 大幅下跌",
    )
    msg = format_advisory_message(result, advisory_id="test-123")
    assert "HIGH" in msg or "🔴" in msg
    assert "BTC 大幅下跌" in msg
    assert "reduce_leverage" in msg


@pytest.mark.asyncio
async def test_notifier_send_advisory():
    with patch("ai_trader.advisory.telegram.Bot") as mock_bot_cls:
        mock_bot = AsyncMock()
        mock_bot_cls.return_value = mock_bot
        mock_bot.send_message = AsyncMock(return_value=MagicMock(message_id=42))

        notifier = TelegramNotifier(
            bot_token="test_token",
            chat_id="123456",
        )

        result = AdvisoryResult(
            urgency=Urgency.MEDIUM,
            suggestions=[],
            market_summary="市场平稳",
        )
        msg_id = await notifier.send_advisory(result, advisory_id="test-id")
        assert msg_id is not None
        mock_bot.send_message.assert_called_once()
```

**Step 3: Run test to verify it fails**

```bash
cd /Users/gowinder/code/gowinder/trader && python -m pytest tests/advisory/test_telegram.py -v
```
Expected: FAIL (ImportError)

**Step 4: Implement Telegram notifier**

```python
# src/ai_trader/advisory/telegram.py
"""Telegram 通知模块"""

from typing import Optional, Dict, Any, List
from uuid import UUID

from ..models.advisory import AdvisoryResult, Suggestion, Urgency
from ..utils.logger import logger

try:
    from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
    HAS_TELEGRAM = True
except ImportError:
    HAS_TELEGRAM = False
    Bot = None


URGENCY_EMOJI = {
    Urgency.HIGH: "🔴",
    Urgency.MEDIUM: "🟡",
    Urgency.LOW: "🟢",
}


def format_advisory_message(result: AdvisoryResult, advisory_id: str) -> str:
    """格式化 advisory 为 Telegram 消息"""
    emoji = URGENCY_EMOJI.get(result.urgency, "⚪")
    lines = [
        f"🔔 AI 交易建议 [{emoji} {result.urgency.value.upper()}]",
        "",
        f"📊 市场概况: {result.market_summary}",
    ]

    if result.suggestions:
        lines.append("")
        for i, s in enumerate(result.suggestions, 1):
            lines.append(f"建议 {i}/{len(result.suggestions)}: {s.action}")
            lines.append(f"  目标: {s.target}")
            lines.append(f"  理由: {s.reasoning}")
            lines.append(f"  风险: {s.risk_note}")
            lines.append("")
    else:
        lines.append("")
        lines.append("✅ 当前无需调整")

    lines.append(f"📋 ID: {advisory_id}")
    return "\n".join(lines)


def build_suggestion_keyboard(
    advisory_id: str, suggestions: List[Suggestion]
) -> Optional["InlineKeyboardMarkup"]:
    """为每条建议构建 Inline Keyboard"""
    if not HAS_TELEGRAM or not suggestions:
        return None

    buttons = []
    for i, s in enumerate(suggestions):
        buttons.append([
            InlineKeyboardButton(
                f"✅ 采纳 #{i+1}", callback_data=f"accept:{advisory_id}:{i}"
            ),
            InlineKeyboardButton(
                f"❌ 拒绝 #{i+1}", callback_data=f"reject:{advisory_id}:{i}"
            ),
        ])
    return InlineKeyboardMarkup(buttons)


class TelegramNotifier:
    """Telegram 通知器"""

    def __init__(self, bot_token: str = "", chat_id: str = ""):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self._bot = None

        if HAS_TELEGRAM and bot_token:
            self._bot = Bot(token=bot_token)

    @property
    def enabled(self) -> bool:
        return bool(self._bot and self.chat_id)

    async def send_advisory(
        self,
        result: AdvisoryResult,
        advisory_id: str,
    ) -> Optional[int]:
        """发送 advisory 通知，返回 message_id"""
        if not self.enabled:
            logger.debug("Telegram not configured, skipping notification")
            return None

        try:
            text = format_advisory_message(result, advisory_id)
            keyboard = build_suggestion_keyboard(advisory_id, result.suggestions)

            msg = await self._bot.send_message(
                chat_id=self.chat_id,
                text=text,
                reply_markup=keyboard,
                parse_mode=None,
            )
            logger.info(f"Telegram advisory sent: msg_id={msg.message_id}")
            return msg.message_id
        except Exception as e:
            logger.error(f"Failed to send Telegram notification: {e}")
            return None

    async def send_execution_result(
        self,
        suggestion_index: int,
        action: str,
        success: bool,
        message: str,
    ):
        """发送执行结果通知"""
        if not self.enabled:
            return

        try:
            emoji = "✅" if success else "❌"
            text = f"{emoji} 建议 #{suggestion_index + 1} ({action}) 执行结果: {message}"
            await self._bot.send_message(chat_id=self.chat_id, text=text)
        except Exception as e:
            logger.error(f"Failed to send execution result: {e}")
```

**Step 5: Run test to verify it passes**

```bash
cd /Users/gowinder/code/gowinder/trader && python -m pytest tests/advisory/test_telegram.py -v
```
Expected: PASS (2 tests)

**Step 6: Commit**

```bash
git add src/ai_trader/advisory/telegram.py tests/advisory/test_telegram.py
git commit -m "feat(advisory): add Telegram notification with inline keyboard"
```

---

## Phase 7: Scheduler Integration

### Task 7.1: Advisory Service & Scheduler Integration

**Files:**
- Create: `src/ai_trader/advisory/service.py`
- Modify: `src/ai_trader/scheduler.py`
- Test: `tests/advisory/test_service.py`

**Step 1: Write failing test**

```python
# tests/advisory/test_service.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from ai_trader.advisory.service import AdvisoryService


@pytest.fixture
def mock_service_deps():
    engine = AsyncMock()
    engine.generate_advisory = AsyncMock(return_value=uuid4())

    trigger_mgr = MagicMock()
    trigger_mgr.should_run_scheduled = MagicMock(return_value=True)
    trigger_mgr.mark_scheduled_run = MagicMock()
    trigger_mgr.config = MagicMock()
    trigger_mgr.config.price_volatility_enabled = True
    trigger_mgr.config.consecutive_loss_enabled = True
    trigger_mgr.config.unrealized_pnl_enabled = True
    trigger_mgr.config.sentiment_shift_enabled = True
    trigger_mgr.price_volatility = MagicMock()
    trigger_mgr.price_volatility.check = MagicMock(return_value=None)
    trigger_mgr.consecutive_loss = MagicMock()
    trigger_mgr.consecutive_loss.check = MagicMock(return_value=None)
    trigger_mgr.unrealized_pnl = MagicMock()
    trigger_mgr.unrealized_pnl.check = MagicMock(return_value=None)
    trigger_mgr.sentiment_shift = MagicMock()
    trigger_mgr.sentiment_shift.check = MagicMock(return_value=None)

    notifier = AsyncMock()
    notifier.enabled = True
    notifier.send_advisory = AsyncMock(return_value=42)

    persistence = AsyncMock()

    return engine, trigger_mgr, notifier, persistence


@pytest.mark.asyncio
async def test_service_scheduled_run(mock_service_deps):
    engine, trigger_mgr, notifier, persistence = mock_service_deps

    service = AdvisoryService(
        engine=engine,
        trigger_manager=trigger_mgr,
        notifier=notifier,
        persistence=persistence,
    )

    # 提供最小上下文
    await service.check_and_run(
        symbols=["BTC/USDT:USDT"],
        positions=[],
        market_data={"BTC/USDT:USDT": {"current_price": 50000.0, "change_24h": -1.0}},
        sentiment=None,
        current_config={"stop_loss_percent": 5.0},
        consecutive_losses=0,
    )

    engine.generate_advisory.assert_called_once()
    trigger_mgr.mark_scheduled_run.assert_called_once()
    notifier.send_advisory.assert_called_once()


@pytest.mark.asyncio
async def test_service_event_trigger(mock_service_deps):
    engine, trigger_mgr, notifier, persistence = mock_service_deps

    # 定时检查不触发，但事件触发
    trigger_mgr.should_run_scheduled.return_value = False
    trigger_mgr.price_volatility.check.return_value = {"change_pct": -6.0}

    service = AdvisoryService(
        engine=engine,
        trigger_manager=trigger_mgr,
        notifier=notifier,
        persistence=persistence,
    )

    await service.check_and_run(
        symbols=["BTC/USDT:USDT"],
        positions=[],
        market_data={"BTC/USDT:USDT": {"current_price": 47000.0, "change_24h": -6.0}},
        sentiment=None,
        current_config={},
        consecutive_losses=0,
        price_context={"BTC/USDT:USDT": {"current": 47000.0, "previous": 50000.0}},
    )

    engine.generate_advisory.assert_called_once()
```

**Step 2: Run test to verify it fails**

```bash
cd /Users/gowinder/code/gowinder/trader && python -m pytest tests/advisory/test_service.py -v
```
Expected: FAIL (ImportError)

**Step 3: Implement advisory service**

```python
# src/ai_trader/advisory/service.py
"""Advisory 服务 - 协调触发器、引擎和通知"""

from typing import Optional, List, Dict, Any

from .engine import AdvisoryEngine
from .triggers import TriggerManager
from .telegram import TelegramNotifier
from .persistence import AdvisoryPersistenceService
from ..models.advisory import TriggerType
from ..utils.logger import logger


class AdvisoryService:
    """Advisory 服务 - 被 Scheduler 调用"""

    def __init__(
        self,
        engine: AdvisoryEngine,
        trigger_manager: TriggerManager,
        notifier: Optional[TelegramNotifier] = None,
        persistence: Optional[AdvisoryPersistenceService] = None,
    ):
        self.engine = engine
        self.trigger_mgr = trigger_manager
        self.notifier = notifier
        self.persistence = persistence

    async def check_and_run(
        self,
        symbols: List[str],
        positions: List[Dict],
        market_data: Dict[str, Dict],
        sentiment: Optional[Dict],
        current_config: Dict[str, Any],
        consecutive_losses: int = 0,
        price_context: Optional[Dict[str, Dict]] = None,
        account_summary: Optional[Dict] = None,
    ):
        """检查触发条件并运行 advisory"""
        triggered = []

        # 1. 定时触发
        if self.trigger_mgr.should_run_scheduled():
            triggered.append((TriggerType.SCHEDULED, {}))
            self.trigger_mgr.mark_scheduled_run()

        # 2. 事件触发 - 价格波动
        if self.trigger_mgr.config.price_volatility_enabled and price_context:
            for symbol, ctx in price_context.items():
                result = self.trigger_mgr.price_volatility.check(
                    current_price=ctx.get("current", 0),
                    previous_price=ctx.get("previous", 0),
                )
                if result:
                    triggered.append((TriggerType.PRICE_VOLATILITY, {**result, "symbol": symbol}))

        # 3. 事件触发 - 连续亏损
        if self.trigger_mgr.config.consecutive_loss_enabled:
            result = self.trigger_mgr.consecutive_loss.check(consecutive_losses)
            if result:
                triggered.append((TriggerType.CONSECUTIVE_LOSS, result))

        # 4. 事件触发 - 浮亏
        if self.trigger_mgr.config.unrealized_pnl_enabled:
            for p in positions:
                pnl_pct = p.get("roi", 0) or 0
                result = self.trigger_mgr.unrealized_pnl.check(float(pnl_pct))
                if result:
                    triggered.append((TriggerType.UNREALIZED_PNL, {**result, "symbol": p.get("symbol", "")}))

        # 5. 事件触发 - 情绪突变
        if self.trigger_mgr.config.sentiment_shift_enabled and sentiment:
            result = self.trigger_mgr.sentiment_shift.check(
                extreme_fear=sentiment.get("extreme_fear", False),
                extreme_greed=sentiment.get("extreme_greed", False),
            )
            if result:
                triggered.append((TriggerType.SENTIMENT_SHIFT, result))

        if not triggered:
            return

        # 取最高优先级的触发原因（或合并）
        trigger_type = triggered[0][0]
        trigger_detail = triggered[0][1]
        if len(triggered) > 1:
            trigger_detail["additional_triggers"] = [
                {"type": t.value, "detail": d} for t, d in triggered[1:]
            ]

        # 生成 advisory
        advisory_id = await self.engine.generate_advisory(
            trigger_type=trigger_type,
            trigger_detail=trigger_detail,
            symbols=symbols,
            positions=positions,
            market_data=market_data,
            sentiment=sentiment,
            current_config=current_config,
            account_summary=account_summary,
        )

        if advisory_id is None:
            return

        # 通知
        if self.notifier and self.notifier.enabled:
            # 需要从 engine 拿到最新的 result - 简化处理，重新解析
            # 实际应从 engine 缓存或 persistence 获取
            try:
                from .persistence import AdvisoryPersistenceService
                if self.persistence:
                    advisories = await self.persistence.get_pending_advisories(limit=1)
                    if advisories:
                        from .telegram import TelegramNotifier
                        from ..models.advisory import AdvisoryResult, Suggestion, Urgency, SuggestionType
                        adv = advisories[0]
                        result = AdvisoryResult(
                            urgency=Urgency(adv["urgency"]),
                            suggestions=[],
                            market_summary=adv.get("market_summary", ""),
                        )
                        await self.notifier.send_advisory(result, str(advisory_id))
            except Exception as e:
                logger.error(f"Failed to send notification: {e}")

        logger.info(
            f"Advisory check complete: {len(triggered)} trigger(s), "
            f"advisory_id={advisory_id}"
        )
```

**Step 4: Run test to verify it passes**

```bash
cd /Users/gowinder/code/gowinder/trader && python -m pytest tests/advisory/test_service.py -v
```
Expected: PASS (2 tests)

**Step 5: Integrate into Scheduler**

Modify `src/ai_trader/scheduler.py`:

1. Add imports at top (after existing imports):
```python
from .advisory.service import AdvisoryService
from .advisory.engine import AdvisoryEngine
from .advisory.llm_client import AdvisoryLLMClient
from .advisory.persistence import AdvisoryPersistenceService
from .advisory.context import AdvisoryContextBuilder
from .advisory.triggers import TriggerManager, TriggerConfig
from .advisory.telegram import TelegramNotifier
```

2. Add to `__init__` (after `self.parameter_registry = ParameterRegistry()`):
```python
        # Advisory system
        self._advisory_service: Optional[AdvisoryService] = None
        self._price_history: dict = {}  # symbol -> last_price for volatility detection
```

3. Add init method (after `_init_persistence`):
```python
    async def _init_advisory(self):
        """初始化 Advisory 系统"""
        if not config.advisory_enabled:
            return

        try:
            llm_client = AdvisoryLLMClient()
            persistence = AdvisoryPersistenceService(self.db_manager) if self.db_manager else None
            context_builder = AdvisoryContextBuilder(db=self.db_manager)
            engine = AdvisoryEngine(llm_client, persistence, context_builder)

            trigger_config = TriggerConfig(interval_minutes=config.advisory_interval_minutes)
            # 尝试从 Redis 加载触发器配置
            if self._redis:
                try:
                    data = await self._redis.get("advisory:trigger_config")
                    if data:
                        import json
                        cfg = json.loads(data)
                        trigger_config = TriggerConfig(**cfg)
                except Exception:
                    pass

            trigger_mgr = TriggerManager(trigger_config)
            notifier = TelegramNotifier(
                bot_token=config.telegram_bot_token,
                chat_id=config.telegram_chat_id,
            )

            self._advisory_service = AdvisoryService(
                engine=engine,
                trigger_manager=trigger_mgr,
                notifier=notifier,
                persistence=persistence,
            )
            logger.info("Advisory system initialized")
        except Exception as e:
            logger.error(f"Failed to initialize advisory system: {e}")
```

4. Call `_init_advisory` in `start()` method (after `await self._init_redis()`):
```python
        # Initialize Advisory system
        await self._init_advisory()
```

5. Add advisory check in `run_cycle_for_symbol` or at end of main loop (after processing all symbols):
```python
    async def _run_advisory_check(self):
        """运行 advisory 检查"""
        if not self._advisory_service:
            return

        try:
            symbols = config.symbols_list
            positions = []
            market_data = {}
            price_context = {}

            for symbol in symbols:
                try:
                    pos = await self.position_mgr.get_position(symbol)
                    if pos and pos.size > 0:
                        positions.append({
                            "symbol": pos.symbol,
                            "side": pos.side,
                            "size": pos.size,
                            "entry_price": pos.entry_price,
                            "unrealized_pnl": pos.unrealized_pnl,
                            "roi": pos.roi,
                            "leverage": pos.leverage,
                        })

                    ticker = await self.exchange.get_ticker(symbol)
                    current_price = ticker.get("last", 0) if ticker else 0
                    market_data[symbol] = {
                        "current_price": current_price,
                        "change_24h": ticker.get("percentage", 0) if ticker else 0,
                    }

                    previous = self._price_history.get(symbol)
                    if previous:
                        price_context[symbol] = {"current": current_price, "previous": previous}
                    self._price_history[symbol] = current_price
                except Exception as e:
                    logger.debug(f"Advisory data collection error for {symbol}: {e}")

            current_config = {
                "stop_loss_percent": config.stop_loss_percent,
                "take_profit_percent": config.take_profit_percent,
                "leverage_max": config.leverage_max,
                "quant_weight": config.quant_weight,
                "ai_weight": config.ai_weight,
            }

            await self._advisory_service.check_and_run(
                symbols=symbols,
                positions=positions,
                market_data=market_data,
                sentiment=None,
                current_config=current_config,
                consecutive_losses=0,
                price_context=price_context,
            )
        except Exception as e:
            logger.error(f"Advisory check error: {e}")
```

6. Call `_run_advisory_check` in the main loop (inside `start()`, after the symbol cycle):
```python
            try:
                # Run cycle for each symbol
                for symbol in symbols:
                    try:
                        await self.run_cycle_for_symbol(symbol)
                    except Exception as e:
                        logger.error(f"Error in cycle for {symbol}: {e}")

                # Run advisory check
                await self._run_advisory_check()
            except Exception as e:
                logger.error(f"Error in main cycle: {e}")
```

**Step 6: Run all advisory tests**

```bash
cd /Users/gowinder/code/gowinder/trader && python -m pytest tests/advisory/ -v
```
Expected: ALL PASS

**Step 7: Commit**

```bash
git add src/ai_trader/advisory/service.py src/ai_trader/scheduler.py tests/advisory/test_service.py
git commit -m "feat(advisory): integrate advisory service into scheduler"
```

---

## Phase 8: Dashboard API

### Task 8.1: Advisory API Endpoints

**Files:**
- Create: `dashboard/app/routes/api.advisory.ts`
- Create: `dashboard/app/routes/api.advisory-settings.ts`
- Create: `dashboard/app/routes/api.advisory-action.ts`

**Step 1: Create advisory list API**

```typescript
// dashboard/app/routes/api.advisory.ts
import type { LoaderFunctionArgs } from "react-router";
import postgres from "postgres";

export async function loader({ request }: LoaderFunctionArgs) {
  const url = new URL(request.url);
  const status = url.searchParams.get("status") || "pending";
  const limit = parseInt(url.searchParams.get("limit") || "50");

  const sql = postgres(process.env.DATABASE_URL!);

  try {
    const advisories = await sql`
      SELECT
        a.*,
        COALESCE(
          json_agg(
            json_build_object(
              'id', s.id,
              'type', s.type,
              'target', s.target,
              'action', s.action,
              'detail', s.detail,
              'reasoning', s.reasoning,
              'risk_note', s.risk_note,
              'status', s.status,
              'execution_result', s.execution_result,
              'rejection_reason', s.rejection_reason
            )
          ) FILTER (WHERE s.id IS NOT NULL),
          '[]'
        ) as suggestions
      FROM advisories a
      LEFT JOIN advisory_suggestions s ON s.advisory_id = a.id
      ${status === "all" ? sql`` : sql`WHERE a.status = ${status}`}
      GROUP BY a.id
      ORDER BY a.created_at DESC
      LIMIT ${limit}
    `;

    // Count pending
    const [{ count }] = await sql`
      SELECT COUNT(*)::int as count FROM advisories WHERE status = 'pending'
    `;

    await sql.end();
    return Response.json({ advisories, pendingCount: count });
  } catch (error) {
    await sql.end();
    const message = error instanceof Error ? error.message : "Unknown error";
    return Response.json({ error: message }, { status: 500 });
  }
}
```

**Step 2: Create advisory action API (accept/reject/confirm)**

```typescript
// dashboard/app/routes/api.advisory-action.ts
import type { ActionFunctionArgs } from "react-router";
import postgres from "postgres";
import { createClient } from "redis";

export async function action({ request }: ActionFunctionArgs) {
  if (request.method !== "POST") {
    return Response.json({ error: "Method not allowed" }, { status: 405 });
  }

  const body = await request.json();
  const { suggestionId, action: userAction, rejectionReason } = body;

  if (!suggestionId || !userAction) {
    return Response.json({ error: "Missing suggestionId or action" }, { status: 400 });
  }

  const sql = postgres(process.env.DATABASE_URL!);

  try {
    if (userAction === "accept") {
      await sql`
        UPDATE advisory_suggestions
        SET status = 'accepted', updated_at = NOW()
        WHERE id = ${suggestionId}
      `;
    } else if (userAction === "reject") {
      await sql`
        UPDATE advisory_suggestions
        SET status = 'rejected', rejection_reason = ${rejectionReason || null}, updated_at = NOW()
        WHERE id = ${suggestionId}
      `;
    } else if (userAction === "confirm") {
      // 二次确认 → 发送执行请求到 Redis 队列
      await sql`
        UPDATE advisory_suggestions
        SET status = 'confirmed', updated_at = NOW()
        WHERE id = ${suggestionId}
      `;

      // 获取建议详情
      const [suggestion] = await sql`
        SELECT * FROM advisory_suggestions WHERE id = ${suggestionId}
      `;

      if (suggestion) {
        const redisUrl = process.env.REDIS_URL || "redis://localhost:6379";
        const redis = createClient({ url: redisUrl });
        await redis.connect();
        await redis.lPush(
          "advisory:execute_tasks",
          JSON.stringify({
            suggestion_id: suggestionId,
            type: suggestion.type,
            target: suggestion.target,
            action: suggestion.action,
            detail: suggestion.detail,
          })
        );
        await redis.disconnect();
      }
    }

    // 检查是否所有 suggestions 都已处理，如果是则 resolve advisory
    const [{ advisoryId }] = await sql`
      SELECT advisory_id FROM advisory_suggestions WHERE id = ${suggestionId}
    `;
    const [{ pendingCount }] = await sql`
      SELECT COUNT(*)::int as "pendingCount"
      FROM advisory_suggestions
      WHERE advisory_id = ${advisoryId} AND status = 'pending'
    `;
    if (pendingCount === 0) {
      await sql`
        UPDATE advisories SET status = 'resolved', resolved_at = NOW()
        WHERE id = ${advisoryId}
      `;
    }

    await sql.end();
    return Response.json({ success: true });
  } catch (error) {
    await sql.end();
    const message = error instanceof Error ? error.message : "Unknown error";
    return Response.json({ error: message }, { status: 500 });
  }
}
```

**Step 3: Create advisory settings API**

```typescript
// dashboard/app/routes/api.advisory-settings.ts
import type { ActionFunctionArgs, LoaderFunctionArgs } from "react-router";
import { createClient } from "redis";

const REDIS_KEY = "advisory:trigger_config";
const LLM_CONFIG_KEY = "advisory:llm_config";

async function getRedisClient() {
  const redisUrl = process.env.REDIS_URL || "redis://localhost:6379";
  const client = createClient({ url: redisUrl });
  await client.connect();
  return client;
}

export async function loader({ request }: LoaderFunctionArgs) {
  try {
    const client = await getRedisClient();
    const triggerConfig = await client.get(REDIS_KEY);
    const llmConfig = await client.get(LLM_CONFIG_KEY);
    await client.disconnect();

    return Response.json({
      triggerConfig: triggerConfig ? JSON.parse(triggerConfig) : {
        interval_minutes: 60,
        price_volatility_enabled: true,
        price_volatility_threshold: 5.0,
        consecutive_loss_enabled: true,
        consecutive_loss_threshold: 3,
        unrealized_pnl_enabled: true,
        unrealized_pnl_threshold: -5.0,
        sentiment_shift_enabled: true,
        cooldown_minutes: 30,
      },
      llmConfig: llmConfig ? JSON.parse(llmConfig) : {
        provider: "openrouter",
        model: "deepseek/deepseek-chat",
        base_url: "",
      },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return Response.json({ error: message }, { status: 500 });
  }
}

export async function action({ request }: ActionFunctionArgs) {
  if (request.method !== "POST") {
    return Response.json({ error: "Method not allowed" }, { status: 405 });
  }

  try {
    const body = await request.json();
    const client = await getRedisClient();

    if (body.triggerConfig) {
      await client.set(REDIS_KEY, JSON.stringify(body.triggerConfig));
      await client.publish("advisory:config:updated", JSON.stringify(body.triggerConfig));
    }
    if (body.llmConfig) {
      await client.set(LLM_CONFIG_KEY, JSON.stringify(body.llmConfig));
    }

    await client.disconnect();
    return Response.json({ success: true });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return Response.json({ error: message }, { status: 500 });
  }
}
```

**Step 4: Commit**

```bash
git add dashboard/app/routes/api.advisory.ts dashboard/app/routes/api.advisory-action.ts dashboard/app/routes/api.advisory-settings.ts
git commit -m "feat(advisory): add dashboard API endpoints for advisory system"
```

---

## Phase 9: Dashboard UI Pages

### Task 9.1: Advisory List Page

**Files:**
- Create: `dashboard/app/routes/dashboard.advisory.tsx`

**Step 1: Implement advisory list page**

Create `dashboard/app/routes/dashboard.advisory.tsx` with:
- Fetch advisories from `api.advisory` loader
- Display advisory cards with urgency color coding
- Expandable suggestion details
- Accept/Reject/Confirm buttons per suggestion
- Status filters (pending/resolved/all)
- Auto-refresh pending count

Follow the existing pattern from `dashboard.decisions.tsx` for card layout, data fetching, and action handling.

Key UI elements:
- Filter bar: urgency level + status + time range
- Advisory card: urgency badge, trigger type, market summary, timestamp
- Suggestion row: type icon, target, action, reasoning, risk_note
- Action buttons: 采纳 → 确认执行? → 执行 / 拒绝(可填理由)
- Execution result display

**Step 2: Commit**

```bash
git add dashboard/app/routes/dashboard.advisory.tsx
git commit -m "feat(advisory): add advisory list dashboard page"
```

---

### Task 9.2: Advisory Settings Page

**Files:**
- Create: `dashboard/app/routes/dashboard.advisory-settings.tsx`

**Step 1: Implement settings page**

Create `dashboard/app/routes/dashboard.advisory-settings.tsx` with:
- Fetch settings from `api.advisory-settings` loader
- Trigger config section: interval slider, per-trigger toggle + threshold + cooldown
- Telegram config: bot token, chat id, push level
- LLM config: provider dropdown, model input, base URL
- Save button → POST to `api.advisory-settings`

Follow existing pattern from `dashboard.strategy.tsx` and `dashboard.settings.tsx`.

**Step 2: Commit**

```bash
git add dashboard/app/routes/dashboard.advisory-settings.tsx
git commit -m "feat(advisory): add advisory settings dashboard page"
```

---

### Task 9.3: Navigation & Badge

**Files:**
- Modify: `dashboard/app/routes/dashboard.tsx` (or wherever the sidebar/nav is defined)

**Step 1: Add advisory nav items**

Add navigation entries for:
- "AI 建议" (with pending count badge) → `/dashboard/advisory`
- "建议设置" → `/dashboard/advisory-settings`

Use `useFetcher` to periodically poll pending count from `api.advisory?status=pending`.

**Step 2: Commit**

```bash
git add dashboard/app/routes/dashboard.tsx
git commit -m "feat(advisory): add advisory navigation with pending badge"
```

---

## Phase 10: Telegram Callback Handler

### Task 10.1: Telegram Bot Callback Handler

**Files:**
- Modify: `src/ai_trader/advisory/telegram.py`
- Modify: `src/ai_trader/advisory/service.py`
- Test: `tests/advisory/test_telegram.py` (add tests)

**Step 1: Add callback handler to Telegram module**

Extend `TelegramNotifier` with a polling/webhook loop to handle Inline Keyboard callbacks:

```python
# Add to telegram.py
async def start_callback_handler(self, persistence, executors):
    """启动 Telegram callback 处理（使用 polling）"""
    if not HAS_TELEGRAM or not self.enabled:
        return

    from telegram.ext import Application, CallbackQueryHandler
    app = Application.builder().token(self.bot_token).build()

    async def handle_callback(update, context):
        query = update.callback_query
        await query.answer()

        # Parse callback data: "accept:advisory_id:suggestion_index"
        data = query.data
        parts = data.split(":")
        if len(parts) != 3:
            return

        action, advisory_id, idx = parts[0], parts[1], int(parts[2])

        # Verify chat_id
        if str(query.message.chat_id) != self.chat_id:
            return

        if action == "accept":
            await persistence.update_suggestion_status_by_index(advisory_id, idx, "accepted")
            # Replace keyboard with confirm button
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("⚠️ 确认执行?", callback_data=f"confirm:{advisory_id}:{idx}"),
                    InlineKeyboardButton("↩️ 取消", callback_data=f"cancel:{advisory_id}:{idx}"),
                ]
            ])
            await query.edit_message_reply_markup(reply_markup=keyboard)
        elif action == "reject":
            await persistence.update_suggestion_status_by_index(advisory_id, idx, "rejected")
            await query.edit_message_text(text=query.message.text + f"\n\n❌ 建议 #{idx+1} 已拒绝")
        elif action == "confirm":
            # Execute via Redis queue
            # ...push to advisory:execute_tasks
            await query.edit_message_text(text=query.message.text + f"\n\n⏳ 建议 #{idx+1} 执行中...")
        elif action == "cancel":
            await persistence.update_suggestion_status_by_index(advisory_id, idx, "pending")
            await query.edit_message_text(text=query.message.text + f"\n\n↩️ 建议 #{idx+1} 已取消")

    app.add_handler(CallbackQueryHandler(handle_callback))
    # Run polling in background
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
```

**Step 2: Commit**

```bash
git add src/ai_trader/advisory/telegram.py tests/advisory/test_telegram.py
git commit -m "feat(advisory): add Telegram inline keyboard callback handler"
```

---

## Phase 11: Execution Task Consumer

### Task 11.1: Redis Execution Queue Consumer

**Files:**
- Modify: `src/ai_trader/scheduler.py`

**Step 1: Add execution queue listener in Scheduler**

Add method similar to `_backtest_task_listener`:

```python
async def _advisory_execute_listener(self):
    """监听 advisory 执行队列"""
    if not self._redis or not self._advisory_service:
        return

    logger.info("Advisory execution queue listener started")
    while self.running:
        try:
            result = await self._redis.brpop("advisory:execute_tasks", timeout=5)
            if result:
                _, task_json = result
                task = json.loads(task_json)
                await self._execute_advisory_suggestion(task)
        except Exception as e:
            logger.error(f"Advisory execution error: {e}")
            await asyncio.sleep(5)

async def _execute_advisory_suggestion(self, task: dict):
    """执行单条 advisory suggestion"""
    from .advisory.executors import ConfigExecutor, TradeExecutor, SymbolExecutor

    suggestion_id = task["suggestion_id"]
    suggestion_type = task["type"]
    target = task["target"]
    action = task["action"]
    detail = task.get("detail", {})

    try:
        if suggestion_type == "param_adjust":
            executor = ConfigExecutor(self._redis)
            result = await executor.execute(action, target, detail)
        elif suggestion_type == "position_action":
            executor = TradeExecutor(self.order_mgr, self.position_mgr)
            result = await executor.execute(action, target, detail)
        elif suggestion_type == "symbol_change":
            executor = SymbolExecutor(self._redis)
            result = await executor.execute(action, target, detail)
        else:
            result = ExecutionResult(success=False, message=f"未知类型: {suggestion_type}")

        # 更新数据库状态
        if self._advisory_service and self._advisory_service.persistence:
            status = "executed" if result.success else "failed"
            await self._advisory_service.persistence.update_suggestion_status(
                suggestion_id,
                status,
                execution_result={"success": result.success, "message": result.message},
            )

        logger.info(f"Advisory suggestion executed: {suggestion_id} -> {result.success}: {result.message}")
    except Exception as e:
        logger.error(f"Advisory suggestion execution failed: {e}")
        if self._advisory_service and self._advisory_service.persistence:
            await self._advisory_service.persistence.update_suggestion_status(
                suggestion_id, "failed", execution_result={"error": str(e)}
            )
```

Launch it in `_init_redis`:
```python
asyncio.create_task(self._advisory_execute_listener())
```

**Step 2: Commit**

```bash
git add src/ai_trader/scheduler.py
git commit -m "feat(advisory): add execution queue consumer in scheduler"
```

---

## Phase 12: Final Integration & Testing

### Task 12.1: Run Full Test Suite

```bash
cd /Users/gowinder/code/gowinder/trader && python -m pytest tests/ -v
```

Ensure all 93+ existing tests pass plus all new advisory tests.

### Task 12.2: Advisory Config Redis Listener

**Files:**
- Modify: `src/ai_trader/scheduler.py`

Add Redis subscription for `advisory:config:updated` in `_config_listener` to hot-reload trigger config.

### Task 12.3: Final Commit

```bash
git add -A
git commit -m "feat(advisory): complete AI advisory system integration"
```

---

## Summary of Files

**New Python files (src/ai_trader/advisory/):**
- `__init__.py`
- `llm_client.py` - Independent LLM client
- `triggers.py` - Trigger system (scheduled + event-driven)
- `context.py` - Context builder for LLM prompts
- `prompts.py` - System/user prompts + JSON schema
- `engine.py` - Core advisory generation engine
- `persistence.py` - Database persistence
- `executors.py` - Config/Trade/Symbol executors
- `telegram.py` - Telegram notification + callback handler
- `service.py` - Service coordinator

**New test files (tests/advisory/):**
- `__init__.py`
- `test_models.py`
- `test_persistence.py`
- `test_llm_client.py`
- `test_triggers.py`
- `test_context.py`
- `test_engine.py`
- `test_executors.py`
- `test_telegram.py`
- `test_service.py`

**New Dashboard files:**
- `dashboard/app/routes/api.advisory.ts`
- `dashboard/app/routes/api.advisory-action.ts`
- `dashboard/app/routes/api.advisory-settings.ts`
- `dashboard/app/routes/dashboard.advisory.tsx`
- `dashboard/app/routes/dashboard.advisory-settings.tsx`

**Modified files:**
- `src/ai_trader/config.py` - Add advisory + telegram config
- `src/ai_trader/scheduler.py` - Integrate advisory service
- `dashboard/db/schema.ts` - Add advisory tables
- `dashboard/app/routes/dashboard.tsx` - Add nav items
- `tests/test_config.py` - Add config test
