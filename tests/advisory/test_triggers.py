import pytest
from ai_trader.advisory.triggers import (
    TriggerManager, PriceVolatilityTrigger, ConsecutiveLossTrigger,
    UnrealizedPnLTrigger, SentimentShiftTrigger, TriggerConfig,
)


def test_trigger_config_defaults():
    cfg = TriggerConfig()
    assert cfg.price_volatility_enabled is True
    assert cfg.price_volatility_threshold == 5.0
    assert cfg.consecutive_loss_threshold == 3
    assert cfg.unrealized_pnl_threshold == -5.0
    assert cfg.cooldown_minutes == 30


def test_price_volatility_trigger_fires():
    trigger = PriceVolatilityTrigger(threshold=5.0, cooldown_minutes=30)
    result = trigger.check(current_price=94.0, previous_price=100.0, interval_minutes=5)
    assert result is not None
    assert result["change_pct"] == pytest.approx(-6.0, abs=0.1)


def test_price_volatility_trigger_no_fire():
    trigger = PriceVolatilityTrigger(threshold=5.0, cooldown_minutes=30)
    result = trigger.check(current_price=98.0, previous_price=100.0, interval_minutes=5)
    assert result is None


def test_consecutive_loss_trigger():
    trigger = ConsecutiveLossTrigger(threshold=3, cooldown_minutes=30)
    result = trigger.check(consecutive_losses=4)
    assert result is not None
    assert result["consecutive_losses"] == 4


def test_unrealized_pnl_trigger():
    trigger = UnrealizedPnLTrigger(threshold=-5.0, cooldown_minutes=30)
    result = trigger.check(unrealized_pnl_pct=-7.0)
    assert result is not None


def test_cooldown_prevents_duplicate():
    trigger = PriceVolatilityTrigger(threshold=5.0, cooldown_minutes=30)
    result1 = trigger.check(current_price=94.0, previous_price=100.0, interval_minutes=5)
    assert result1 is not None
    result2 = trigger.check(current_price=93.0, previous_price=100.0, interval_minutes=5)
    assert result2 is None


def test_trigger_manager_scheduled():
    mgr = TriggerManager(TriggerConfig(interval_minutes=60))
    assert mgr.should_run_scheduled() is True
    mgr.mark_scheduled_run()
    assert mgr.should_run_scheduled() is False
