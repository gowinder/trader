"""事件触发配置常量 — 策略事件映射与默认触发参数。"""

from __future__ import annotations

# 每种策略关注的事件类型列表
STRATEGY_EVENT_DEFAULTS: dict[str, list[str]] = {
    "trend_following": [
        "price_surge",
        "macd_cross",
        "market_state_change",
        "position_pnl",
    ],
    "mean_reversion": [
        "price_surge",
        "rsi_extreme",
        "bollinger_break",
        "market_state_change",
        "position_pnl",
    ],
    "breakout": [
        "price_surge",
        "volume_spike",
        "bollinger_break",
        "market_state_change",
        "position_pnl",
    ],
}

# 完整的默认事件触发配置
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
            "confirmation_bars": 1,
            "severity": "medium",
        },
        "bollinger_break": {
            "enabled": True,
            "std_dev": 2.0,
            "severity": "medium",
        },
        "market_state_change": {
            "enabled": True,
            "severity": "high",
        },
        "position_pnl": {
            "enabled": True,
            "profit_threshold_percent": 3.0,
            "loss_threshold_percent": -2.0,
        },
    },
}
