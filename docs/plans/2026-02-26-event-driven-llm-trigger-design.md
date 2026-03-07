# 市场事件驱动 LLM 智能触发机制 — 设计文档

## 背景

当前主决策 LLM 每 15 分钟定时调用一次。对于快速行情（急涨急跌、突破等），15 分钟间隔可能反应不及；但若缩短间隔又浪费 token 和 rate limit。

## 目标

在保留 15 分钟定时调用的基础上，增加纯程序化事件检测层，检测到市场异常时主动触发 LLM 调用，实现"平时低频，关键时刻即时响应"。

## 整体架构

```
Scheduler 主循环 (每30秒)
  │
  ├─ EventDetector.scan()          ← 纯程序化，不调 LLM
  │   ├─ PriceSurgeDetector
  │   ├─ VolumeSpikeDetector
  │   ├─ RSIExtremeDetector
  │   ├─ MACDCrossDetector
  │   ├─ BollingerBreakDetector
  │   ├─ MarketStateChangeDetector
  │   └─ PositionPnLDetector
  │
  ├─ 有事件触发？
  │   ├─ YES → 检查冷却 → 通过 → 调用 HybridDecisionEngine（带触发上下文）→ 重置15分钟计时器
  │   └─ NO  → pass
  │
  └─ 15分钟定时器到期？
      └─ YES → 调用 HybridDecisionEngine（常规调用）→ 重置计时器
```

## 核心设计原则

1. EventDetector 是纯计算层，30 秒跑一次，零 LLM 开销
2. 触发后复用现有 HybridDecisionEngine，不新建决策引擎
3. 冷却机制：全局 5 分钟 + 单事件 10 分钟
4. 触发后重置 15 分钟定时器，避免短时间内重复调用
5. 事件按策略关联过滤，只有当前活跃策略关注的事件才触发
6. 触发原因 + 关键数据注入 LLM prompt，让 LLM 聚焦分析

## 7 个事件检测器

| # | 事件 | 说明 | 关键参数 |
|---|---|---|---|
| 1 | price_surge | 价格急涨急跌 | atr_multiplier=1.5, lookback_seconds=300 |
| 2 | volume_spike | 成交量突增 | volume_multiplier=2.5 |
| 3 | rsi_extreme | RSI 超买/超卖 | upper=75, lower=25 |
| 4 | macd_cross | MACD 金叉/死叉 | 无额外参数 |
| 5 | bollinger_break | 布林带突破 | 无额外参数 |
| 6 | market_state_change | 市场状态突变 | 检测 MarketClassifier 状态变化 |
| 7 | position_pnl | 持仓浮亏/浮盈 | profit=3.0%, loss=-2.0% |

全部默认开启，用户可按需关闭。

## 策略关联过滤

不同策略关注不同事件，只有当前活跃策略关注的事件才能触发 LLM：

```python
STRATEGY_EVENT_DEFAULTS = {
    "trend_following": ["price_surge", "macd_cross", "market_state_change", "position_pnl"],
    "mean_reversion": ["price_surge", "rsi_extreme", "bollinger_break", "market_state_change", "position_pnl"],
    "breakout": ["price_surge", "volume_spike", "bollinger_break", "market_state_change", "position_pnl"],
}
```

当多策略同时启用时，取并集。

## 配置结构

存储在 Redis，Dashboard 可热更新：

```python
event_trigger_config = {
    "enabled": True,                    # 总开关
    "scan_interval_seconds": 30,        # 检测频率
    "global_cooldown_seconds": 300,     # 全局冷却 5 分钟
    "per_event_cooldown_seconds": 600,  # 单事件冷却 10 分钟
    "reset_decision_timer": True,       # 触发后重置15分钟定时器

    "events": {
        "price_surge": {
            "enabled": True,
            "atr_multiplier": 1.5,
            "lookback_seconds": 300
        },
        "volume_spike": {
            "enabled": True,
            "volume_multiplier": 2.5
        },
        "rsi_extreme": {
            "enabled": True,
            "upper_threshold": 75,
            "lower_threshold": 25
        },
        "macd_cross": {
            "enabled": True
        },
        "bollinger_break": {
            "enabled": True
        },
        "market_state_change": {
            "enabled": True
        },
        "position_pnl": {
            "enabled": True,
            "profit_threshold_percent": 3.0,
            "loss_threshold_percent": -2.0
        }
    }
}
```

## 核心数据模型

```python
@dataclass
class TriggerEvent:
    """传递给 LLM 的触发上下文"""
    event_type: str           # "price_surge"
    description: str          # "5分钟内跌幅 2.1 ATR"
    severity: str             # "high" / "medium"
    key_data: dict            # {"price_change_pct": -3.2, "atr_ratio": 2.1}
    timestamp: datetime
```

## EventDetector 主类

```python
class EventDetector:
    """纯程序化事件检测器，不调用 LLM"""

    def __init__(self, config, market_data_manager, strategy_selector):
        self.detectors = {
            "price_surge": PriceSurgeDetector(config),
            "volume_spike": VolumeSpikeDetector(config),
            "rsi_extreme": RSIExtremeDetector(config),
            "macd_cross": MACDCrossDetector(config),
            "bollinger_break": BollingerBreakDetector(config),
            "market_state_change": MarketStateChangeDetector(config),
            "position_pnl": PositionPnLDetector(config),
        }
        self.cooldown_manager = CooldownManager(config)

    def scan(self, symbol, market_data, indicators, position) -> list[TriggerEvent]:
        """扫描所有活跃事件，返回触发的事件列表"""
        active_events = self._get_active_events_for_strategies()
        triggered = []
        for name, detector in self.detectors.items():
            if name not in active_events:
                continue
            if not self.cooldown_manager.can_trigger(name):
                continue
            result = detector.check(market_data, indicators, position)
            if result.triggered:
                triggered.append(result)
        return triggered
```

## LLM Prompt 注入

事件触发时注入以下片段到 HybridDecisionEngine 的 prompt：

```
⚡ 本次分析由市场事件触发（非定时调用），请重点关注以下信号：

[1] 价格急跌 (severity: high)
    - 5分钟内跌幅: -3.2%
    - ATR倍数: 2.1x

[2] 成交量突增 (severity: medium)
    - 当前成交量/均值: 3.2x

当前活跃策略: trend_following (权重0.7), breakout (权重0.3)
请结合以上触发事件，判断是否需要立即行动。
```

## 调度器集成

改造 Scheduler 主循环：

```
现有循环:
  sleep(decision_interval) → run_cycle_for_symbol()

改为:
  sleep(30s) → EventDetector.scan()
              → 有触发？→ run_cycle_for_symbol(trigger_context=events) → 重置计时器
              → 无触发？→ 计时器到期？→ run_cycle_for_symbol(trigger_context=None)
```

- `run_cycle_for_symbol` 增加 `trigger_context: list[TriggerEvent] | None` 参数
- 有 trigger_context 时，注入到 HybridDecisionEngine 的 prompt 中
- 无 trigger_context 时，就是现有的常规定时调用

## 文件变更清单

| 操作 | 文件 | 说明 |
|---|---|---|
| 新增 | `src/ai_trader/events/__init__.py` | 模块初始化 |
| 新增 | `src/ai_trader/events/detector.py` | EventDetector 主类 + CooldownManager |
| 新增 | `src/ai_trader/events/models.py` | TriggerEvent 数据模型 |
| 新增 | `src/ai_trader/events/config.py` | STRATEGY_EVENT_DEFAULTS 常量 + 配置加载 |
| 新增 | `src/ai_trader/events/detectors/__init__.py` | 检测器模块初始化 |
| 新增 | `src/ai_trader/events/detectors/price_surge.py` | 价格急涨急跌检测器 |
| 新增 | `src/ai_trader/events/detectors/volume_spike.py` | 成交量突增检测器 |
| 新增 | `src/ai_trader/events/detectors/rsi_extreme.py` | RSI 极端值检测器 |
| 新增 | `src/ai_trader/events/detectors/macd_cross.py` | MACD 交叉检测器 |
| 新增 | `src/ai_trader/events/detectors/bollinger_break.py` | 布林带突破检测器 |
| 新增 | `src/ai_trader/events/detectors/market_state_change.py` | 市场状态突变检测器 |
| 新增 | `src/ai_trader/events/detectors/position_pnl.py` | 持仓浮亏/浮盈检测器 |
| 修改 | `src/ai_trader/scheduler.py` | 主循环改 30s + 集成 EventDetector + 计时器逻辑 |
| 修改 | `src/ai_trader/config.py` | 增加 event_trigger 默认配置 |
| 修改 | `src/ai_trader/ai/decision_engine.py` | prompt 组装增加 trigger_context |
| 修改 | Dashboard 相关 | event_trigger 配置的 UI 编辑页面 |
