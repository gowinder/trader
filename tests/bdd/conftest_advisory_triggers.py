"""BDD step definitions for Advisory Triggers"""

import pytest
from pytest_bdd import given, when, then, parsers

from ai_trader.advisory.triggers import (
    PriceVolatilityTrigger,
    ConsecutiveLossTrigger,
    UnrealizedPnLTrigger,
    SentimentShiftTrigger,
    TriggerManager,
    TriggerConfig,
)


@pytest.fixture
def at_context():
    return {}


# ── Given: 价格波动 ──────────────────────────────

@given(parsers.parse("价格波动触发器阈值为 {threshold:g}%，冷却 {cd:d} 分钟"))
def at_price_volatility(at_context, threshold, cd):
    at_context["pv_trigger"] = PriceVolatilityTrigger(
        threshold=threshold, cooldown_minutes=cd,
    )


@given(parsers.parse("{symbol} 价格波动刚刚触发过"))
def at_price_just_fired(at_context, symbol):
    at_context["pv_trigger"]._mark_fired(symbol)


# ── Given: 连续亏损 ──────────────────────────────

@given(parsers.parse("连续亏损触发器阈值为 {threshold:d} 次，冷却 {cd:d} 分钟"))
def at_consecutive_loss(at_context, threshold, cd):
    at_context["cl_trigger"] = ConsecutiveLossTrigger(
        threshold=threshold, cooldown_minutes=cd,
    )


# ── Given: 未实现亏损 ──────────────────────────────

@given(parsers.parse("未实现亏损触发器阈值为 {threshold:g}%，冷却 {cd:d} 分钟"))
def at_unrealized_pnl(at_context, threshold, cd):
    at_context["up_trigger"] = UnrealizedPnLTrigger(
        threshold=threshold, cooldown_minutes=cd,
    )


# ── Given: 情绪 ──────────────────────────────

@given(parsers.parse("情绪触发器冷却 {cd:d} 分钟"))
def at_sentiment(at_context, cd):
    at_context["st_trigger"] = SentimentShiftTrigger(cooldown_minutes=cd)


# ── Given: 触发管理器 ──────────────────────────────

@given(parsers.parse("触发管理器间隔为 {interval:d} 分钟"))
def at_trigger_manager(at_context, interval):
    at_context["tm"] = TriggerManager(TriggerConfig(interval_minutes=interval))


@given("刚刚执行过定时调度")
def at_just_scheduled(at_context):
    at_context["tm"].mark_scheduled_run()


# ── When: 价格波动 ──────────────────────────────

@when(parsers.parse("{symbol} 价格从 {prev:g} 变为 {curr:g}"))
def at_check_price(at_context, symbol, prev, curr):
    result = at_context["pv_trigger"].check(curr, prev, symbol=symbol)
    at_context["pv_result"] = result


# ── When: 连续亏损 ──────────────────────────────

@when(parsers.parse("连续亏损次数为 {count:d}"))
def at_check_loss(at_context, count):
    at_context["cl_result"] = at_context["cl_trigger"].check(count)


# ── When: 未实现亏损 ──────────────────────────────

@when(parsers.parse("{symbol} 未实现亏损为 {pct:g}%"))
def at_check_unrealized(at_context, symbol, pct):
    at_context["up_result"] = at_context["up_trigger"].check(pct, symbol=symbol)


# ── When: 情绪 ──────────────────────────────

@when("市场情绪为极度恐慌")
def at_extreme_fear(at_context):
    at_context["st_result"] = at_context["st_trigger"].check(extreme_fear=True)


@when("市场情绪为极度贪婪")
def at_extreme_greed(at_context):
    at_context["st_result"] = at_context["st_trigger"].check(extreme_greed=True)


@when("市场情绪正常")
def at_normal_sentiment(at_context):
    at_context["st_result"] = at_context["st_trigger"].check()


# ── Then: 价格波动 ──────────────────────────────

@then("应触发价格波动建议")
def at_pv_triggered(at_context):
    assert at_context["pv_result"] is not None


@then("不应触发价格波动建议")
def at_pv_not_triggered(at_context):
    assert at_context["pv_result"] is None


@then(parsers.parse("建议详情中变化幅度为 {pct:g}%"))
def at_pv_change_pct(at_context, pct):
    assert at_context["pv_result"]["change_pct"] == pytest.approx(pct, rel=1e-2)


# ── Then: 连续亏损 ──────────────────────────────

@then("应触发连续亏损建议")
def at_cl_triggered(at_context):
    assert at_context["cl_result"] is not None


@then("不应触发连续亏损建议")
def at_cl_not_triggered(at_context):
    assert at_context["cl_result"] is None


# ── Then: 未实现亏损 ──────────────────────────────

@then("应触发未实现亏损建议")
def at_up_triggered(at_context):
    assert at_context["up_result"] is not None


@then("不应触发未实现亏损建议")
def at_up_not_triggered(at_context):
    assert at_context["up_result"] is None


# ── Then: 情绪 ──────────────────────────────

@then("应触发情绪建议")
def at_st_triggered(at_context):
    assert at_context["st_result"] is not None


@then("不应触发情绪建议")
def at_st_not_triggered(at_context):
    assert at_context["st_result"] is None


# ── Then: 定时调度 ──────────────────────────────

@then("定时调度应运行")
def at_should_schedule(at_context):
    assert at_context["tm"].should_run_scheduled() is True


@then("定时调度不应运行")
def at_should_not_schedule(at_context):
    assert at_context["tm"].should_run_scheduled() is False
