# AI 记忆与策略自优化系统实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现 AI 交易记忆系统，支持复盘反思和自动参数优化

**Architecture:** 双层记忆（短期+长期）+ 复盘引擎 + 影子运行验证

**Tech Stack:** Python 3.11+, asyncpg, pydantic, scipy (统计验证)

---

## Phase 1: 数据模型与数据库

### Task 1.1: 创建记忆数据模型

**Files:**
- Create: `src/ai_trader/memory/__init__.py`
- Create: `src/ai_trader/memory/models.py`
- Create: `tests/memory/__init__.py`
- Create: `tests/memory/test_models.py`

**Step 1: 创建目录结构**

```bash
mkdir -p src/ai_trader/memory tests/memory
touch src/ai_trader/memory/__init__.py tests/memory/__init__.py
```

**Step 2: 写测试 - TradeMemoryEntry 模型**

```python
# tests/memory/test_models.py
import pytest
from datetime import datetime, timedelta
from ai_trader.memory.models import TradeMemoryEntry, DistilledRule


class TestTradeMemoryEntry:
    def test_create_entry(self):
        entry = TradeMemoryEntry(
            trade_id="trade_001",
            timestamp=datetime.now(),
            symbol="BTCUSDT",
            action="open_long",
            confidence=75.0,
            leverage=5.0,
            reasoning="趋势向上",
            market_state="strong_trend",
            entry_price=50000.0,
        )
        assert entry.trade_id == "trade_001"
        assert entry.action == "open_long"
        assert entry.is_winner is None  # 未平仓

    def test_entry_with_result(self):
        entry = TradeMemoryEntry(
            trade_id="trade_002",
            timestamp=datetime.now(),
            symbol="BTCUSDT",
            action="close_long",
            confidence=80.0,
            leverage=5.0,
            reasoning="止盈",
            market_state="strong_trend",
            entry_price=50000.0,
            exit_price=52000.0,
            pnl_percent=4.0,
            is_winner=True,
        )
        assert entry.is_winner is True
        assert entry.pnl_percent == 4.0


class TestDistilledRule:
    def test_create_rule(self):
        rule = DistilledRule(
            rule_id="rule_001",
            condition={"market_state": "ranging", "rsi": ">70"},
            recommendation={"confidence_threshold": "+10"},
            sample_size=25,
            win_rate=0.72,
            avg_pnl=0.015,
            p_value=0.03,
        )
        assert rule.status == "candidate"
        assert rule.is_statistically_valid()

    def test_rule_invalid_p_value(self):
        rule = DistilledRule(
            rule_id="rule_002",
            condition={"market_state": "trending"},
            recommendation={"leverage": "-1"},
            sample_size=15,
            win_rate=0.55,
            avg_pnl=0.005,
            p_value=0.12,
        )
        assert not rule.is_statistically_valid()
```

**Step 3: 运行测试验证失败**

```bash
pytest tests/memory/test_models.py -v
```
Expected: FAIL - module not found

**Step 4: 实现模型**

```python
# src/ai_trader/memory/models.py
"""记忆系统数据模型"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
from enum import Enum


class RuleStatus(str, Enum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


@dataclass
class TradeMemoryEntry:
    """短期记忆条目 - 单笔交易完整上下文"""

    # 基础信息
    trade_id: str
    timestamp: datetime
    symbol: str

    # 决策快照
    action: str
    confidence: float
    leverage: float
    reasoning: str

    # 市场上下文
    market_state: str
    timeframe_alignment: dict = field(default_factory=dict)
    technical_snapshot: dict = field(default_factory=dict)
    patterns_detected: list[str] = field(default_factory=list)

    # 结果
    entry_price: float = 0.0
    exit_price: Optional[float] = None
    pnl_percent: Optional[float] = None
    max_adverse_excursion: float = 0.0
    max_favorable_excursion: float = 0.0
    holding_duration: Optional[timedelta] = None

    # 分析维度
    hour_of_day: int = 0
    day_of_week: int = 0
    consecutive_losses: int = 0
    is_winner: Optional[bool] = None

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "trade_id": self.trade_id,
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "action": self.action,
            "confidence": self.confidence,
            "leverage": self.leverage,
            "reasoning": self.reasoning,
            "market_state": self.market_state,
            "timeframe_alignment": self.timeframe_alignment,
            "technical_snapshot": self.technical_snapshot,
            "patterns_detected": self.patterns_detected,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "pnl_percent": self.pnl_percent,
            "max_adverse_excursion": self.max_adverse_excursion,
            "max_favorable_excursion": self.max_favorable_excursion,
            "holding_duration": str(self.holding_duration) if self.holding_duration else None,
            "hour_of_day": self.hour_of_day,
            "day_of_week": self.day_of_week,
            "consecutive_losses": self.consecutive_losses,
            "is_winner": self.is_winner,
        }


@dataclass
class DistilledRule:
    """长期记忆条目 - 提炼后的规则"""

    rule_id: str
    condition: dict
    recommendation: dict

    # 统计验证
    sample_size: int
    win_rate: float
    avg_pnl: float
    p_value: float

    # 元数据
    reasoning: str = ""
    status: str = RuleStatus.CANDIDATE.value
    validation_count: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    last_validated: Optional[datetime] = None

    # 验证阈值
    P_VALUE_THRESHOLD: float = field(default=0.05, repr=False)
    MIN_SAMPLE_SIZE: int = field(default=20, repr=False)

    def is_statistically_valid(self) -> bool:
        """检查规则是否通过统计验证"""
        return (
            self.p_value < self.P_VALUE_THRESHOLD
            and self.sample_size >= self.MIN_SAMPLE_SIZE
        )

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "rule_id": self.rule_id,
            "condition": self.condition,
            "recommendation": self.recommendation,
            "sample_size": self.sample_size,
            "win_rate": self.win_rate,
            "avg_pnl": self.avg_pnl,
            "p_value": self.p_value,
            "reasoning": self.reasoning,
            "status": self.status,
            "validation_count": self.validation_count,
            "created_at": self.created_at.isoformat(),
            "last_validated": self.last_validated.isoformat() if self.last_validated else None,
        }
```

**Step 5: 更新 __init__.py**

```python
# src/ai_trader/memory/__init__.py
"""AI 记忆系统"""

from .models import TradeMemoryEntry, DistilledRule, RuleStatus

__all__ = ["TradeMemoryEntry", "DistilledRule", "RuleStatus"]
```

**Step 6: 运行测试验证通过**

```bash
pytest tests/memory/test_models.py -v
```
Expected: PASS

**Step 7: 提交**

```bash
git add src/ai_trader/memory/ tests/memory/
git commit -m "feat(memory): add memory data models"
```

---

### Task 1.2: 创建参数注册表模型

**Files:**
- Create: `src/ai_trader/optimization/__init__.py`
- Create: `src/ai_trader/optimization/parameter_registry.py`
- Create: `tests/optimization/__init__.py`
- Create: `tests/optimization/test_parameter_registry.py`

**Step 1: 创建目录**

```bash
mkdir -p src/ai_trader/optimization tests/optimization
touch src/ai_trader/optimization/__init__.py tests/optimization/__init__.py
```

**Step 2: 写测试**

```python
# tests/optimization/test_parameter_registry.py
import pytest
from ai_trader.optimization.parameter_registry import (
    AdjustableParameter,
    ParameterRegistry,
)


class TestAdjustableParameter:
    def test_create_parameter(self):
        param = AdjustableParameter(
            name="confidence_threshold",
            current_value=60.0,
            min_bound=40.0,
            max_bound=90.0,
            step=5.0,
            category="decision",
        )
        assert param.current_value == 60.0
        assert param.is_within_bounds(60.0)

    def test_bound_validation(self):
        param = AdjustableParameter(
            name="max_leverage",
            current_value=5.0,
            min_bound=1.0,
            max_bound=10.0,
            step=1.0,
            category="position",
        )
        assert param.is_within_bounds(5.0)
        assert not param.is_within_bounds(15.0)
        assert not param.is_within_bounds(0.5)

    def test_clamp_value(self):
        param = AdjustableParameter(
            name="stop_loss_percent",
            current_value=5.0,
            min_bound=2.0,
            max_bound=10.0,
            step=0.5,
            category="risk",
        )
        assert param.clamp(1.0) == 2.0
        assert param.clamp(15.0) == 10.0
        assert param.clamp(5.0) == 5.0


class TestParameterRegistry:
    def test_get_parameter(self):
        registry = ParameterRegistry()
        param = registry.get("confidence_threshold")
        assert param is not None
        assert param.category == "decision"

    def test_update_parameter(self):
        registry = ParameterRegistry()
        old_value = registry.get("confidence_threshold").current_value
        registry.update("confidence_threshold", 70.0)
        assert registry.get("confidence_threshold").current_value == 70.0

    def test_update_with_boundary_enforcement(self):
        registry = ParameterRegistry()
        registry.update("max_leverage", 20.0)  # 超出边界
        assert registry.get("max_leverage").current_value == 10.0  # 被限制

    def test_get_all_by_category(self):
        registry = ParameterRegistry()
        risk_params = registry.get_by_category("risk")
        assert len(risk_params) >= 2  # stop_loss, take_profit
```

**Step 3: 运行测试验证失败**

```bash
pytest tests/optimization/test_parameter_registry.py -v
```
Expected: FAIL

**Step 4: 实现参数注册表**

```python
# src/ai_trader/optimization/parameter_registry.py
"""参数注册表 - 管理所有可调参数及其硬边界"""

from dataclasses import dataclass, field
from typing import Optional
from copy import deepcopy


@dataclass
class AdjustableParameter:
    """可调参数定义"""

    name: str
    current_value: float
    min_bound: float
    max_bound: float
    step: float
    category: str  # decision, position, risk, timing
    description: str = ""

    def is_within_bounds(self, value: float) -> bool:
        """检查值是否在边界内"""
        return self.min_bound <= value <= self.max_bound

    def clamp(self, value: float) -> float:
        """将值限制在边界内"""
        return max(self.min_bound, min(self.max_bound, value))


# 默认参数配置
DEFAULT_PARAMETERS = {
    # 决策偏好类
    "confidence_threshold": AdjustableParameter(
        name="confidence_threshold",
        current_value=60.0,
        min_bound=40.0,
        max_bound=90.0,
        step=5.0,
        category="decision",
        description="开仓置信度阈值",
    ),
    "hold_bias": AdjustableParameter(
        name="hold_bias",
        current_value=0.0,
        min_bound=-0.3,
        max_bound=0.3,
        step=0.05,
        category="decision",
        description="HOLD 倾向权重",
    ),
    "quant_ai_weight_trend": AdjustableParameter(
        name="quant_ai_weight_trend",
        current_value=0.7,
        min_bound=0.3,
        max_bound=0.9,
        step=0.1,
        category="decision",
        description="趋势市量化权重",
    ),
    "quant_ai_weight_ranging": AdjustableParameter(
        name="quant_ai_weight_ranging",
        current_value=0.4,
        min_bound=0.2,
        max_bound=0.7,
        step=0.1,
        category="decision",
        description="震荡市量化权重",
    ),
    # 仓位控制类
    "max_position_percent": AdjustableParameter(
        name="max_position_percent",
        current_value=20.0,
        min_bound=5.0,
        max_bound=30.0,
        step=5.0,
        category="position",
        description="最大仓位百分比",
    ),
    "max_leverage": AdjustableParameter(
        name="max_leverage",
        current_value=5.0,
        min_bound=1.0,
        max_bound=10.0,
        step=1.0,
        category="position",
        description="最大杠杆",
    ),
    # 风险控制类
    "stop_loss_percent": AdjustableParameter(
        name="stop_loss_percent",
        current_value=5.0,
        min_bound=2.0,
        max_bound=10.0,
        step=0.5,
        category="risk",
        description="止损百分比",
    ),
    "take_profit_percent": AdjustableParameter(
        name="take_profit_percent",
        current_value=10.0,
        min_bound=5.0,
        max_bound=25.0,
        step=1.0,
        category="risk",
        description="止盈百分比",
    ),
}


class ParameterRegistry:
    """参数注册表"""

    def __init__(self, parameters: Optional[dict[str, AdjustableParameter]] = None):
        """初始化参数注册表"""
        self._parameters = deepcopy(parameters or DEFAULT_PARAMETERS)
        self._history: list[dict] = []

    def get(self, name: str) -> Optional[AdjustableParameter]:
        """获取参数"""
        return self._parameters.get(name)

    def update(self, name: str, new_value: float, reason: str = "") -> bool:
        """更新参数值（自动限制在边界内）"""
        param = self._parameters.get(name)
        if not param:
            return False

        old_value = param.current_value
        param.current_value = param.clamp(new_value)

        # 记录历史
        self._history.append({
            "name": name,
            "old_value": old_value,
            "new_value": param.current_value,
            "reason": reason,
        })
        return True

    def get_by_category(self, category: str) -> list[AdjustableParameter]:
        """按类别获取参数"""
        return [p for p in self._parameters.values() if p.category == category]

    def get_all(self) -> dict[str, AdjustableParameter]:
        """获取所有参数"""
        return self._parameters.copy()

    def to_dict(self) -> dict[str, float]:
        """导出为简单字典"""
        return {name: p.current_value for name, p in self._parameters.items()}

    def get_history(self) -> list[dict]:
        """获取变更历史"""
        return self._history.copy()
```

**Step 5: 更新 __init__.py**

```python
# src/ai_trader/optimization/__init__.py
"""策略优化系统"""

from .parameter_registry import AdjustableParameter, ParameterRegistry

__all__ = ["AdjustableParameter", "ParameterRegistry"]
```

**Step 6: 运行测试**

```bash
pytest tests/optimization/test_parameter_registry.py -v
```
Expected: PASS

**Step 7: 提交**

```bash
git add src/ai_trader/optimization/ tests/optimization/
git commit -m "feat(optimization): add parameter registry with boundaries"
```

---

### Task 1.3: 创建数据库迁移脚本

**Files:**
- Create: `dashboard/prisma/migrations/YYYYMMDD_add_memory_tables/migration.sql`

**Step 1: 创建迁移文件**

```sql
-- dashboard/prisma/migrations/20260201000000_add_memory_tables/migration.sql

-- 短期记忆表
CREATE TABLE IF NOT EXISTS trade_memory (
    id SERIAL PRIMARY KEY,
    trade_id VARCHAR(64) UNIQUE NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(20) NOT NULL,

    -- 决策快照
    action VARCHAR(20) NOT NULL,
    confidence FLOAT NOT NULL,
    leverage FLOAT NOT NULL,
    reasoning TEXT,

    -- 市场上下文
    market_state VARCHAR(20),
    timeframe_alignment JSONB,
    technical_snapshot JSONB,
    patterns_detected JSONB,

    -- 结果
    entry_price FLOAT,
    exit_price FLOAT,
    pnl_percent FLOAT,
    max_adverse_excursion FLOAT,
    max_favorable_excursion FLOAT,
    holding_duration INTERVAL,

    -- 分析维度
    hour_of_day INT,
    day_of_week INT,
    consecutive_losses INT,
    is_winner BOOLEAN,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 长期记忆表（提炼规则）
CREATE TABLE IF NOT EXISTS distilled_rules (
    id SERIAL PRIMARY KEY,
    rule_id VARCHAR(64) UNIQUE NOT NULL,

    -- 规则定义
    condition JSONB NOT NULL,
    recommendation JSONB NOT NULL,
    reasoning TEXT,

    -- 统计验证
    sample_size INT NOT NULL,
    win_rate FLOAT NOT NULL,
    avg_pnl FLOAT NOT NULL,
    p_value FLOAT NOT NULL,

    -- 状态
    status VARCHAR(20) DEFAULT 'candidate',
    validation_count INT DEFAULT 0,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_validated TIMESTAMPTZ
);

-- 参数历史表
CREATE TABLE IF NOT EXISTS parameter_history (
    id SERIAL PRIMARY KEY,
    param_name VARCHAR(64) NOT NULL,
    old_value FLOAT NOT NULL,
    new_value FLOAT NOT NULL,
    trigger_type VARCHAR(20),
    reasoning TEXT,
    changed_at TIMESTAMPTZ DEFAULT NOW()
);

-- 影子运行结果表
CREATE TABLE IF NOT EXISTS shadow_runs (
    id SERIAL PRIMARY KEY,
    run_id VARCHAR(64) UNIQUE NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,

    current_params JSONB NOT NULL,
    candidate_params JSONB NOT NULL,

    current_trades INT DEFAULT 0,
    candidate_trades INT DEFAULT 0,
    current_win_rate FLOAT,
    candidate_win_rate FLOAT,
    current_avg_pnl FLOAT,
    candidate_avg_pnl FLOAT,

    status VARCHAR(20) DEFAULT 'running',
    conclusion TEXT
);

-- 复盘记录表
CREATE TABLE IF NOT EXISTS reflection_logs (
    id SERIAL PRIMARY KEY,
    reflection_id VARCHAR(64) UNIQUE NOT NULL,
    triggered_at TIMESTAMPTZ NOT NULL,
    trades_analyzed INT NOT NULL,

    summary TEXT,
    insights JSONB,
    candidate_rules JSONB,
    parameter_suggestions JSONB,

    rules_created INT DEFAULT 0,
    shadow_run_started BOOLEAN DEFAULT FALSE
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_trade_memory_timestamp ON trade_memory(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_trade_memory_symbol ON trade_memory(symbol);
CREATE INDEX IF NOT EXISTS idx_trade_memory_market_state ON trade_memory(market_state);
CREATE INDEX IF NOT EXISTS idx_distilled_rules_status ON distilled_rules(status);
CREATE INDEX IF NOT EXISTS idx_shadow_runs_status ON shadow_runs(status);
CREATE INDEX IF NOT EXISTS idx_parameter_history_param ON parameter_history(param_name);
```

**Step 2: 提交**

```bash
git add dashboard/prisma/migrations/
git commit -m "feat(db): add memory system tables migration"
```

---

## Phase 2: 记忆收集器

### Task 2.1: 实现 TradeMemoryCollector

**Files:**
- Create: `src/ai_trader/memory/collector.py`
- Create: `tests/memory/test_collector.py`

**Step 1: 写测试**

```python
# tests/memory/test_collector.py
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from ai_trader.memory.collector import TradeMemoryCollector
from ai_trader.memory.models import TradeMemoryEntry


class TestTradeMemoryCollector:
    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        db.fetchval = AsyncMock(return_value=1)
        return db

    @pytest.fixture
    def collector(self, mock_db):
        return TradeMemoryCollector(mock_db)

    @pytest.mark.asyncio
    async def test_collect_trade(self, collector):
        # 模拟交易数据
        position = MagicMock()
        position.symbol = "BTCUSDT"
        position.side = "long"
        position.entry_price = 50000.0
        position.size = 0.1

        result = MagicMock()
        result.exit_price = 52000.0
        result.pnl = 200.0
        result.pnl_percent = 4.0

        decision = MagicMock()
        decision.action = "close_long"
        decision.confidence = 80.0
        decision.leverage = 5
        decision.reasoning = "止盈"

        technical = MagicMock()
        technical.trend = "bullish"

        market_state = "strong_trend"

        entry = await collector.collect(
            position=position,
            result=result,
            decision=decision,
            technical=technical,
            market_state=market_state,
        )

        assert entry.symbol == "BTCUSDT"
        assert entry.pnl_percent == 4.0
        assert entry.is_winner is True

    @pytest.mark.asyncio
    async def test_get_recent_memories(self, collector, mock_db):
        mock_db.fetch = AsyncMock(return_value=[
            {
                "trade_id": "t1",
                "timestamp": datetime.now(),
                "symbol": "BTCUSDT",
                "action": "close_long",
                "confidence": 75.0,
                "leverage": 5.0,
                "reasoning": "test",
                "market_state": "trending",
                "is_winner": True,
                "pnl_percent": 2.0,
            }
        ])

        memories = await collector.get_recent(limit=10)
        assert len(memories) == 1
        assert memories[0].trade_id == "t1"
```

**Step 2: 运行测试验证失败**

```bash
pytest tests/memory/test_collector.py -v
```
Expected: FAIL

**Step 3: 实现收集器**

```python
# src/ai_trader/memory/collector.py
"""交易记忆收集器"""

import json
from datetime import datetime
from typing import Optional
from uuid import uuid4

from .models import TradeMemoryEntry
from ..persistence.database import DatabaseManager
from ..utils.logger import logger


class TradeMemoryCollector:
    """收集交易数据到短期记忆"""

    def __init__(self, db: DatabaseManager):
        self.db = db
        self._consecutive_losses = 0

    async def collect(
        self,
        position,
        result,
        decision,
        technical,
        market_state: str,
        patterns: Optional[list[str]] = None,
    ) -> TradeMemoryEntry:
        """收集单笔交易到记忆

        Args:
            position: 仓位信息
            result: 交易结果
            decision: 决策信息
            technical: 技术分析结果
            market_state: 市场状态
            patterns: 识别到的形态

        Returns:
            TradeMemoryEntry
        """
        now = datetime.now()
        is_winner = result.pnl > 0 if result else None

        # 更新连亏计数
        if is_winner is False:
            self._consecutive_losses += 1
        elif is_winner is True:
            self._consecutive_losses = 0

        entry = TradeMemoryEntry(
            trade_id=f"trade_{uuid4().hex[:8]}",
            timestamp=now,
            symbol=position.symbol,
            action=decision.action,
            confidence=decision.confidence,
            leverage=float(decision.leverage),
            reasoning=decision.reasoning,
            market_state=market_state,
            technical_snapshot={
                "trend": technical.trend if technical else None,
                "trend_confidence": technical.trend_confidence if technical else None,
                "signal_strength": technical.signal_strength if technical else None,
            },
            patterns_detected=patterns or [],
            entry_price=position.entry_price,
            exit_price=result.exit_price if result else None,
            pnl_percent=result.pnl_percent if result else None,
            hour_of_day=now.hour,
            day_of_week=now.weekday(),
            consecutive_losses=self._consecutive_losses,
            is_winner=is_winner,
        )

        # 持久化到数据库
        await self._save_to_db(entry)

        logger.info(f"交易记忆已收集: {entry.trade_id}, winner={is_winner}")
        return entry

    async def _save_to_db(self, entry: TradeMemoryEntry) -> None:
        """保存到数据库"""
        await self.db.execute(
            """
            INSERT INTO trade_memory (
                trade_id, timestamp, symbol, action, confidence, leverage, reasoning,
                market_state, timeframe_alignment, technical_snapshot, patterns_detected,
                entry_price, exit_price, pnl_percent, max_adverse_excursion,
                max_favorable_excursion, holding_duration, hour_of_day, day_of_week,
                consecutive_losses, is_winner
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21
            )
            """,
            entry.trade_id,
            entry.timestamp,
            entry.symbol,
            entry.action,
            entry.confidence,
            entry.leverage,
            entry.reasoning,
            entry.market_state,
            json.dumps(entry.timeframe_alignment),
            json.dumps(entry.technical_snapshot),
            json.dumps(entry.patterns_detected),
            entry.entry_price,
            entry.exit_price,
            entry.pnl_percent,
            entry.max_adverse_excursion,
            entry.max_favorable_excursion,
            str(entry.holding_duration) if entry.holding_duration else None,
            entry.hour_of_day,
            entry.day_of_week,
            entry.consecutive_losses,
            entry.is_winner,
        )

    async def get_recent(self, limit: int = 100) -> list[TradeMemoryEntry]:
        """获取最近的记忆"""
        rows = await self.db.fetch(
            """
            SELECT * FROM trade_memory
            ORDER BY timestamp DESC
            LIMIT $1
            """,
            limit,
        )
        return [self._row_to_entry(row) for row in rows]

    async def get_count_since_last_reflection(self) -> int:
        """获取自上次复盘以来的交易数"""
        result = await self.db.fetchval(
            """
            SELECT COUNT(*) FROM trade_memory
            WHERE timestamp > COALESCE(
                (SELECT MAX(triggered_at) FROM reflection_logs),
                '1970-01-01'::timestamp
            )
            """
        )
        return result or 0

    def _row_to_entry(self, row) -> TradeMemoryEntry:
        """数据库行转换为 Entry"""
        return TradeMemoryEntry(
            trade_id=row["trade_id"],
            timestamp=row["timestamp"],
            symbol=row["symbol"],
            action=row["action"],
            confidence=row["confidence"],
            leverage=row["leverage"],
            reasoning=row["reasoning"] or "",
            market_state=row["market_state"] or "",
            timeframe_alignment=json.loads(row["timeframe_alignment"] or "{}"),
            technical_snapshot=json.loads(row["technical_snapshot"] or "{}"),
            patterns_detected=json.loads(row["patterns_detected"] or "[]"),
            entry_price=row["entry_price"] or 0.0,
            exit_price=row["exit_price"],
            pnl_percent=row["pnl_percent"],
            hour_of_day=row["hour_of_day"] or 0,
            day_of_week=row["day_of_week"] or 0,
            consecutive_losses=row["consecutive_losses"] or 0,
            is_winner=row["is_winner"],
        )
```

**Step 4: 更新 __init__.py**

```python
# src/ai_trader/memory/__init__.py
"""AI 记忆系统"""

from .models import TradeMemoryEntry, DistilledRule, RuleStatus
from .collector import TradeMemoryCollector

__all__ = ["TradeMemoryEntry", "DistilledRule", "RuleStatus", "TradeMemoryCollector"]
```

**Step 5: 运行测试**

```bash
pytest tests/memory/test_collector.py -v
```
Expected: PASS

**Step 6: 提交**

```bash
git add src/ai_trader/memory/ tests/memory/
git commit -m "feat(memory): add trade memory collector"
```

---

## Phase 3: 复盘引擎

### Task 3.1: 实现复盘触发器

**Files:**
- Create: `src/ai_trader/reflection/__init__.py`
- Create: `src/ai_trader/reflection/trigger.py`
- Create: `tests/reflection/__init__.py`
- Create: `tests/reflection/test_trigger.py`

**Step 1: 创建目录**

```bash
mkdir -p src/ai_trader/reflection tests/reflection
touch src/ai_trader/reflection/__init__.py tests/reflection/__init__.py
```

**Step 2: 写测试**

```python
# tests/reflection/test_trigger.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from ai_trader.reflection.trigger import ReflectionTrigger


class TestReflectionTrigger:
    @pytest.fixture
    def mock_collector(self):
        collector = AsyncMock()
        return collector

    @pytest.fixture
    def mock_engine(self):
        engine = AsyncMock()
        engine.run_reflection = AsyncMock(return_value={"summary": "test"})
        return engine

    @pytest.fixture
    def trigger(self, mock_collector, mock_engine):
        return ReflectionTrigger(
            collector=mock_collector,
            engine=mock_engine,
            threshold=10,
        )

    @pytest.mark.asyncio
    async def test_no_trigger_below_threshold(self, trigger, mock_collector):
        mock_collector.get_count_since_last_reflection = AsyncMock(return_value=5)

        result = await trigger.check_and_run()

        assert result is None

    @pytest.mark.asyncio
    async def test_trigger_at_threshold(self, trigger, mock_collector, mock_engine):
        mock_collector.get_count_since_last_reflection = AsyncMock(return_value=10)
        mock_collector.get_recent = AsyncMock(return_value=[MagicMock()] * 10)

        result = await trigger.check_and_run()

        assert result is not None
        mock_engine.run_reflection.assert_called_once()
```

**Step 3: 运行测试验证失败**

```bash
pytest tests/reflection/test_trigger.py -v
```
Expected: FAIL

**Step 4: 实现触发器**

```python
# src/ai_trader/reflection/trigger.py
"""复盘触发器"""

from typing import Optional
from ..memory.collector import TradeMemoryCollector
from ..utils.logger import logger


class ReflectionTrigger:
    """复盘触发器 - 按交易数量触发"""

    def __init__(
        self,
        collector: TradeMemoryCollector,
        engine,  # ReflectionEngine
        threshold: int = 10,
    ):
        self.collector = collector
        self.engine = engine
        self.threshold = threshold

    async def check_and_run(self) -> Optional[dict]:
        """检查是否需要触发复盘

        Returns:
            复盘结果（如果触发），否则 None
        """
        count = await self.collector.get_count_since_last_reflection()

        if count < self.threshold:
            logger.debug(f"复盘未触发: {count}/{self.threshold} 笔交易")
            return None

        logger.info(f"触发复盘: 已累计 {count} 笔交易")

        # 获取需要分析的交易
        memories = await self.collector.get_recent(limit=count)

        # 运行复盘
        result = await self.engine.run_reflection(memories)

        return result
```

**Step 5: 运行测试**

```bash
pytest tests/reflection/test_trigger.py -v
```
Expected: PASS

**Step 6: 提交**

```bash
git add src/ai_trader/reflection/ tests/reflection/
git commit -m "feat(reflection): add reflection trigger"
```

---

### Task 3.2: 实现复盘引擎

**Files:**
- Create: `src/ai_trader/reflection/engine.py`
- Create: `src/ai_trader/reflection/prompts.py`
- Create: `tests/reflection/test_engine.py`

**Step 1: 写测试**

```python
# tests/reflection/test_engine.py
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from ai_trader.reflection.engine import ReflectionEngine
from ai_trader.memory.models import TradeMemoryEntry


class TestReflectionEngine:
    @pytest.fixture
    def mock_llm(self):
        llm = AsyncMock()
        llm.generate = AsyncMock(return_value="""{
            "summary": "整体表现良好，趋势市胜率较高",
            "insights": [
                {"dimension": "市况", "finding": "趋势市胜率70%", "confidence": 0.8}
            ],
            "candidate_rules": [
                {
                    "condition": {"market_state": "ranging"},
                    "recommendation": {"confidence_threshold": "+10"},
                    "reasoning": "震荡市需提高门槛"
                }
            ],
            "parameter_suggestions": {
                "confidence_threshold": {"new_value": 70, "reasoning": "提升整体胜率"}
            }
        }""")
        return llm

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        db.fetchval = AsyncMock(return_value="reflection_001")
        return db

    @pytest.fixture
    def engine(self, mock_llm, mock_db):
        return ReflectionEngine(llm_client=mock_llm, db=mock_db)

    @pytest.fixture
    def sample_memories(self):
        return [
            TradeMemoryEntry(
                trade_id=f"t{i}",
                timestamp=datetime.now(),
                symbol="BTCUSDT",
                action="close_long",
                confidence=75.0,
                leverage=5.0,
                reasoning="test",
                market_state="strong_trend",
                entry_price=50000.0,
                exit_price=51000.0,
                pnl_percent=2.0,
                is_winner=True,
            )
            for i in range(10)
        ]

    @pytest.mark.asyncio
    async def test_run_reflection(self, engine, sample_memories):
        result = await engine.run_reflection(sample_memories)

        assert "summary" in result
        assert "insights" in result
        assert "candidate_rules" in result

    @pytest.mark.asyncio
    async def test_parse_llm_response(self, engine):
        response = """{
            "summary": "test",
            "insights": [],
            "candidate_rules": [],
            "parameter_suggestions": {}
        }"""

        result = engine._parse_response(response)

        assert result["summary"] == "test"
```

**Step 2: 运行测试验证失败**

```bash
pytest tests/reflection/test_engine.py -v
```
Expected: FAIL

**Step 3: 实现 prompts**

```python
# src/ai_trader/reflection/prompts.py
"""复盘 Prompt 模板"""

REFLECTION_PROMPT = """你是交易策略分析师。分析以下 {n} 笔交易记录，从多个维度总结经验。

## 交易数据
{trade_data_json}

## 当前参数
{current_parameters}

## 分析维度要求

1. **绩效总览**：胜率、平均盈亏、最大回撤
2. **市况表现**：趋势市 vs 震荡市 vs 突破市的表现差异
3. **信号质量**：哪些技术信号组合更可靠，哪些容易误判
4. **时段分析**：不同时段的交易效果
5. **心理因素**：连亏后的决策质量是否下降

## 输出格式（严格 JSON）
{{
  "summary": "整体表现概述（1-2句话）",
  "insights": [
    {{"dimension": "维度名称", "finding": "发现内容", "confidence": 0.0-1.0}}
  ],
  "candidate_rules": [
    {{
      "condition": {{"market_state": "...", "indicator": "..."}},
      "recommendation": {{"param": "...", "adjustment": "..."}},
      "reasoning": "规则理由"
    }}
  ],
  "parameter_suggestions": {{
    "param_name": {{"new_value": 数值, "reasoning": "调整理由"}}
  }}
}}

只输出 JSON，不要其他内容。
"""
```

**Step 4: 实现引擎**

```python
# src/ai_trader/reflection/engine.py
"""复盘引擎"""

import json
from datetime import datetime
from typing import Optional
from uuid import uuid4

from .prompts import REFLECTION_PROMPT
from ..memory.models import TradeMemoryEntry
from ..optimization.parameter_registry import ParameterRegistry
from ..persistence.database import DatabaseManager
from ..utils.logger import logger


class ReflectionEngine:
    """复盘引擎 - LLM 驱动的交易分析"""

    def __init__(
        self,
        llm_client,
        db: DatabaseManager,
        parameter_registry: Optional[ParameterRegistry] = None,
    ):
        self.llm = llm_client
        self.db = db
        self.registry = parameter_registry or ParameterRegistry()

    async def run_reflection(
        self, memories: list[TradeMemoryEntry]
    ) -> dict:
        """运行复盘分析

        Args:
            memories: 待分析的交易记忆列表

        Returns:
            复盘结果
        """
        reflection_id = f"ref_{uuid4().hex[:8]}"
        logger.info(f"开始复盘: {reflection_id}, 分析 {len(memories)} 笔交易")

        # 构建 prompt
        prompt = self._build_prompt(memories)

        # 调用 LLM
        response = await self.llm.generate(prompt)

        # 解析结果
        result = self._parse_response(response)
        result["reflection_id"] = reflection_id
        result["trades_analyzed"] = len(memories)

        # 保存复盘记录
        await self._save_reflection(reflection_id, len(memories), result)

        logger.info(f"复盘完成: {reflection_id}")
        return result

    def _build_prompt(self, memories: list[TradeMemoryEntry]) -> str:
        """构建复盘 prompt"""
        trade_data = [m.to_dict() for m in memories]

        return REFLECTION_PROMPT.format(
            n=len(memories),
            trade_data_json=json.dumps(trade_data, indent=2, ensure_ascii=False),
            current_parameters=json.dumps(self.registry.to_dict(), indent=2),
        )

    def _parse_response(self, response: str) -> dict:
        """解析 LLM 响应"""
        try:
            # 尝试提取 JSON
            response = response.strip()
            if response.startswith("```"):
                lines = response.split("\n")
                response = "\n".join(lines[1:-1])

            return json.loads(response)
        except json.JSONDecodeError as e:
            logger.error(f"复盘响应解析失败: {e}")
            return {
                "summary": "解析失败",
                "insights": [],
                "candidate_rules": [],
                "parameter_suggestions": {},
            }

    async def _save_reflection(
        self, reflection_id: str, trades_analyzed: int, result: dict
    ) -> None:
        """保存复盘记录"""
        await self.db.execute(
            """
            INSERT INTO reflection_logs (
                reflection_id, triggered_at, trades_analyzed,
                summary, insights, candidate_rules, parameter_suggestions
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            reflection_id,
            datetime.now(),
            trades_analyzed,
            result.get("summary"),
            json.dumps(result.get("insights", [])),
            json.dumps(result.get("candidate_rules", [])),
            json.dumps(result.get("parameter_suggestions", {})),
        )
```

**Step 5: 更新 __init__.py**

```python
# src/ai_trader/reflection/__init__.py
"""复盘系统"""

from .trigger import ReflectionTrigger
from .engine import ReflectionEngine

__all__ = ["ReflectionTrigger", "ReflectionEngine"]
```

**Step 6: 运行测试**

```bash
pytest tests/reflection/test_engine.py -v
```
Expected: PASS

**Step 7: 提交**

```bash
git add src/ai_trader/reflection/ tests/reflection/
git commit -m "feat(reflection): add reflection engine with LLM analysis"
```

---

## Phase 4: 规则验证与影子运行

### Task 4.1: 实现规则验证器

**Files:**
- Create: `src/ai_trader/optimization/rule_validator.py`
- Create: `tests/optimization/test_rule_validator.py`

**Step 1: 写测试**

```python
# tests/optimization/test_rule_validator.py
import pytest
from datetime import datetime
from ai_trader.optimization.rule_validator import RuleValidator
from ai_trader.memory.models import TradeMemoryEntry


class TestRuleValidator:
    @pytest.fixture
    def validator(self):
        return RuleValidator()

    @pytest.fixture
    def sample_trades(self):
        # 创建 30 笔交易，其中震荡市 20 笔
        trades = []
        for i in range(30):
            is_ranging = i < 20
            # 震荡市使用高门槛胜率 75%，低门槛 45%
            is_winner = (i % 4 != 0) if is_ranging else (i % 3 != 0)

            trades.append(TradeMemoryEntry(
                trade_id=f"t{i}",
                timestamp=datetime.now(),
                symbol="BTCUSDT",
                action="close_long",
                confidence=55.0 if is_ranging else 70.0,
                leverage=5.0,
                reasoning="test",
                market_state="ranging" if is_ranging else "strong_trend",
                entry_price=50000.0,
                pnl_percent=2.0 if is_winner else -1.5,
                is_winner=is_winner,
            ))
        return trades

    def test_validate_with_sufficient_samples(self, validator, sample_trades):
        rule = {
            "condition": {"market_state": "ranging"},
            "recommendation": {"confidence_threshold": "+10"},
        }

        result = validator.validate(rule, sample_trades)

        assert "is_valid" in result
        assert "sample_size" in result
        assert result["sample_size"] >= 20

    def test_reject_insufficient_samples(self, validator):
        trades = [
            TradeMemoryEntry(
                trade_id="t1",
                timestamp=datetime.now(),
                symbol="BTCUSDT",
                action="close_long",
                confidence=70.0,
                leverage=5.0,
                reasoning="test",
                market_state="ranging",
                entry_price=50000.0,
                is_winner=True,
            )
        ] * 5  # 只有 5 笔

        rule = {"condition": {"market_state": "ranging"}, "recommendation": {}}

        result = validator.validate(rule, trades)

        assert result["is_valid"] is False
        assert "样本不足" in result["reason"]
```

**Step 2: 运行测试验证失败**

```bash
pytest tests/optimization/test_rule_validator.py -v
```
Expected: FAIL

**Step 3: 实现验证器**

```python
# src/ai_trader/optimization/rule_validator.py
"""规则统计验证器"""

from typing import Optional
from scipy import stats

from ..memory.models import TradeMemoryEntry, DistilledRule
from ..utils.logger import logger


class RuleValidator:
    """候选规则的统计验证器"""

    MIN_SAMPLE_SIZE = 20
    P_VALUE_THRESHOLD = 0.05
    MIN_WIN_RATE_IMPROVEMENT = 0.05

    def validate(
        self,
        rule: dict,
        history: list[TradeMemoryEntry],
    ) -> dict:
        """验证候选规则

        Args:
            rule: 候选规则（包含 condition 和 recommendation）
            history: 历史交易记录

        Returns:
            验证结果
        """
        condition = rule.get("condition", {})

        # 筛选符合条件的交易
        matched = [t for t in history if self._match_condition(t, condition)]

        if len(matched) < self.MIN_SAMPLE_SIZE:
            return {
                "is_valid": False,
                "reason": f"样本不足: {len(matched)}/{self.MIN_SAMPLE_SIZE}",
                "sample_size": len(matched),
            }

        # 计算胜率
        winners = [t for t in matched if t.is_winner]
        win_rate = len(winners) / len(matched)

        # 计算平均盈亏
        pnls = [t.pnl_percent for t in matched if t.pnl_percent is not None]
        avg_pnl = sum(pnls) / len(pnls) if pnls else 0

        # 基准对比（不符合条件的交易）
        baseline = [t for t in history if not self._match_condition(t, condition)]
        baseline_winners = [t for t in baseline if t.is_winner]
        baseline_win_rate = len(baseline_winners) / len(baseline) if baseline else 0

        # 统计检验
        p_value = self._chi_square_test(matched, baseline)

        is_valid = (
            p_value < self.P_VALUE_THRESHOLD
            and win_rate - baseline_win_rate >= self.MIN_WIN_RATE_IMPROVEMENT
        )

        result = {
            "is_valid": is_valid,
            "sample_size": len(matched),
            "win_rate": win_rate,
            "baseline_win_rate": baseline_win_rate,
            "avg_pnl": avg_pnl,
            "p_value": p_value,
            "improvement": win_rate - baseline_win_rate,
        }

        if not is_valid:
            if p_value >= self.P_VALUE_THRESHOLD:
                result["reason"] = f"统计不显著: p={p_value:.3f}"
            else:
                result["reason"] = f"提升不足: {(win_rate - baseline_win_rate)*100:.1f}%"

        logger.info(f"规则验证: valid={is_valid}, p={p_value:.3f}, win_rate={win_rate:.2%}")
        return result

    def _match_condition(self, trade: TradeMemoryEntry, condition: dict) -> bool:
        """检查交易是否符合规则条件"""
        for key, value in condition.items():
            if key == "market_state":
                if trade.market_state != value:
                    return False
            elif key == "hour_range":
                if not (value[0] <= trade.hour_of_day <= value[1]):
                    return False
            elif key == "consecutive_losses_gt":
                if trade.consecutive_losses <= value:
                    return False
        return True

    def _chi_square_test(
        self,
        matched: list[TradeMemoryEntry],
        baseline: list[TradeMemoryEntry],
    ) -> float:
        """卡方检验"""
        if not baseline:
            return 1.0

        matched_wins = sum(1 for t in matched if t.is_winner)
        matched_losses = len(matched) - matched_wins

        baseline_wins = sum(1 for t in baseline if t.is_winner)
        baseline_losses = len(baseline) - baseline_wins

        # 2x2 contingency table
        table = [
            [matched_wins, matched_losses],
            [baseline_wins, baseline_losses],
        ]

        try:
            _, p_value, _, _ = stats.chi2_contingency(table)
            return p_value
        except ValueError:
            return 1.0

    def create_distilled_rule(
        self, rule: dict, validation_result: dict
    ) -> Optional[DistilledRule]:
        """创建已验证的规则"""
        if not validation_result.get("is_valid"):
            return None

        from uuid import uuid4

        return DistilledRule(
            rule_id=f"rule_{uuid4().hex[:8]}",
            condition=rule["condition"],
            recommendation=rule["recommendation"],
            reasoning=rule.get("reasoning", ""),
            sample_size=validation_result["sample_size"],
            win_rate=validation_result["win_rate"],
            avg_pnl=validation_result["avg_pnl"],
            p_value=validation_result["p_value"],
        )
```

**Step 4: 更新 __init__.py**

```python
# src/ai_trader/optimization/__init__.py
"""策略优化系统"""

from .parameter_registry import AdjustableParameter, ParameterRegistry
from .rule_validator import RuleValidator

__all__ = ["AdjustableParameter", "ParameterRegistry", "RuleValidator"]
```

**Step 5: 运行测试**

```bash
pytest tests/optimization/test_rule_validator.py -v
```
Expected: PASS

**Step 6: 提交**

```bash
git add src/ai_trader/optimization/ tests/optimization/
git commit -m "feat(optimization): add statistical rule validator"
```

---

### Task 4.2: 实现影子运行器

**Files:**
- Create: `src/ai_trader/optimization/shadow_runner.py`
- Create: `tests/optimization/test_shadow_runner.py`

**Step 1: 写测试**

```python
# tests/optimization/test_shadow_runner.py
import pytest
from unittest.mock import AsyncMock
from ai_trader.optimization.shadow_runner import ShadowRunner


class TestShadowRunner:
    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        db.fetchval = AsyncMock(return_value="run_001")
        return db

    @pytest.fixture
    def runner(self, mock_db):
        return ShadowRunner(mock_db)

    @pytest.mark.asyncio
    async def test_start_shadow_run(self, runner):
        current = {"confidence_threshold": 60.0}
        candidate = {"confidence_threshold": 70.0}

        run_id = await runner.start(current, candidate)

        assert run_id is not None
        assert runner.is_running

    @pytest.mark.asyncio
    async def test_record_results(self, runner):
        await runner.start({"a": 1}, {"a": 2})

        # 记录实盘结果
        runner.record_current_result(is_winner=True, pnl=0.02)
        runner.record_current_result(is_winner=False, pnl=-0.01)

        # 记录影子结果
        runner.record_candidate_result(is_winner=True, pnl=0.025)
        runner.record_candidate_result(is_winner=True, pnl=0.015)

        stats = runner.get_stats()

        assert stats["current_trades"] == 2
        assert stats["candidate_trades"] == 2
        assert stats["candidate_win_rate"] == 1.0

    @pytest.mark.asyncio
    async def test_evaluate_should_switch(self, runner):
        await runner.start({"a": 1}, {"a": 2})

        # 模拟影子胜率更高
        for _ in range(5):
            runner.record_current_result(is_winner=True, pnl=0.01)
            runner.record_current_result(is_winner=False, pnl=-0.01)

        for _ in range(10):
            runner.record_candidate_result(is_winner=True, pnl=0.02)

        result = runner.evaluate()

        assert result["should_switch"] is True
```

**Step 2: 运行测试验证失败**

```bash
pytest tests/optimization/test_shadow_runner.py -v
```
Expected: FAIL

**Step 3: 实现影子运行器**

```python
# src/ai_trader/optimization/shadow_runner.py
"""影子运行器 - 参数验证"""

import json
from datetime import datetime
from uuid import uuid4
from dataclasses import dataclass, field

from ..persistence.database import DatabaseManager
from ..utils.logger import logger


@dataclass
class ShadowStats:
    """影子运行统计"""
    trades: int = 0
    wins: int = 0
    total_pnl: float = 0.0

    @property
    def win_rate(self) -> float:
        return self.wins / self.trades if self.trades > 0 else 0.0

    @property
    def avg_pnl(self) -> float:
        return self.total_pnl / self.trades if self.trades > 0 else 0.0


class ShadowRunner:
    """影子运行器"""

    MIN_TRADES = 10
    WIN_RATE_THRESHOLD = 0.03
    PNL_THRESHOLD = 0.005

    def __init__(self, db: DatabaseManager):
        self.db = db
        self._run_id: str | None = None
        self._current_params: dict = {}
        self._candidate_params: dict = {}
        self._current_stats = ShadowStats()
        self._candidate_stats = ShadowStats()
        self._started_at: datetime | None = None

    @property
    def is_running(self) -> bool:
        return self._run_id is not None

    async def start(self, current_params: dict, candidate_params: dict) -> str:
        """启动影子运行

        Args:
            current_params: 当前参数
            candidate_params: 候选参数

        Returns:
            运行 ID
        """
        self._run_id = f"shadow_{uuid4().hex[:8]}"
        self._current_params = current_params
        self._candidate_params = candidate_params
        self._current_stats = ShadowStats()
        self._candidate_stats = ShadowStats()
        self._started_at = datetime.now()

        await self.db.execute(
            """
            INSERT INTO shadow_runs (
                run_id, started_at, current_params, candidate_params, status
            ) VALUES ($1, $2, $3, $4, 'running')
            """,
            self._run_id,
            self._started_at,
            json.dumps(current_params),
            json.dumps(candidate_params),
        )

        logger.info(f"影子运行启动: {self._run_id}")
        return self._run_id

    def record_current_result(self, is_winner: bool, pnl: float) -> None:
        """记录实盘结果"""
        self._current_stats.trades += 1
        if is_winner:
            self._current_stats.wins += 1
        self._current_stats.total_pnl += pnl

    def record_candidate_result(self, is_winner: bool, pnl: float) -> None:
        """记录影子（候选参数）结果"""
        self._candidate_stats.trades += 1
        if is_winner:
            self._candidate_stats.wins += 1
        self._candidate_stats.total_pnl += pnl

    def get_stats(self) -> dict:
        """获取当前统计"""
        return {
            "current_trades": self._current_stats.trades,
            "current_win_rate": self._current_stats.win_rate,
            "current_avg_pnl": self._current_stats.avg_pnl,
            "candidate_trades": self._candidate_stats.trades,
            "candidate_win_rate": self._candidate_stats.win_rate,
            "candidate_avg_pnl": self._candidate_stats.avg_pnl,
        }

    def evaluate(self) -> dict:
        """评估是否应该切换参数"""
        if self._candidate_stats.trades < self.MIN_TRADES:
            return {
                "should_switch": False,
                "reason": f"样本不足: {self._candidate_stats.trades}/{self.MIN_TRADES}",
            }

        win_rate_improvement = (
            self._candidate_stats.win_rate - self._current_stats.win_rate
        )
        pnl_improvement = (
            self._candidate_stats.avg_pnl - self._current_stats.avg_pnl
        )

        should_switch = (
            win_rate_improvement >= self.WIN_RATE_THRESHOLD
            and pnl_improvement >= self.PNL_THRESHOLD
        )

        return {
            "should_switch": should_switch,
            "win_rate_improvement": win_rate_improvement,
            "pnl_improvement": pnl_improvement,
            "stats": self.get_stats(),
        }

    async def complete(self, switched: bool, conclusion: str = "") -> None:
        """完成影子运行"""
        if not self._run_id:
            return

        stats = self.get_stats()

        await self.db.execute(
            """
            UPDATE shadow_runs SET
                ended_at = $1,
                current_trades = $2,
                candidate_trades = $3,
                current_win_rate = $4,
                candidate_win_rate = $5,
                current_avg_pnl = $6,
                candidate_avg_pnl = $7,
                status = $8,
                conclusion = $9
            WHERE run_id = $10
            """,
            datetime.now(),
            stats["current_trades"],
            stats["candidate_trades"],
            stats["current_win_rate"],
            stats["candidate_win_rate"],
            stats["current_avg_pnl"],
            stats["candidate_avg_pnl"],
            "switched" if switched else "rejected",
            conclusion,
            self._run_id,
        )

        logger.info(f"影子运行完成: {self._run_id}, switched={switched}")
        self._run_id = None
```

**Step 4: 更新 __init__.py**

```python
# src/ai_trader/optimization/__init__.py
"""策略优化系统"""

from .parameter_registry import AdjustableParameter, ParameterRegistry
from .rule_validator import RuleValidator
from .shadow_runner import ShadowRunner

__all__ = [
    "AdjustableParameter",
    "ParameterRegistry",
    "RuleValidator",
    "ShadowRunner",
]
```

**Step 5: 运行测试**

```bash
pytest tests/optimization/test_shadow_runner.py -v
```
Expected: PASS

**Step 6: 提交**

```bash
git add src/ai_trader/optimization/ tests/optimization/
git commit -m "feat(optimization): add shadow runner for parameter validation"
```

---

## Phase 5: 系统集成

### Task 5.1: 扩展配置

**Files:**
- Modify: `src/ai_trader/config.py`

**Step 1: 添加记忆系统配置**

在 `TradingConfig` 类中添加：

```python
# 在 TradingConfig 类中添加

# ============= 记忆与自优化配置 =============
reflection_trade_count: int = Field(
    default=10, description="触发复盘的交易数量"
)
short_term_memory_size: int = Field(
    default=100, description="短期记忆保留笔数"
)
enable_auto_optimization: bool = Field(
    default=False, description="启用自动参数优化"
)
shadow_run_min_trades: int = Field(
    default=10, description="影子运行最少交易数"
)
```

**Step 2: 提交**

```bash
git add src/ai_trader/config.py
git commit -m "feat(config): add memory and optimization settings"
```

---

### Task 5.2: 集成到调度器

**Files:**
- Modify: `src/ai_trader/scheduler.py`

**Step 1: 修改调度器**

在 `Scheduler.__init__` 中添加：

```python
# 新增导入
from .memory import TradeMemoryCollector
from .reflection import ReflectionTrigger, ReflectionEngine
from .optimization import ParameterRegistry, ShadowRunner

# 在 __init__ 中添加
self.memory_collector: Optional[TradeMemoryCollector] = None
self.reflection_trigger: Optional[ReflectionTrigger] = None
self.shadow_runner: Optional[ShadowRunner] = None
self.parameter_registry = ParameterRegistry()
```

在 `_init_persistence` 中添加：

```python
# 初始化记忆系统
if config.enable_auto_optimization:
    self.memory_collector = TradeMemoryCollector(self.db_manager)
    reflection_engine = ReflectionEngine(
        self.llm, self.db_manager, self.parameter_registry
    )
    self.reflection_trigger = ReflectionTrigger(
        self.memory_collector,
        reflection_engine,
        threshold=config.reflection_trade_count,
    )
    self.shadow_runner = ShadowRunner(self.db_manager)
    logger.info("记忆与自优化系统已初始化")
```

在 `_persist_position_change` 中，平仓后添加：

```python
# 收集交易记忆并检查复盘
if self.memory_collector and action in ["close_long", "close_short"]:
    await self.memory_collector.collect(
        position=position,
        result=result,  # 需要构造
        decision=decision,
        technical=tech,
        market_state=market_state,
    )
    if self.reflection_trigger:
        await self.reflection_trigger.check_and_run()
```

**Step 2: 提交**

```bash
git add src/ai_trader/scheduler.py
git commit -m "feat(scheduler): integrate memory and reflection system"
```

---

## 测试验证

### Task 6.1: 运行完整测试

```bash
pytest tests/memory/ tests/optimization/ tests/reflection/ -v
```

### Task 6.2: 集成测试

创建集成测试验证完整流程。

---

**Plan complete and saved to `docs/plans/2026-02-01-ai-memory-implementation-plan.md`. Two execution options:**

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

**Which approach?**
