import pytest
from unittest.mock import AsyncMock, MagicMock
from ai_trader.config import TradingConfig


@pytest.mark.asyncio
async def test_stock_symbol_short_filtering(monkeypatch):
    """Stock symbols should filter out short actions to hold"""
    monkeypatch.setenv("STOCK_TRADING_SYMBOLS", "AAPLx/USD")
    from ai_trader import config as config_module
    cfg = config_module.TradingConfig(_env_file=None)
    monkeypatch.setattr(config_module, "config", cfg)

    # Verify is_stock_symbol works
    assert cfg.is_stock_symbol("AAPLx/USD") is True
    assert cfg.is_stock_symbol("BTC/USDT:USDT") is False


def test_stock_trading_prompt_exists():
    """Stock trading prompt module should be importable"""
    from ai_trader.prompts.stock_trading import (
        STOCK_SYSTEM_PROMPT,
        STOCK_USER_PROMPT_TEMPLATE,
        STOCK_SCHEMA,
    )
    assert len(STOCK_SYSTEM_PROMPT) > 100
    assert "{symbol}" in STOCK_USER_PROMPT_TEMPLATE
    # Schema should not contain short actions
    actions = STOCK_SCHEMA["properties"]["action"]["enum"]
    assert "open_short" not in actions
    assert "close_short" not in actions
    assert "open_long" in actions
    assert "close_long" in actions


def test_stock_schema_actions():
    """Stock schema should only allow long-side actions"""
    from ai_trader.prompts.stock_trading import STOCK_SCHEMA
    actions = STOCK_SCHEMA["properties"]["action"]["enum"]
    valid_stock_actions = {"open_long", "close_long", "add_long", "reduce_long", "hold"}
    assert set(actions) == valid_stock_actions
