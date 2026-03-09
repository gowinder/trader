"""BDD step definitions for SignalFilter (anti-overtrading)"""

import pytest
from datetime import datetime, timedelta
from pytest_bdd import given, when, then, parsers

from ai_trader.strategies.signal_filter import SignalFilter
from ai_trader.strategies.strategy_base import SignalAction


@pytest.fixture
def sf_context():
    return {}


# ── Given ──────────────────────────────────────────

@given(parsers.parse("信号过滤器最小间隔为 {hours:g} 小时"))
def sf_min_interval(sf_context, hours):
    sf_context["min_interval"] = hours


@given(parsers.parse("信号过滤器反转冷却为 {hours:g} 小时"))
def sf_reverse_cooldown(sf_context, hours):
    sf_context["reverse_cooldown"] = hours
    sf_context["filter"] = SignalFilter(
        min_interval_hours=sf_context["min_interval"],
        reverse_cooldown_hours=hours,
    )
    sf_context["now"] = datetime(2026, 1, 1, 12, 0, 0)


_ACTION_MAP = {
    "LONG": SignalAction.LONG,
    "SHORT": SignalAction.SHORT,
    "HOLD": SignalAction.HOLD,
    "CLOSE_LONG": SignalAction.CLOSE_LONG,
    "CLOSE_SHORT": SignalAction.CLOSE_SHORT,
}


@given(parsers.parse("上次交易为 {action}，{hours:g} 小时前"))
def sf_last_trade(sf_context, action, hours):
    f = sf_context["filter"]
    trade_time = sf_context["now"] - timedelta(hours=hours)
    f.record_trade(_ACTION_MAP[action], trade_time)


# ── When ──────────────────────────────────────────

@when(parsers.parse("收到 {action} 信号"))
def sf_receive_signal(sf_context, action):
    f = sf_context["filter"]
    allowed, reason = f.should_allow_signal(_ACTION_MAP[action], sf_context["now"])
    sf_context["allowed"] = allowed
    sf_context["reason"] = reason


# ── Then ──────────────────────────────────────────

@then("信号应被允许")
def sf_signal_allowed(sf_context):
    assert sf_context["allowed"] is True


@then("信号应被拒绝")
def sf_signal_rejected(sf_context):
    assert sf_context["allowed"] is False


@then(parsers.parse('原因包含 "{text}"'))
def sf_reason_contains(sf_context, text):
    assert text in sf_context["reason"]
