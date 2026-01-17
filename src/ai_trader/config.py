"""配置管理模块 - 使用 pydantic-settings"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Literal


class TradingConfig(BaseSettings):
    """交易配置"""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # 交易所配置
    weex_api_key: str = Field(..., validation_alias="WEEX_API_KEY")
    weex_api_secret: str = Field(..., validation_alias="WEEX_API_SECRET")
    weex_passphrase: str = Field(..., validation_alias="WEEX_PASSPHRASE")
    weex_api_url: str = Field(default="https://api-contract.weex.com")

    # 代理配置
    proxy_url: str = Field(default="")

    # 交易对
    trading_symbol: str = Field(default="cmt_btcusdt")

    # AI 配置
    openrouter_api_key: str = Field(..., validation_alias="OPENROUTER_API_KEY")
    ai_model: str = Field(default="deepseek/deepseek-chat")
    ai_fallback_model: str = Field(default="minimax/minimax-01")

    # 杠杆配置
    leverage_min: int = Field(default=3)
    leverage_max: int = Field(default=10)
    default_leverage: int = Field(default=5)

    # 风险控制
    stop_loss_percent: float = Field(default=5.0)
    take_profit_percent: float = Field(default=10.0)
    max_position_percent: float = Field(default=20.0)

    # 交易策略
    trading_strategy: Literal["short_term", "long_term", "balanced"] = "balanced"
    analysis_interval: int = Field(default=15)
    decision_interval: int = Field(default=60)

    # 日志
    log_level: str = Field(default="INFO")
    log_file: str = Field(default="logs/trading.log")


# Global config instance
try:
    config = TradingConfig()
except Exception as e:
    # Fail fast if configuration is invalid
    # This ensures we don't run with broken config
    # For tests, ensure required env vars are set via pytest-env or conftest
    print(f"CRITICAL: Failed to load configuration: {e}")
    print("Please ensure .env file exists and contains all required fields.")
    raise
