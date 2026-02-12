"""BDD tests shared fixtures and step definitions for PositionManager"""

import pytest
from pytest_bdd import given, when, then, parsers
from ai_trader.risk.position_manager import PositionManager


@pytest.fixture
def context():
    """共享上下文，在 steps 之间传递数据"""
    return {}


# =============================================
# Given steps - 风控参数
# =============================================

@given(parsers.parse("风控参数默认风险比例为 {risk:g}%"))
def pm_default_risk(context, risk):
    context.setdefault("pm_kwargs", {})["default_risk_percentage"] = risk / 100


@given(parsers.parse("风控参数最大单笔风险为 {risk:g}%"))
def pm_max_risk(context, risk):
    context.setdefault("pm_kwargs", {})["max_single_trade_risk"] = risk / 100


@given(parsers.parse("每日亏损限额为 {limit:g}%"))
def pm_daily_loss_limit(context, limit):
    context.setdefault("pm_kwargs", {})["daily_loss_limit"] = limit / 100


@given(parsers.parse("账户余额为 {balance:g} USDT"))
def set_balance(context, balance):
    context["balance"] = balance


# =============================================
# Given steps - 持仓状态
# =============================================

@given(parsers.parse("多头持仓，入场价 {entry:g}，止损价 {stop_loss:g}"))
def set_long_position(context, entry, stop_loss):
    context["entry_price"] = entry
    context["stop_loss"] = stop_loss


@given(parsers.parse("多头持仓，入场价 {entry:g}，当前止损 {stop:g}"))
def set_long_position_with_current_stop(context, entry, stop):
    context["entry_price"] = entry
    context["current_stop"] = stop


@given(parsers.parse("当前价格为 {price:g}"))
def set_current_price(context, price):
    context["current_price"] = price


@given(parsers.parse("当前盈利为 {profit:g}%"))
def set_current_profit(context, profit):
    context["profit_pct"] = profit / 100


@given("趋势保持强势")
def set_trend_strong(context):
    context["trend_strong"] = True


@given("趋势已转弱")
def set_trend_weak(context):
    context["trend_strong"] = False


@given(parsers.parse("初始仓位大小为 {size:g}"))
def set_initial_position_size(context, size):
    context["initial_position_size"] = size


@given(parsers.parse("ATR 为 {atr:g}"))
def set_atr(context, atr):
    context["atr"] = atr


# =============================================
# When steps - 仓位计算
# =============================================

@when(parsers.parse("计算初始仓位，入场价 {entry:g}，止损价 {stop_loss:g}，风险比例 {risk:g}%"))
def calc_position_with_risk(context, entry, stop_loss, risk):
    pm = PositionManager(**context.get("pm_kwargs", {}))
    context["result"] = pm.calculate_initial_position(
        account_balance=context["balance"],
        entry_price=entry,
        stop_loss_price=stop_loss,
        risk_percentage=risk / 100,
    )


@when(parsers.parse("计算初始仓位，入场价 {entry:g}，止损价 {stop_loss:g}"))
def calc_position_no_risk(context, entry, stop_loss):
    pm = PositionManager(**context.get("pm_kwargs", {}))
    context["result"] = pm.calculate_initial_position(
        account_balance=context["balance"],
        entry_price=entry,
        stop_loss_price=stop_loss,
    )


# =============================================
# When steps - 加仓判断
# =============================================

@when(parsers.parse("判断是否应该加仓，最低盈利要求 {min_profit:g}%"))
def check_should_add(context, min_profit):
    pm = PositionManager(**context.get("pm_kwargs", {}))
    should_add, reason = pm.should_add_position(
        current_price=context["current_price"],
        entry_price=context["entry_price"],
        original_stop_loss=context["stop_loss"],
        current_profit_pct=context["profit_pct"],
        min_profit_for_add=min_profit / 100,
        trend_strong=context["trend_strong"],
    )
    context["should_add"] = should_add
    context["add_reason"] = reason


@when(parsers.parse("计算第 {level:d} 层加仓仓位"))
def calc_pyramid_size(context, level):
    pm = PositionManager(**context.get("pm_kwargs", {}))
    context["pyramid_size"] = pm.calculate_pyramid_position_size(
        initial_position_size=context["initial_position_size"],
        pyramid_level=level,
    )


# =============================================
# When steps - 移动止损
# =============================================

@when(parsers.parse("价格到达 {price:g}，盈利 {profit:g}%，使用 {method} 移动止损"))
def calc_trailing_stop_basic(context, price, profit, method):
    pm = PositionManager(**context.get("pm_kwargs", {}))
    context["trailing_result"] = pm.calculate_trailing_stop(
        current_price=price,
        entry_price=context["entry_price"],
        current_stop=context["current_stop"],
        atr=context["atr"],
        profit_pct=profit / 100,
        method=method,
    )


@when(parsers.parse("价格到达 {price:g}，盈利 {profit:g}%，使用 {method} 移动止损，ATR倍数 {multiplier:g}"))
def calc_trailing_stop_atr(context, price, profit, method, multiplier):
    pm = PositionManager(**context.get("pm_kwargs", {}))
    context["trailing_result"] = pm.calculate_trailing_stop(
        current_price=price,
        entry_price=context["entry_price"],
        current_stop=context["current_stop"],
        atr=context["atr"],
        profit_pct=profit / 100,
        method=method,
        atr_multiplier=multiplier,
    )


@when(parsers.parse("价格到达 {price:g}，盈利 {profit:g}%，使用 {method} 移动止损，回撤比例 {pct:g}%"))
def calc_trailing_stop_pct(context, price, profit, method, pct):
    pm = PositionManager(**context.get("pm_kwargs", {}))
    context["trailing_result"] = pm.calculate_trailing_stop(
        current_price=price,
        entry_price=context["entry_price"],
        current_stop=context["current_stop"],
        atr=context["atr"],
        profit_pct=profit / 100,
        method=method,
        percentage=pct / 100,
    )


# =============================================
# When steps - 每日亏损
# =============================================

@when(parsers.parse("当日亏损为 {loss:g} USDT"))
def check_daily_loss(context, loss):
    pm = PositionManager(**context.get("pm_kwargs", {}))
    exceeded, message = pm.check_daily_loss_limit(
        daily_pnl=-loss,
        account_balance=context["balance"],
    )
    context["limit_exceeded"] = exceeded
    context["limit_message"] = message


@when(parsers.parse("当日盈利为 {profit:g} USDT"))
def check_daily_profit(context, profit):
    pm = PositionManager(**context.get("pm_kwargs", {}))
    exceeded, message = pm.check_daily_loss_limit(
        daily_pnl=profit,
        account_balance=context["balance"],
    )
    context["limit_exceeded"] = exceeded
    context["limit_message"] = message


# =============================================
# Then steps - 仓位计算结果
# =============================================

@then(parsers.parse("风险金额应为 {amount:g} USDT"))
def check_risk_amount(context, amount):
    assert context["result"].risk_amount == pytest.approx(amount)


@then(parsers.parse("仓位大小应为 {size:g}"))
def check_position_size(context, size):
    assert context["result"].position_size == pytest.approx(size)


@then(parsers.parse("实际风险比例应为 {risk:g}%"))
def check_risk_pct(context, risk):
    assert context["result"].risk_percentage == pytest.approx(risk / 100)


@then("计算结果应为空")
def check_result_none(context):
    assert context["result"] is None


# =============================================
# Then steps - 加仓判断结果
# =============================================

@then("应该允许加仓")
def check_should_add_true(context):
    assert context["should_add"] is True


@then("应该拒绝加仓")
def check_should_add_false(context):
    assert context["should_add"] is False


@then(parsers.parse("拒绝原因包含 \"{text}\""))
def check_add_reason_contains(context, text):
    assert text in context["add_reason"]


@then(parsers.parse("加仓仓位应为 {size:g}"))
def check_pyramid_size(context, size):
    assert context["pyramid_size"] == pytest.approx(size, rel=1e-6)


# =============================================
# Then steps - 移动止损结果
# =============================================

@then("止损应该移动")
def check_stop_should_move(context):
    assert context["trailing_result"].should_move_stop is True


@then("止损不应移动")
def check_stop_should_not_move(context):
    assert context["trailing_result"].should_move_stop is False


@then(parsers.parse("止损价应为 {price:g}"))
def check_stop_price_exact(context, price):
    assert context["trailing_result"].new_stop_price == pytest.approx(price)


@then(parsers.parse("止损价应接近 {price:g}"))
def check_stop_price_approx(context, price):
    assert context["trailing_result"].new_stop_price == pytest.approx(price, rel=1e-2)


@then(parsers.parse("止损原因包含 \"{text}\""))
def check_stop_reason_contains(context, text):
    assert text in context["trailing_result"].reason


# =============================================
# Then steps - 每日亏损结果
# =============================================

@then("应触发亏损限额")
def check_limit_exceeded(context):
    assert context["limit_exceeded"] is True


@then("不应触发亏损限额")
def check_limit_not_exceeded(context):
    assert context["limit_exceeded"] is False


@then(parsers.parse("限额消息包含 \"{text}\""))
def check_limit_message_contains(context, text):
    assert text in context["limit_message"]
