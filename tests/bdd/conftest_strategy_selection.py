"""BDD step definitions for StrategySelector & MarketClassifier"""

import pytest
from unittest.mock import MagicMock, patch
from pytest_bdd import given, when, then, parsers

from ai_trader.strategies.strategy_selector import StrategySelector, AggregatedSignal
from ai_trader.strategies.market_classifier import MarketState, MarketClassification
from ai_trader.strategies.strategy_base import Signal, SignalAction


@pytest.fixture
def ss_context():
    return {}


ALL_STRATEGIES = ["trend_following", "mean_reversion", "breakout"]


# ── Given ──────────────────────────────────────────

@given("启用全部策略")
def ss_all_strategies(ss_context):
    ss_context["selector"] = StrategySelector(ALL_STRATEGIES)


@given(parsers.parse("仅启用 {name} 策略"))
def ss_single_strategy(ss_context, name):
    ss_context["selector"] = StrategySelector([name])


@given(parsers.parse("覆盖 {state} 权重为 {weights_str}"))
def ss_override_weights(ss_context, state, weights_str):
    weights = {}
    for pair in weights_str.split(","):
        k, v = pair.split("=")
        weights[k.strip()] = float(v.strip())
    ss_context["selector"].update_weights(state, weights)


# ── When ──────────────────────────────────────────

@when(parsers.parse("市场状态为 {state}"))
def ss_select_for_state(ss_context, state):
    ms = MarketState(state)
    ss_context["weights"] = ss_context["selector"].select_strategies(ms)


@when("策略产生冲突信号且反向分数超过 70%")
def ss_conflicting_signals(ss_context):
    import pandas as pd
    import numpy as np

    selector = ss_context["selector"]

    # 构造冲突: trend_following -> LONG(0.8), mean_reversion -> SHORT(0.85)
    # strong_trend: tf=0.7, breakout=0.3, mr=0.0 — 不会冲突
    # weak_trend: tf=0.6, mr=0.4 — tf LONG score=0.8*0.6=0.48, mr SHORT score=0.85*0.4=0.34
    # 需要让反向分数 > 70% of best: 用 range_bound tf=0.2, mr=0.8
    # tf LONG score=0.8*0.2=0.16, mr SHORT score=0.85*0.8=0.68
    # opposite of SHORT is LONG, LONG score (0.16) vs SHORT best (0.68) -> 0.16/0.68=0.23 不冲突
    # 需要让两个方向分数接近: 用 weak_trend tf=0.6 mr=0.4
    # mock tf -> LONG conf 0.9, mock mr -> SHORT conf 0.9
    # LONG score=0.9*0.6=0.54, SHORT score=0.9*0.4=0.36, 0.36/0.54=0.67 < 0.7 不够
    # 调整: tf -> LONG conf 0.7, mr -> SHORT conf 0.95
    # LONG score=0.7*0.6=0.42, SHORT score=0.95*0.4=0.38, 0.38/0.42=0.9 > 0.7 冲突!

    mc = MarketClassification(
        state=MarketState.WEAK_TREND,
        confidence=0.7,
        adx_value=22.0,
        volatility=1.5,
        volume_ratio=1.0,
        trend_direction=1,
    )

    df = pd.DataFrame({
        "open": np.random.uniform(100, 101, 100),
        "high": np.random.uniform(101, 102, 100),
        "low": np.random.uniform(99, 100, 100),
        "close": np.random.uniform(100, 101, 100),
        "volume": np.random.uniform(1000, 2000, 100),
    })

    # Mock strategy generate_signal
    long_signal = Signal(
        action=SignalAction.LONG, confidence=0.7,
        entry_price=100.0, stop_loss=98.0, take_profit=104.0, reason="trend up",
    )
    short_signal = Signal(
        action=SignalAction.SHORT, confidence=0.95,
        entry_price=100.0, stop_loss=102.0, take_profit=96.0, reason="mean revert",
    )

    selector.strategies["trend_following"].generate_signal = MagicMock(return_value=long_signal)
    selector.strategies["mean_reversion"].generate_signal = MagicMock(return_value=short_signal)

    ss_context["agg_result"] = selector.aggregate_signals(df, mc)


# ── Then ──────────────────────────────────────────

@then(parsers.parse("{strategy} 权重应为 {weight:g}"))
def ss_check_weight(ss_context, strategy, weight):
    assert ss_context["weights"].get(strategy, 0.0) == pytest.approx(weight)


@then(parsers.parse("策略总数应为 {count:d}"))
def ss_check_count(ss_context, count):
    assert len(ss_context["weights"]) == count


@then("聚合结果应为 HOLD")
def ss_agg_hold(ss_context):
    assert ss_context["agg_result"].action == SignalAction.HOLD


@then(parsers.parse('原因应包含 "{text}"'))
def ss_reason_contains(ss_context, text):
    assert text in ss_context["agg_result"].reason
