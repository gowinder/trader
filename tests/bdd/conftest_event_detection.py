"""BDD step definitions for EventDetector & CooldownManager"""

import time
import pytest
from pytest_bdd import given, when, then, parsers

from ai_trader.events.cooldown import CooldownManager
from ai_trader.events.detector import EventDetector
from ai_trader.events.config import DEFAULT_EVENT_TRIGGER_CONFIG, STRATEGY_EVENT_DEFAULTS


@pytest.fixture
def ed_context():
    return {}


# ── Given: 策略与配置 ──────────────────────────────

@given(parsers.parse("启用策略为 {strategies}"))
def ed_set_strategies(ed_context, strategies):
    ed_context["strategies"] = [s.strip() for s in strategies.split(",")]
    ed_context["config"] = dict(DEFAULT_EVENT_TRIGGER_CONFIG)


@given("启用策略为空")
def ed_set_empty_strategies(ed_context):
    ed_context["strategies"] = []
    ed_context["config"] = dict(DEFAULT_EVENT_TRIGGER_CONFIG)


@given("事件检测全局禁用")
def ed_disable_global(ed_context):
    ed_context["config"]["enabled"] = False


@given(parsers.parse("{event_type} 事件被禁用"))
def ed_disable_event(ed_context, event_type):
    import copy
    cfg = ed_context.get("config", dict(DEFAULT_EVENT_TRIGGER_CONFIG))
    cfg = copy.deepcopy(cfg)
    cfg["events"][event_type]["enabled"] = False
    ed_context["config"] = cfg


# ── Given: 冷却管理器 ──────────────────────────────

@given(parsers.parse("冷却管理器全局冷却为 {global_cd:d} 秒，事件冷却为 {per_cd:d} 秒"))
def ed_cooldown_manager(ed_context, global_cd, per_cd):
    ed_context["cooldown"] = CooldownManager(
        global_cooldown=global_cd,
        per_event_cooldown=per_cd,
    )


@given(parsers.parse("{event_type} 事件刚刚触发"))
def ed_event_just_triggered(ed_context, event_type):
    ed_context["cooldown"].record_trigger(event_type)


@given(parsers.parse("{event_type} 事件在 {seconds:d} 秒前触发"))
def ed_event_triggered_ago(ed_context, event_type, seconds):
    cm = ed_context["cooldown"]
    cm.record_trigger(event_type)
    # 手动回拨时间戳
    now = time.monotonic()
    past = now - seconds
    cm._last_global_trigger = past
    cm._last_per_event[event_type] = past


# ── When: 扫描 ──────────────────────────────────

@when("执行事件扫描")
def ed_get_active_types(ed_context):
    detector = EventDetector(
        event_config=ed_context["config"],
        enabled_strategies=ed_context["strategies"],
    )
    ed_context["active_types"] = detector._get_active_event_types()


@when("对市场数据执行扫描")
def ed_scan_market(ed_context):
    detector = EventDetector(
        event_config=ed_context["config"],
        enabled_strategies=ed_context["strategies"],
    )
    # 使用 mock market_data — scan 内部全局/策略检查在真正调用检测器之前
    # 对于 "无启用策略" 和 "全局禁用" 场景，不会走到检测器调用
    from unittest.mock import MagicMock
    mock_md = MagicMock()
    ed_context["events"] = detector.scan("BTCUSDT", mock_md, None, None)


@when(parsers.parse("检查 {event_type} 是否可触发"))
def ed_check_can_trigger(ed_context, event_type):
    ed_context["can_trigger"] = ed_context["cooldown"].can_trigger(event_type)


@when("重置冷却管理器")
def ed_reset_cooldown(ed_context):
    ed_context["cooldown"].reset()


# ── Then ──────────────────────────────────────────

@then(parsers.parse('活跃事件类型应包含 "{event_type}"'))
def ed_active_contains(ed_context, event_type):
    assert event_type in ed_context["active_types"]


@then(parsers.parse('活跃事件类型不应包含 "{event_type}"'))
def ed_active_not_contains(ed_context, event_type):
    assert event_type not in ed_context["active_types"]


@then("触发事件列表应为空")
def ed_events_empty(ed_context):
    assert ed_context["events"] == []


@then(parsers.parse('触发事件不应包含 "{event_type}"'))
def ed_events_not_contain(ed_context, event_type):
    types = [e.event_type for e in ed_context["events"]]
    assert event_type not in types


@then("该事件不可触发")
def ed_cannot_trigger(ed_context):
    assert ed_context["can_trigger"] is False


@then("该事件可以触发")
def ed_can_trigger(ed_context):
    assert ed_context["can_trigger"] is True


@then(parsers.parse("{event_type} 应可以触发"))
def ed_event_can_trigger_after_reset(ed_context, event_type):
    assert ed_context["cooldown"].can_trigger(event_type) is True
