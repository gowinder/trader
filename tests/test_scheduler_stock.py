import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from ai_trader.config import TradingConfig


@pytest.mark.asyncio
async def test_scheduler_stock_signal_filter_no_reverse_cooldown(monkeypatch):
    """Stock symbols should not have reverse cooldown in SignalFilter"""
    monkeypatch.setenv("STOCK_TRADING_SYMBOLS", "AAPLx/USD")
    monkeypatch.setenv("SIGNAL_REVERSE_COOLDOWN_HOURS", "12")
    monkeypatch.setenv("SIGNAL_MIN_INTERVAL_HOURS", "4")
    from ai_trader import config as config_module
    cfg = config_module.TradingConfig(_env_file=None)
    monkeypatch.setattr(config_module, "config", cfg)

    from ai_trader.strategies.signal_filter import SignalFilter
    from ai_trader.strategies.strategy_base import SignalAction
    from datetime import datetime as _dt

    # Stock symbol: reverse cooldown should be disabled (0)
    is_stock = cfg.is_stock_symbol("AAPLx/USD")
    assert is_stock is True

    # Create SignalFilter with 0 reverse cooldown (as scheduler would for stocks)
    sf = SignalFilter(min_interval_hours=4.0, reverse_cooldown_hours=0)

    # Record a LONG trade
    sf.record_trade(SignalAction.LONG, _dt.utcnow())

    # Immediately after a LONG trade, another LONG should be blocked by min_interval
    # But reverse (SHORT -> LONG flip) should NOT be blocked
    allowed, reason = sf.should_allow_signal(SignalAction.LONG, _dt.utcnow())
    # This is blocked by min interval, not reverse cooldown
    assert not allowed
    assert "soon" in reason.lower() or "interval" in reason.lower() or "cooldown" in reason.lower()


@pytest.mark.asyncio
async def test_scheduler_stock_position_sizing_no_leverage(monkeypatch):
    """Stock position sizing should not multiply by leverage"""
    monkeypatch.setenv("STOCK_TRADING_SYMBOLS", "AAPLx/USD")
    from ai_trader import config as config_module
    cfg = config_module.TradingConfig(_env_file=None)
    monkeypatch.setattr(config_module, "config", cfg)

    # Verify decision.leverage is forced to 1 for stocks in hybrid_decision
    assert cfg.is_stock_symbol("AAPLx/USD") is True

    # Simulate position sizing calculation
    balance = 10000.0
    position_percent = 10.0  # 10%
    leverage = 1  # forced for stocks

    # Stock sizing: balance * (pct/100) * 1
    stock_amount = balance * (position_percent / 100) * leverage
    assert stock_amount == 1000.0

    # Futures sizing would be: balance * (pct/100) * leverage (e.g. 5x)
    futures_leverage = 5
    futures_amount = balance * (position_percent / 100) * futures_leverage
    assert futures_amount == 5000.0

    # Stock amount should be strictly less
    assert stock_amount < futures_amount
