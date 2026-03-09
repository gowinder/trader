import os
import pytest
from ai_trader.config import TradingConfig


def test_config_loading_from_env(monkeypatch):
    """Test loading configuration from environment variables"""
    monkeypatch.setenv("WEEX_API_KEY", "test_key")
    monkeypatch.setenv("WEEX_API_SECRET", "test_secret")
    monkeypatch.setenv("WEEX_PASSPHRASE", "test_pass")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test_ai_key")
    monkeypatch.setenv("TRADING_SYMBOL", "eth_usdt")

    config = TradingConfig(_env_file=None)

    assert config.weex_api_key == "test_key"
    assert config.trading_symbol == "eth_usdt"
    assert config.leverage_min == 3  # Default value


def test_config_defaults():
    """Test default values"""
    # Create config with minimal required fields set via dummy env vars
    os.environ["WEEX_API_KEY"] = "k"
    os.environ["WEEX_API_SECRET"] = "s"
    os.environ["WEEX_PASSPHRASE"] = "p"
    os.environ["OPENROUTER_API_KEY"] = "a"

    config = TradingConfig(_env_file=None)

    assert config.weex_api_url == "https://api-contract.weex.com"
    assert config.ai_model == "deepseek/deepseek-v3.2"
    assert config.stop_loss_percent == 5.0


def test_advisory_config_defaults():
    """Test advisory config default values"""
    from ai_trader.config import TradingConfig
    cfg = TradingConfig(_env_file=None)
    assert cfg.advisory_enabled is False
    assert cfg.advisory_interval_minutes == 60
    # Advisory LLM 配置已移至 Dashboard/Redis，不再从 .env 读取
    assert not hasattr(cfg, "advisory_llm_provider")
    assert cfg.telegram_bot_token == ""
    assert cfg.telegram_chat_id == ""
