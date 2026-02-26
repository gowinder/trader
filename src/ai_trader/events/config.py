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
            "threshold_pct": 3.0,
            "window_minutes": 5,
            "severity": "high",
        },
        "volume_spike": {
            "enabled": True,
            "threshold_multiplier": 3.0,
            "window_minutes": 5,
            "severity": "medium",
        },
        "rsi_extreme": {
            "enabled": True,
            "overbought": 80,
            "oversold": 20,
            "severity": "medium",
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
            "profit_threshold_pct": 5.0,
            "loss_threshold_pct": -3.0,
            "severity": "high",
        },
    },
}
