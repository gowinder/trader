# 市场事件驱动 LLM 智能触发 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在保留 15 分钟定时 LLM 调用的基础上，增加纯程序化事件检测层，检测到市场异常时主动触发 LLM 调用。

**Architecture:** 新增 `events` 模块，包含 EventDetector 主类、7 个独立检测器、CooldownManager。改造 Scheduler 主循环从 sleep(decision_interval) 改为 sleep(30s) + 事件检测 + 计时器。HybridDecisionEngine 的 `analyze_and_decide` 增加 `trigger_context` 参数注入 prompt。

**Tech Stack:** Python 3.11+, Pydantic, asyncio, Redis (配置存储)

---

## Task 1: 数据模型 — TriggerEvent + EventConfig

**Files:**
- Create: `src/ai_trader/events/__init__.py`
- Create: `src/ai_trader/events/models.py`
- Create: `src/ai_trader/events/config.py`
- Test: `tests/events/__init__.py`
- Test: `tests/events/test_models.py`

**Step 1: Write the failing test**

```python
# tests/events/__init__.py
# (empty)

# tests/events/test_models.py
from datetime import datetime, timezone
from ai_trader.events.models import TriggerEvent


class TestTriggerEvent:
    def test_create_trigger_event(self):
        event = TriggerEvent(
            event_type="price_surge",
            description="5分钟内跌幅 2.1 ATR",
            severity="high",
            key_data={"price_change_pct": -3.2, "atr_ratio": 2.1},
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        assert event.event_type == "price_surge"
        assert event.severity == "high"
        assert event.key_data["atr_ratio"] == 2.1

    def test_trigger_event_format_for_prompt(self):
        event = TriggerEvent(
            event_type="price_surge",
            description="5分钟内跌幅 2.1 ATR",
            severity="high",
            key_data={"price_change_pct": -3.2, "atr_ratio": 2.1},
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        text = event.format_for_prompt()
        assert "price_surge" in text
        assert "high" in text
        assert "2.1 ATR" in text
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/gowinder/code/gowinder/trader && python -m pytest tests/events/test_models.py -v`
Expected: FAIL — ModuleNotFoundError

**Step 3: Write minimal implementation**

```python
# src/ai_trader/events/__init__.py
from .models import TriggerEvent
from .config import STRATEGY_EVENT_DEFAULTS, DEFAULT_EVENT_TRIGGER_CONFIG

__all__ = ["TriggerEvent", "STRATEGY_EVENT_DEFAULTS", "DEFAULT_EVENT_TRIGGER_CONFIG"]


# src/ai_trader/events/models.py
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class TriggerEvent:
    """传递给 LLM 的触发上下文"""
    event_type: str
    description: str
    severity: str  # "high" / "medium" / "low"
    key_data: dict
    timestamp: datetime

    def format_for_prompt(self) -> str:
        """格式化为 LLM prompt 片段"""
        lines = [f"{self.event_type} (severity: {self.severity})"]
        lines.append(f"    - {self.description}")
        for k, v in self.key_data.items():
            if isinstance(v, float):
                lines.append(f"    - {k}: {v:.4f}")
            else:
                lines.append(f"    - {k}: {v}")
        return "\n".join(lines)


# src/ai_trader/events/config.py
"""事件触发器配置常量"""

STRATEGY_EVENT_DEFAULTS: dict[str, list[str]] = {
    "trend_following": ["price_surge", "macd_cross", "market_state_change", "position_pnl"],
    "mean_reversion": ["price_surge", "rsi_extreme", "bollinger_break", "market_state_change", "position_pnl"],
    "breakout": ["price_surge", "volume_spike", "bollinger_break", "market_state_change", "position_pnl"],
}

DEFAULT_EVENT_TRIGGER_CONFIG: dict = {
    "enabled": True,
    "scan_interval_seconds": 30,
    "global_cooldown_seconds": 300,
    "per_event_cooldown_seconds": 600,
    "reset_decision_timer": True,
    "events": {
        "price_surge": {
            "enabled": True,
            "atr_multiplier": 1.5,
            "lookback_seconds": 300,
        },
        "volume_spike": {
            "enabled": True,
            "volume_multiplier": 2.5,
        },
        "rsi_extreme": {
            "enabled": True,
            "upper_threshold": 75,
            "lower_threshold": 25,
        },
        "macd_cross": {
            "enabled": True,
        },
        "bollinger_break": {
            "enabled": True,
        },
        "market_state_change": {
            "enabled": True,
        },
        "position_pnl": {
            "enabled": True,
            "profit_threshold_percent": 3.0,
            "loss_threshold_percent": -2.0,
        },
    },
}
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/gowinder/code/gowinder/trader && python -m pytest tests/events/test_models.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/ai_trader/events/ tests/events/
git commit -m "feat(events): add TriggerEvent model and event trigger config"
```

---

## Task 2: CooldownManager

**Files:**
- Create: `src/ai_trader/events/cooldown.py`
- Test: `tests/events/test_cooldown.py`

**Step 1: Write the failing test**

```python
# tests/events/test_cooldown.py
import time
from ai_trader.events.cooldown import CooldownManager


class TestCooldownManager:
    def test_can_trigger_initially(self):
        mgr = CooldownManager(global_cooldown=300, per_event_cooldown=600)
        assert mgr.can_trigger("price_surge") is True

    def test_global_cooldown_blocks(self):
        mgr = CooldownManager(global_cooldown=300, per_event_cooldown=600)
        mgr.record_trigger("price_surge")
        # 全局冷却中，任何事件都不能触发
        assert mgr.can_trigger("volume_spike") is False

    def test_per_event_cooldown_blocks(self):
        mgr = CooldownManager(global_cooldown=0, per_event_cooldown=600)
        mgr.record_trigger("price_surge")
        # 同类事件被冷却
        assert mgr.can_trigger("price_surge") is False
        # 不同事件不受影响
        assert mgr.can_trigger("volume_spike") is True

    def test_cooldown_expires(self):
        mgr = CooldownManager(global_cooldown=0, per_event_cooldown=0)
        mgr.record_trigger("price_surge")
        assert mgr.can_trigger("price_surge") is True

    def test_reset(self):
        mgr = CooldownManager(global_cooldown=300, per_event_cooldown=600)
        mgr.record_trigger("price_surge")
        mgr.reset()
        assert mgr.can_trigger("price_surge") is True
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/gowinder/code/gowinder/trader && python -m pytest tests/events/test_cooldown.py -v`
Expected: FAIL — ModuleNotFoundError

**Step 3: Write minimal implementation**

```python
# src/ai_trader/events/cooldown.py
"""冷却时间管理器"""

import time


class CooldownManager:
    """管理事件触发的冷却时间

    - global_cooldown: 任意事件触发后，所有事件的全局冷却（秒）
    - per_event_cooldown: 单个事件类型的独立冷却（秒）
    """

    def __init__(self, global_cooldown: int = 300, per_event_cooldown: int = 600):
        self.global_cooldown = global_cooldown
        self.per_event_cooldown = per_event_cooldown
        self._last_global_trigger: float = 0.0
        self._last_event_triggers: dict[str, float] = {}

    def can_trigger(self, event_type: str) -> bool:
        """检查指定事件是否可以触发（未在冷却中）"""
        now = time.monotonic()
        # 全局冷却检查
        if self.global_cooldown > 0 and (now - self._last_global_trigger) < self.global_cooldown:
            return False
        # 单事件冷却检查
        last = self._last_event_triggers.get(event_type, 0.0)
        if self.per_event_cooldown > 0 and (now - last) < self.per_event_cooldown:
            return False
        return True

    def record_trigger(self, event_type: str) -> None:
        """记录事件触发时间"""
        now = time.monotonic()
        self._last_global_trigger = now
        self._last_event_triggers[event_type] = now

    def reset(self) -> None:
        """重置所有冷却"""
        self._last_global_trigger = 0.0
        self._last_event_triggers.clear()
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/gowinder/code/gowinder/trader && python -m pytest tests/events/test_cooldown.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/ai_trader/events/cooldown.py tests/events/test_cooldown.py
git commit -m "feat(events): add CooldownManager with global and per-event cooldown"
```

---

## Task 3: BaseDetector 接口 + 7 个检测器

**Files:**
- Create: `src/ai_trader/events/detectors/__init__.py`
- Create: `src/ai_trader/events/detectors/base.py`
- Create: `src/ai_trader/events/detectors/price_surge.py`
- Create: `src/ai_trader/events/detectors/volume_spike.py`
- Create: `src/ai_trader/events/detectors/rsi_extreme.py`
- Create: `src/ai_trader/events/detectors/macd_cross.py`
- Create: `src/ai_trader/events/detectors/bollinger_break.py`
- Create: `src/ai_trader/events/detectors/market_state_change.py`
- Create: `src/ai_trader/events/detectors/position_pnl.py`
- Test: `tests/events/test_detectors.py`

**Step 1: Write the failing tests**

```python
# tests/events/test_detectors.py
"""事件检测器测试 — 使用真实计算逻辑，不 mock 底层"""

import pytest
from datetime import datetime, timezone
from ai_trader.events.detectors.price_surge import PriceSurgeDetector
from ai_trader.events.detectors.volume_spike import VolumeSpikeDetector
from ai_trader.events.detectors.rsi_extreme import RSIExtremeDetector
from ai_trader.events.detectors.macd_cross import MACDCrossDetector
from ai_trader.events.detectors.bollinger_break import BollingerBreakDetector
from ai_trader.events.detectors.market_state_change import MarketStateChangeDetector
from ai_trader.events.detectors.position_pnl import PositionPnLDetector
from ai_trader.models.market import Indicators, MarketData, Kline


def _make_indicators(**overrides) -> Indicators:
    defaults = dict(
        ma7=100.0, ma25=100.0, ma99=100.0,
        rsi=50.0, macd=0.0, macd_signal=0.0, macd_histogram=0.0,
        boll_upper=110.0, boll_middle=100.0, boll_lower=90.0, atr=2.0,
    )
    defaults.update(overrides)
    return Indicators(**defaults)


def _make_kline(close: float, volume: float = 1000.0, ts_offset: int = 0) -> Kline:
    return Kline(
        timestamp=1700000000 + ts_offset * 60,
        open=close, high=close + 1, low=close - 1,
        close=close, volume=volume,
    )


def _make_market_data(
    current_price: float = 100.0,
    indicators: Indicators | None = None,
    klines: list[Kline] | None = None,
) -> MarketData:
    if indicators is None:
        indicators = _make_indicators()
    if klines is None:
        klines = [_make_kline(100.0, ts_offset=i) for i in range(150)]
    return MarketData(
        symbol="BTC/USDT:USDT",
        current_price=current_price,
        klines=klines,
        interval="15m",
        indicators=indicators,
        high_24h=105.0, low_24h=95.0,
        change_24h=2.0, volume_24h=50000.0,
    )


class TestPriceSurgeDetector:
    def test_no_trigger_normal_price(self):
        det = PriceSurgeDetector(atr_multiplier=1.5, lookback_seconds=300)
        # 价格平稳，最近K线 close 都是 100
        md = _make_market_data(current_price=100.0)
        result = det.check(md, md.indicators, None)
        assert result is None

    def test_trigger_on_price_drop(self):
        det = PriceSurgeDetector(atr_multiplier=1.5, lookback_seconds=300)
        # ATR=2, 1.5x=3, 价格从100跌到96（跌4 > 3）
        klines = [_make_kline(100.0, ts_offset=i) for i in range(145)]
        # 最近5根 close 逐步下跌
        for i in range(5):
            klines.append(_make_kline(100.0 - (i + 1) * 0.8, ts_offset=145 + i))
        md = _make_market_data(current_price=96.0, klines=klines)
        result = det.check(md, md.indicators, None)
        assert result is not None
        assert result.event_type == "price_surge"
        assert result.severity == "high"


class TestVolumeSpikeDetector:
    def test_no_trigger_normal_volume(self):
        det = VolumeSpikeDetector(volume_multiplier=2.5)
        md = _make_market_data()
        result = det.check(md, md.indicators, None)
        assert result is None

    def test_trigger_on_volume_spike(self):
        det = VolumeSpikeDetector(volume_multiplier=2.5)
        klines = [_make_kline(100.0, volume=1000.0, ts_offset=i) for i in range(148)]
        # 最近2根成交量突增
        klines.append(_make_kline(100.0, volume=3000.0, ts_offset=148))
        klines.append(_make_kline(100.0, volume=3500.0, ts_offset=149))
        md = _make_market_data(klines=klines)
        result = det.check(md, md.indicators, None)
        assert result is not None
        assert result.event_type == "volume_spike"


class TestRSIExtremeDetector:
    def test_no_trigger_normal_rsi(self):
        det = RSIExtremeDetector(upper_threshold=75, lower_threshold=25)
        indicators = _make_indicators(rsi=50.0)
        md = _make_market_data(indicators=indicators)
        result = det.check(md, indicators, None)
        assert result is None

    def test_trigger_oversold(self):
        det = RSIExtremeDetector(upper_threshold=75, lower_threshold=25)
        indicators = _make_indicators(rsi=20.0)
        md = _make_market_data(indicators=indicators)
        result = det.check(md, indicators, None)
        assert result is not None
        assert result.event_type == "rsi_extreme"
        assert "oversold" in result.description.lower() or "超卖" in result.description

    def test_trigger_overbought(self):
        det = RSIExtremeDetector(upper_threshold=75, lower_threshold=25)
        indicators = _make_indicators(rsi=80.0)
        md = _make_market_data(indicators=indicators)
        result = det.check(md, indicators, None)
        assert result is not None


class TestMACDCrossDetector:
    def test_no_trigger_no_cross(self):
        det = MACDCrossDetector()
        # 初始状态，没有前一次数据，不应触发
        indicators = _make_indicators(macd=1.0, macd_signal=0.5)
        md = _make_market_data(indicators=indicators)
        result = det.check(md, indicators, None)
        assert result is None

    def test_trigger_golden_cross(self):
        det = MACDCrossDetector()
        # 先记录一次 MACD < signal
        ind1 = _make_indicators(macd=-0.5, macd_signal=0.5)
        md1 = _make_market_data(indicators=ind1)
        det.check(md1, ind1, None)
        # 再来一次 MACD > signal → 金叉
        ind2 = _make_indicators(macd=0.8, macd_signal=0.5)
        md2 = _make_market_data(indicators=ind2)
        result = det.check(md2, ind2, None)
        assert result is not None
        assert result.event_type == "macd_cross"


class TestBollingerBreakDetector:
    def test_no_trigger_within_bands(self):
        det = BollingerBreakDetector()
        indicators = _make_indicators(boll_upper=110.0, boll_lower=90.0)
        md = _make_market_data(current_price=100.0, indicators=indicators)
        result = det.check(md, indicators, None)
        assert result is None

    def test_trigger_upper_break(self):
        det = BollingerBreakDetector()
        indicators = _make_indicators(boll_upper=110.0, boll_lower=90.0)
        md = _make_market_data(current_price=112.0, indicators=indicators)
        result = det.check(md, indicators, None)
        assert result is not None
        assert result.event_type == "bollinger_break"

    def test_trigger_lower_break(self):
        det = BollingerBreakDetector()
        indicators = _make_indicators(boll_upper=110.0, boll_lower=90.0)
        md = _make_market_data(current_price=88.0, indicators=indicators)
        result = det.check(md, indicators, None)
        assert result is not None


class TestMarketStateChangeDetector:
    def test_no_trigger_first_call(self):
        det = MarketStateChangeDetector()
        result = det.check_state_change("strong_trend")
        assert result is None

    def test_no_trigger_same_state(self):
        det = MarketStateChangeDetector()
        det.check_state_change("sideways")
        result = det.check_state_change("sideways")
        assert result is None

    def test_trigger_on_state_change(self):
        det = MarketStateChangeDetector()
        det.check_state_change("sideways")
        result = det.check_state_change("breakout")
        assert result is not None
        assert result.event_type == "market_state_change"
        assert "sideways" in result.description
        assert "breakout" in result.description


class TestPositionPnLDetector:
    def test_no_trigger_no_position(self):
        det = PositionPnLDetector(profit_threshold=3.0, loss_threshold=-2.0)
        md = _make_market_data()
        result = det.check(md, md.indicators, None)
        assert result is None

    def test_trigger_profit_threshold(self):
        det = PositionPnLDetector(profit_threshold=3.0, loss_threshold=-2.0)
        md = _make_market_data()
        # 模拟持仓: roi=4.0 > 3.0 阈值
        from unittest.mock import MagicMock
        position = MagicMock()
        position.size = 1.0
        position.roi = 4.0
        position.side = "long"
        position.unrealized_pnl = 40.0
        result = det.check(md, md.indicators, position)
        assert result is not None
        assert result.event_type == "position_pnl"

    def test_trigger_loss_threshold(self):
        det = PositionPnLDetector(profit_threshold=3.0, loss_threshold=-2.0)
        md = _make_market_data()
        from unittest.mock import MagicMock
        position = MagicMock()
        position.size = 1.0
        position.roi = -3.0
        position.side = "long"
        position.unrealized_pnl = -30.0
        result = det.check(md, md.indicators, position)
        assert result is not None
        assert result.severity == "high"
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/gowinder/code/gowinder/trader && python -m pytest tests/events/test_detectors.py -v`
Expected: FAIL — ModuleNotFoundError

**Step 3: Write minimal implementation**

```python
# src/ai_trader/events/detectors/__init__.py
from .price_surge import PriceSurgeDetector
from .volume_spike import VolumeSpikeDetector
from .rsi_extreme import RSIExtremeDetector
from .macd_cross import MACDCrossDetector
from .bollinger_break import BollingerBreakDetector
from .market_state_change import MarketStateChangeDetector
from .position_pnl import PositionPnLDetector

__all__ = [
    "PriceSurgeDetector", "VolumeSpikeDetector", "RSIExtremeDetector",
    "MACDCrossDetector", "BollingerBreakDetector",
    "MarketStateChangeDetector", "PositionPnLDetector",
]


# src/ai_trader/events/detectors/base.py
from abc import ABC, abstractmethod
from typing import Optional
from ..models import TriggerEvent
from ...models.market import MarketData, Indicators
from ...models.order import Position


class BaseDetector(ABC):
    """事件检测器基类"""

    @abstractmethod
    def check(
        self,
        market_data: MarketData,
        indicators: Indicators,
        position: Optional[Position],
    ) -> Optional[TriggerEvent]:
        """检测事件，返回 TriggerEvent 或 None"""
        ...


# src/ai_trader/events/detectors/price_surge.py
from datetime import datetime, timezone
from typing import Optional
from .base import BaseDetector
from ..models import TriggerEvent
from ...models.market import MarketData, Indicators
from ...models.order import Position


class PriceSurgeDetector(BaseDetector):
    """价格急涨急跌检测器：短时间内价格变动超过 ATR 的 N 倍"""

    def __init__(self, atr_multiplier: float = 1.5, lookback_seconds: int = 300):
        self.atr_multiplier = atr_multiplier
        self.lookback_seconds = lookback_seconds

    def check(self, market_data: MarketData, indicators: Indicators, position: Optional[Position]) -> Optional[TriggerEvent]:
        atr = indicators.atr
        if atr <= 0:
            return None
        # 从 klines 取回看窗口内的起始价格
        # lookback_seconds / (interval_minutes * 60) = 需要的K线数
        interval_minutes = int(market_data.interval.replace("m", "").replace("h", "")) if "m" in market_data.interval else 60
        lookback_bars = max(1, self.lookback_seconds // (interval_minutes * 60))
        if len(market_data.klines) < lookback_bars + 1:
            return None
        ref_price = market_data.klines[-(lookback_bars + 1)].close
        current_price = market_data.current_price
        price_change = abs(current_price - ref_price)
        threshold = atr * self.atr_multiplier
        if price_change < threshold:
            return None
        change_pct = (current_price - ref_price) / ref_price * 100
        direction = "急涨" if current_price > ref_price else "急跌"
        return TriggerEvent(
            event_type="price_surge",
            description=f"{self.lookback_seconds // 60}分钟内{direction} {abs(change_pct):.2f}%, ATR倍数 {price_change / atr:.1f}x",
            severity="high" if price_change > atr * 2 else "medium",
            key_data={"price_change_pct": round(change_pct, 4), "atr_ratio": round(price_change / atr, 2), "direction": direction},
            timestamp=datetime.now(timezone.utc),
        )


# src/ai_trader/events/detectors/volume_spike.py
from datetime import datetime, timezone
from typing import Optional
from .base import BaseDetector
from ..models import TriggerEvent
from ...models.market import MarketData, Indicators
from ...models.order import Position


class VolumeSpikeDetector(BaseDetector):
    """成交量突增检测器：最近K线成交量超过均值的 N 倍"""

    def __init__(self, volume_multiplier: float = 2.5):
        self.volume_multiplier = volume_multiplier

    def check(self, market_data: MarketData, indicators: Indicators, position: Optional[Position]) -> Optional[TriggerEvent]:
        klines = market_data.klines
        if len(klines) < 21:
            return None
        # 用前20根K线计算平均成交量（排除最近1根）
        avg_volume = sum(k.volume for k in klines[-21:-1]) / 20
        if avg_volume <= 0:
            return None
        latest_volume = klines[-1].volume
        ratio = latest_volume / avg_volume
        if ratio < self.volume_multiplier:
            return None
        return TriggerEvent(
            event_type="volume_spike",
            description=f"成交量突增 {ratio:.1f}x (均值 {avg_volume:.0f}, 当前 {latest_volume:.0f})",
            severity="high" if ratio > 4.0 else "medium",
            key_data={"volume_ratio": round(ratio, 2), "avg_volume": round(avg_volume, 2), "latest_volume": round(latest_volume, 2)},
            timestamp=datetime.now(timezone.utc),
        )


# src/ai_trader/events/detectors/rsi_extreme.py
from datetime import datetime, timezone
from typing import Optional
from .base import BaseDetector
from ..models import TriggerEvent
from ...models.market import MarketData, Indicators
from ...models.order import Position


class RSIExtremeDetector(BaseDetector):
    """RSI 超买/超卖检测器"""

    def __init__(self, upper_threshold: float = 75, lower_threshold: float = 25):
        self.upper_threshold = upper_threshold
        self.lower_threshold = lower_threshold

    def check(self, market_data: MarketData, indicators: Indicators, position: Optional[Position]) -> Optional[TriggerEvent]:
        rsi = indicators.rsi
        if rsi <= 0:
            return None
        if rsi >= self.upper_threshold:
            return TriggerEvent(
                event_type="rsi_extreme",
                description=f"RSI 超买 {rsi:.1f} (阈值 {self.upper_threshold})",
                severity="high" if rsi > 80 else "medium",
                key_data={"rsi": round(rsi, 2), "zone": "overbought"},
                timestamp=datetime.now(timezone.utc),
            )
        if rsi <= self.lower_threshold:
            return TriggerEvent(
                event_type="rsi_extreme",
                description=f"RSI 超卖 (oversold) {rsi:.1f} (阈值 {self.lower_threshold})",
                severity="high" if rsi < 20 else "medium",
                key_data={"rsi": round(rsi, 2), "zone": "oversold"},
                timestamp=datetime.now(timezone.utc),
            )
        return None


# src/ai_trader/events/detectors/macd_cross.py
from datetime import datetime, timezone
from typing import Optional
from .base import BaseDetector
from ..models import TriggerEvent
from ...models.market import MarketData, Indicators
from ...models.order import Position


class MACDCrossDetector(BaseDetector):
    """MACD 金叉/死叉检测器：需要前后两次数据比较"""

    def __init__(self):
        self._prev_macd: Optional[float] = None
        self._prev_signal: Optional[float] = None

    def check(self, market_data: MarketData, indicators: Indicators, position: Optional[Position]) -> Optional[TriggerEvent]:
        macd = indicators.macd
        signal = indicators.macd_signal
        result = None
        if self._prev_macd is not None and self._prev_signal is not None:
            prev_diff = self._prev_macd - self._prev_signal
            curr_diff = macd - signal
            if prev_diff <= 0 < curr_diff:
                result = TriggerEvent(
                    event_type="macd_cross",
                    description=f"MACD 金叉 (MACD={macd:.4f}, Signal={signal:.4f})",
                    severity="medium",
                    key_data={"cross_type": "golden", "macd": round(macd, 6), "signal": round(signal, 6)},
                    timestamp=datetime.now(timezone.utc),
                )
            elif prev_diff >= 0 > curr_diff:
                result = TriggerEvent(
                    event_type="macd_cross",
                    description=f"MACD 死叉 (MACD={macd:.4f}, Signal={signal:.4f})",
                    severity="medium",
                    key_data={"cross_type": "death", "macd": round(macd, 6), "signal": round(signal, 6)},
                    timestamp=datetime.now(timezone.utc),
                )
        self._prev_macd = macd
        self._prev_signal = signal
        return result


# src/ai_trader/events/detectors/bollinger_break.py
from datetime import datetime, timezone
from typing import Optional
from .base import BaseDetector
from ..models import TriggerEvent
from ...models.market import MarketData, Indicators
from ...models.order import Position


class BollingerBreakDetector(BaseDetector):
    """布林带突破检测器"""

    def check(self, market_data: MarketData, indicators: Indicators, position: Optional[Position]) -> Optional[TriggerEvent]:
        price = market_data.current_price
        upper = indicators.boll_upper
        lower = indicators.boll_lower
        if upper <= 0 or lower <= 0:
            return None
        if price > upper:
            pct = (price - upper) / upper * 100
            return TriggerEvent(
                event_type="bollinger_break",
                description=f"价格突破布林上轨 (价格={price:.2f}, 上轨={upper:.2f}, 偏离 {pct:.2f}%)",
                severity="high" if pct > 1.0 else "medium",
                key_data={"direction": "upper", "price": price, "band": upper, "deviation_pct": round(pct, 4)},
                timestamp=datetime.now(timezone.utc),
            )
        if price < lower:
            pct = (lower - price) / lower * 100
            return TriggerEvent(
                event_type="bollinger_break",
                description=f"价格跌破布林下轨 (价格={price:.2f}, 下轨={lower:.2f}, 偏离 {pct:.2f}%)",
                severity="high" if pct > 1.0 else "medium",
                key_data={"direction": "lower", "price": price, "band": lower, "deviation_pct": round(pct, 4)},
                timestamp=datetime.now(timezone.utc),
            )
        return None


# src/ai_trader/events/detectors/market_state_change.py
from datetime import datetime, timezone
from typing import Optional
from ..models import TriggerEvent


class MarketStateChangeDetector:
    """市场状态突变检测器：MarketClassifier 状态发生变化时触发"""

    def __init__(self):
        self._prev_state: Optional[str] = None

    def check_state_change(self, current_state: str) -> Optional[TriggerEvent]:
        """检测状态变化。注意：接口与其他检测器不同，直接传入状态字符串"""
        result = None
        if self._prev_state is not None and self._prev_state != current_state:
            result = TriggerEvent(
                event_type="market_state_change",
                description=f"市场状态变化: {self._prev_state} → {current_state}",
                severity="high" if current_state == "breakout" else "medium",
                key_data={"prev_state": self._prev_state, "new_state": current_state},
                timestamp=datetime.now(timezone.utc),
            )
        self._prev_state = current_state
        return result


# src/ai_trader/events/detectors/position_pnl.py
from datetime import datetime, timezone
from typing import Optional
from .base import BaseDetector
from ..models import TriggerEvent
from ...models.market import MarketData, Indicators
from ...models.order import Position


class PositionPnLDetector(BaseDetector):
    """持仓浮亏/浮盈检测器"""

    def __init__(self, profit_threshold: float = 3.0, loss_threshold: float = -2.0):
        self.profit_threshold = profit_threshold
        self.loss_threshold = loss_threshold

    def check(self, market_data: MarketData, indicators: Indicators, position: Optional[Position]) -> Optional[TriggerEvent]:
        if position is None or position.size <= 0:
            return None
        roi = position.roi
        if roi >= self.profit_threshold:
            return TriggerEvent(
                event_type="position_pnl",
                description=f"持仓浮盈 {roi:.2f}% 达到阈值 {self.profit_threshold}%",
                severity="medium",
                key_data={"roi": round(roi, 4), "pnl": round(position.unrealized_pnl, 4), "side": position.side, "zone": "profit"},
                timestamp=datetime.now(timezone.utc),
            )
        if roi <= self.loss_threshold:
            return TriggerEvent(
                event_type="position_pnl",
                description=f"持仓浮亏 {roi:.2f}% 达到阈值 {self.loss_threshold}%",
                severity="high",
                key_data={"roi": round(roi, 4), "pnl": round(position.unrealized_pnl, 4), "side": position.side, "zone": "loss"},
                timestamp=datetime.now(timezone.utc),
            )
        return None
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/gowinder/code/gowinder/trader && python -m pytest tests/events/test_detectors.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/ai_trader/events/detectors/ tests/events/test_detectors.py
git commit -m "feat(events): add 7 market event detectors with base interface"
```

---

## Task 4: EventDetector 主类 — 整合检测器 + 冷却 + 策略过滤

**Files:**
- Create: `src/ai_trader/events/detector.py`
- Test: `tests/events/test_detector.py`

**Step 1: Write the failing test**

```python
# tests/events/test_detector.py
import pytest
from unittest.mock import MagicMock
from ai_trader.events.detector import EventDetector
from ai_trader.events.config import DEFAULT_EVENT_TRIGGER_CONFIG
from ai_trader.models.market import Indicators, MarketData, Kline


def _make_indicators(**overrides) -> Indicators:
    defaults = dict(
        ma7=100.0, ma25=100.0, ma99=100.0,
        rsi=50.0, macd=0.0, macd_signal=0.0, macd_histogram=0.0,
        boll_upper=110.0, boll_middle=100.0, boll_lower=90.0, atr=2.0,
    )
    defaults.update(overrides)
    return Indicators(**defaults)


def _make_market_data(current_price=100.0, indicators=None, klines=None):
    if indicators is None:
        indicators = _make_indicators()
    if klines is None:
        klines = [
            Kline(timestamp=1700000000 + i * 60, open=100.0, high=101.0, low=99.0, close=100.0, volume=1000.0)
            for i in range(150)
        ]
    return MarketData(
        symbol="BTC/USDT:USDT", current_price=current_price,
        klines=klines, interval="15m", indicators=indicators,
        high_24h=105.0, low_24h=95.0, change_24h=2.0, volume_24h=50000.0,
    )


class TestEventDetector:
    def test_init(self):
        detector = EventDetector(
            event_config=DEFAULT_EVENT_TRIGGER_CONFIG,
            enabled_strategies=["trend_following"],
        )
        assert detector is not None

    def test_scan_no_events_normal_market(self):
        detector = EventDetector(
            event_config=DEFAULT_EVENT_TRIGGER_CONFIG,
            enabled_strategies=["trend_following"],
        )
        md = _make_market_data()
        events = detector.scan(md, md.indicators, None, market_state=None)
        assert events == []

    def test_scan_filters_by_strategy(self):
        """trend_following 不关注 rsi_extreme，不应触发"""
        detector = EventDetector(
            event_config=DEFAULT_EVENT_TRIGGER_CONFIG,
            enabled_strategies=["trend_following"],
        )
        indicators = _make_indicators(rsi=20.0)
        md = _make_market_data(indicators=indicators)
        events = detector.scan(md, indicators, None, market_state=None)
        rsi_events = [e for e in events if e.event_type == "rsi_extreme"]
        assert len(rsi_events) == 0

    def test_scan_allows_strategy_relevant_event(self):
        """mean_reversion 关注 rsi_extreme，应触发"""
        detector = EventDetector(
            event_config=DEFAULT_EVENT_TRIGGER_CONFIG,
            enabled_strategies=["mean_reversion"],
        )
        indicators = _make_indicators(rsi=20.0)
        md = _make_market_data(indicators=indicators)
        events = detector.scan(md, indicators, None, market_state=None)
        rsi_events = [e for e in events if e.event_type == "rsi_extreme"]
        assert len(rsi_events) == 1

    def test_scan_multi_strategy_union(self):
        """多策略取并集"""
        detector = EventDetector(
            event_config=DEFAULT_EVENT_TRIGGER_CONFIG,
            enabled_strategies=["trend_following", "mean_reversion"],
        )
        active = detector._get_active_event_types()
        # trend_following 有 macd_cross，mean_reversion 有 rsi_extreme，并集都应包含
        assert "macd_cross" in active
        assert "rsi_extreme" in active

    def test_cooldown_prevents_duplicate(self):
        detector = EventDetector(
            event_config=DEFAULT_EVENT_TRIGGER_CONFIG,
            enabled_strategies=["mean_reversion"],
        )
        indicators = _make_indicators(rsi=20.0)
        md = _make_market_data(indicators=indicators)
        events1 = detector.scan(md, indicators, None, market_state=None)
        assert len(events1) > 0
        # 第二次调用应被冷却阻止
        events2 = detector.scan(md, indicators, None, market_state=None)
        assert len(events2) == 0

    def test_disabled_event_not_triggered(self):
        cfg = dict(DEFAULT_EVENT_TRIGGER_CONFIG)
        cfg["events"] = dict(cfg["events"])
        cfg["events"]["rsi_extreme"] = {"enabled": False, "upper_threshold": 75, "lower_threshold": 25}
        detector = EventDetector(
            event_config=cfg,
            enabled_strategies=["mean_reversion"],
        )
        indicators = _make_indicators(rsi=20.0)
        md = _make_market_data(indicators=indicators)
        events = detector.scan(md, indicators, None, market_state=None)
        rsi_events = [e for e in events if e.event_type == "rsi_extreme"]
        assert len(rsi_events) == 0
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/gowinder/code/gowinder/trader && python -m pytest tests/events/test_detector.py -v`
Expected: FAIL — ModuleNotFoundError

**Step 3: Write minimal implementation**

```python
# src/ai_trader/events/detector.py
"""事件检测器主类 — 整合所有子检测器 + 冷却 + 策略过滤"""

from typing import Optional
from .models import TriggerEvent
from .cooldown import CooldownManager
from .config import STRATEGY_EVENT_DEFAULTS
from .detectors import (
    PriceSurgeDetector, VolumeSpikeDetector, RSIExtremeDetector,
    MACDCrossDetector, BollingerBreakDetector,
    MarketStateChangeDetector, PositionPnLDetector,
)
from ..models.market import MarketData, Indicators
from ..models.order import Position
from ..utils.logger import logger


class EventDetector:
    """纯程序化事件检测器，不调用 LLM"""

    def __init__(self, event_config: dict, enabled_strategies: list[str]):
        self._config = event_config
        self._enabled_strategies = enabled_strategies
        events_cfg = event_config.get("events", {})

        # 初始化子检测器
        ps_cfg = events_cfg.get("price_surge", {})
        self._detectors: dict = {
            "price_surge": PriceSurgeDetector(
                atr_multiplier=ps_cfg.get("atr_multiplier", 1.5),
                lookback_seconds=ps_cfg.get("lookback_seconds", 300),
            ),
            "volume_spike": VolumeSpikeDetector(
                volume_multiplier=events_cfg.get("volume_spike", {}).get("volume_multiplier", 2.5),
            ),
            "rsi_extreme": RSIExtremeDetector(
                upper_threshold=events_cfg.get("rsi_extreme", {}).get("upper_threshold", 75),
                lower_threshold=events_cfg.get("rsi_extreme", {}).get("lower_threshold", 25),
            ),
            "macd_cross": MACDCrossDetector(),
            "bollinger_break": BollingerBreakDetector(),
            "position_pnl": PositionPnLDetector(
                profit_threshold=events_cfg.get("position_pnl", {}).get("profit_threshold_percent", 3.0),
                loss_threshold=events_cfg.get("position_pnl", {}).get("loss_threshold_percent", -2.0),
            ),
        }
        self._market_state_detector = MarketStateChangeDetector()

        # 冷却管理
        self._cooldown = CooldownManager(
            global_cooldown=event_config.get("global_cooldown_seconds", 300),
            per_event_cooldown=event_config.get("per_event_cooldown_seconds", 600),
        )

    def update_config(self, event_config: dict, enabled_strategies: list[str]) -> None:
        """热更新配置"""
        self._config = event_config
        self._enabled_strategies = enabled_strategies

    def _get_active_event_types(self) -> set[str]:
        """根据当前活跃策略，计算需要检测的事件类型（取并集）"""
        active = set()
        for strategy in self._enabled_strategies:
            events = STRATEGY_EVENT_DEFAULTS.get(strategy, [])
            active.update(events)
        return active

    def scan(
        self,
        market_data: MarketData,
        indicators: Indicators,
        position: Optional[Position],
        market_state: Optional[str],
    ) -> list[TriggerEvent]:
        """扫描所有活跃事件，返回触发的事件列表"""
        if not self._config.get("enabled", True):
            return []

        active_types = self._get_active_event_types()
        events_cfg = self._config.get("events", {})
        triggered: list[TriggerEvent] = []

        # 检测常规检测器（除 market_state_change 外）
        for name, detector in self._detectors.items():
            if name not in active_types:
                continue
            if not events_cfg.get(name, {}).get("enabled", True):
                continue
            if not self._cooldown.can_trigger(name):
                continue
            try:
                result = detector.check(market_data, indicators, position)
                if result is not None:
                    triggered.append(result)
                    self._cooldown.record_trigger(name)
            except Exception as e:
                logger.warning(f"Event detector {name} error: {e}")

        # 检测市场状态变化
        if "market_state_change" in active_types and market_state is not None:
            if events_cfg.get("market_state_change", {}).get("enabled", True):
                if self._cooldown.can_trigger("market_state_change"):
                    try:
                        result = self._market_state_detector.check_state_change(market_state)
                        if result is not None:
                            triggered.append(result)
                            self._cooldown.record_trigger("market_state_change")
                    except Exception as e:
                        logger.warning(f"Market state change detector error: {e}")

        if triggered:
            logger.info(f"Event detector triggered {len(triggered)} event(s): {[e.event_type for e in triggered]}")

        return triggered


def format_trigger_context(events: list[TriggerEvent], active_strategies: list[str], strategy_weights: dict[str, float] | None = None) -> str:
    """将触发事件格式化为 LLM prompt 注入文本"""
    if not events:
        return ""
    lines = ["⚡ 本次分析由市场事件触发（非定时调用），请重点关注以下信号：", ""]
    for i, event in enumerate(events, 1):
        lines.append(f"[{i}] {event.format_for_prompt()}")
        lines.append("")
    strategies_str = ", ".join(active_strategies)
    if strategy_weights:
        parts = [f"{s} (权重{w:.1f})" for s, w in strategy_weights.items() if s in active_strategies]
        strategies_str = ", ".join(parts) if parts else strategies_str
    lines.append(f"当前活跃策略: {strategies_str}")
    lines.append("请结合以上触发事件，判断是否需要立即行动。")
    return "\n".join(lines)
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/gowinder/code/gowinder/trader && python -m pytest tests/events/test_detector.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/ai_trader/events/detector.py tests/events/test_detector.py
git commit -m "feat(events): add EventDetector with strategy filtering and cooldown"
```

---

## Task 5: 集成到 Scheduler — 主循环改造

**Files:**
- Modify: `src/ai_trader/scheduler.py` — 主循环从 `sleep(decision_interval)` 改为 `sleep(30s)` + 事件检测 + 计时器
- Modify: `src/ai_trader/config.py` — 无需改动（event_trigger config 存 Redis）

**Step 1: 修改 Scheduler.__init__ — 初始化 EventDetector**

在 `src/ai_trader/scheduler.py` 的 `__init__` 中添加：

```python
# 导入（文件顶部追加）
from .events.detector import EventDetector, format_trigger_context
from .events.config import DEFAULT_EVENT_TRIGGER_CONFIG

# __init__ 中追加
self._event_detector: Optional[EventDetector] = None
self._event_trigger_config: dict = dict(DEFAULT_EVENT_TRIGGER_CONFIG)
self._decision_timer: float = 0.0  # monotonic time of last LLM call
self._scan_interval: int = 30  # 事件检测间隔（秒）
```

**Step 2: 修改 _init_redis — 加载 event_trigger 配置 + 初始化 EventDetector**

在 `_init_redis` 方法末尾追加：

```python
# 从 Redis 加载 event trigger 配置
raw = await self._redis.get("trading:event_trigger_config")
if raw:
    import json as _json
    self._event_trigger_config = _json.loads(raw)
self._scan_interval = self._event_trigger_config.get("scan_interval_seconds", 30)

# 初始化 EventDetector
self._event_detector = EventDetector(
    event_config=self._event_trigger_config,
    enabled_strategies=config.enabled_strategies,
)
```

**Step 3: 改造主循环 — sleep(30s) + 事件检测 + 计时器**

替换 `start()` 方法中 `while self.running:` 循环体的核心调度逻辑：

```python
# 原逻辑:
#   for symbol in config.symbols_list:
#       await self.run_cycle_for_symbol(symbol)
#   await asyncio.sleep(self._decision_interval)

# 新逻辑:
import time as _time

for symbol in config.symbols_list:
    try:
        trigger_events: list = []

        # 事件检测（如果 EventDetector 已初始化）
        if self._event_detector and self._event_trigger_config.get("enabled", True):
            try:
                md = await self.market_mgr.get_market_data(symbol, interval=f"{config.analysis_interval}m")
                if md:
                    # 获取市场状态
                    market_state_str = None
                    if self.decision_engine.market_classifier:
                        klines_data = [k.model_dump() for k in md.klines]
                        df = pd.DataFrame(klines_data)
                        mc = self.decision_engine.market_classifier.classify(df)
                        market_state_str = mc.state.value

                    position = None
                    if config.trading_mode == "testnet":
                        # testnet 使用虚拟持仓
                        if symbol in self._testnet_positions:
                            position = self._testnet_positions[symbol]
                    else:
                        position = await self.position_mgr.get_position(symbol)

                    trigger_events = self._event_detector.scan(
                        md, md.indicators, position, market_state=market_state_str
                    )
            except Exception as e:
                logger.warning(f"Event detection failed for {symbol}: {e}")

        now = _time.monotonic()
        should_run_llm = False
        trigger_context = None

        # 情况1：有事件触发
        if trigger_events:
            should_run_llm = True
            trigger_context = trigger_events

        # 情况2：定时器到期
        if (now - self._decision_timer) >= self._decision_interval:
            should_run_llm = True

        if should_run_llm:
            await self.run_cycle_for_symbol(symbol, trigger_context=trigger_context)
            self._decision_timer = _time.monotonic()

    except Exception as e:
        logger.error(f"Error in cycle for {symbol}: {e}")

# sleep 改为 scan_interval
logger.info(f"Waiting {self._scan_interval}s...")
await asyncio.sleep(self._scan_interval)
```

**Step 4: 修改 run_cycle_for_symbol — 传递 trigger_context**

```python
async def run_cycle_for_symbol(self, symbol: str, trigger_context: list | None = None):
    """执行指定 symbol 的交易循环"""
    async with self._get_symbol_lock(symbol):
        await self._run_cycle_for_symbol_impl(symbol, trigger_context=trigger_context)

async def _run_cycle_for_symbol_impl(self, symbol: str, trigger_context: list | None = None):
    # ... 现有代码 ...
    # 在调用 decision_engine.analyze_and_decide 时传入 trigger_context
    decision, tech, risk = await self.decision_engine.analyze_and_decide(
        market_data, position, balance, equity,
        mtf_data=mtf_data,
        trigger_context=trigger_context,
    )
```

**Step 5: 修改 _config_listener — 热更新 event_trigger 配置**

在 Redis config listener 中处理 `trading:event_trigger_config:updated` 频道：

```python
# 在 _config_listener 的 channel 处理逻辑中追加
elif channel == "trading:event_trigger_config:updated":
    raw = await self._redis.get("trading:event_trigger_config")
    if raw:
        self._event_trigger_config = json.loads(raw)
        self._scan_interval = self._event_trigger_config.get("scan_interval_seconds", 30)
        if self._event_detector:
            self._event_detector.update_config(
                self._event_trigger_config, config.enabled_strategies
            )
        logger.info("Event trigger config updated from Redis")
```

**Step 6: Commit**

```bash
git add src/ai_trader/scheduler.py
git commit -m "feat(scheduler): integrate EventDetector into main loop with 30s scan interval"
```

---

## Task 6: HybridDecisionEngine — 注入 trigger_context 到 LLM prompt

**Files:**
- Modify: `src/ai_trader/ai/hybrid_decision.py` — `analyze_and_decide` 增加 `trigger_context` 参数
- Modify: `src/ai_trader/ai/decision.py` — `_make_decision` 增加 trigger 文本注入

**Step 1: 修改 analyze_and_decide 签名**

在 `hybrid_decision.py` 的 `analyze_and_decide` 方法签名中加参数：

```python
async def analyze_and_decide(
    self,
    market_data: MarketData,
    current_position: Optional[Position],
    available_balance: float,
    total_equity: float,
    mtf_data: Optional[MultiTimeframeData] = None,
    daily_pnl: float = 0.0,
    trades_today: int = 0,
    consecutive_losses: int = 0,
    emotional_state: str = "calm",
    trigger_context: list | None = None,  # 新增
) -> Tuple[TradingDecision, TechnicalAnalysisResult, RiskAssessment]:
```

传递给 `_make_hybrid_decision`：

```python
decision = await self._make_hybrid_decision(
    # ... 现有参数 ...
    trigger_context=trigger_context,
)
```

**Step 2: 修改 _make_hybrid_decision → _make_decision — 注入 prompt**

在 `_make_hybrid_decision` 签名中加 `trigger_context: list | None = None`，传递给 `self._make_decision`。

在 `decision.py` 的 `_make_decision` 中，在组装 `user_prompt` 前追加 trigger 文本：

```python
# 在 user_prompt = TRADING_USER.format(...) 之后
if trigger_context:
    from ..events.detector import format_trigger_context
    trigger_text = format_trigger_context(
        trigger_context,
        active_strategies=config.enabled_strategies,
    )
    user_prompt = trigger_text + "\n\n" + user_prompt
```

**Step 3: 同步修改 DecisionEngine 基类签名**

在 `decision.py` 的 `analyze_and_decide` 和 `_make_decision` 也增加 `trigger_context` 参数（保持兼容）。

**Step 4: Commit**

```bash
git add src/ai_trader/ai/hybrid_decision.py src/ai_trader/ai/decision.py
git commit -m "feat(decision): inject trigger_context into LLM prompt for event-driven calls"
```

---

## Task 7: Redis 配置存储 + Dashboard API（可后续迭代）

**Files:**
- 此任务标记为可选/后续迭代，初始版本用默认配置即可
- 需要时：新增 Dashboard route `api.event-trigger-config.ts`
- 需要时：新增 Dashboard 页面 `dashboard.event-trigger.tsx`

**Step 1: 初始化 Redis 默认配置**

在 Scheduler 的 `_init_redis` 中，如果 Redis 中没有配置则写入默认值：

```python
if not await self._redis.exists("trading:event_trigger_config"):
    await self._redis.set(
        "trading:event_trigger_config",
        json.dumps(DEFAULT_EVENT_TRIGGER_CONFIG),
    )
    logger.info("Initialized default event trigger config in Redis")
```

**Step 2: Commit**

```bash
git add src/ai_trader/scheduler.py
git commit -m "feat(events): initialize default event trigger config in Redis"
```

---

## 执行顺序总结

| Task | 内容 | 依赖 |
|------|------|------|
| 1 | TriggerEvent 模型 + 配置常量 | 无 |
| 2 | CooldownManager | 无 |
| 3 | 7 个检测器 | Task 1 |
| 4 | EventDetector 主类 | Task 1, 2, 3 |
| 5 | Scheduler 集成 | Task 4 |
| 6 | HybridDecisionEngine prompt 注入 | Task 4 |
| 7 | Redis 配置初始化 | Task 5 |

Task 1 和 Task 2 可并行。Task 5 和 Task 6 可并行。
