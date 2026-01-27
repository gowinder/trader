"""配置管理模块 - 使用 pydantic-settings"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
from typing import Literal, Optional
import os


class LLMConfig(BaseSettings):
    """LLM Provider 配置"""

    model_config = SettingsConfigDict(env_prefix="LLM_", extra="ignore")

    # Provider 类型: openrouter, deepseek, glm, gemini
    provider: str = Field(default="openrouter", description="LLM Provider 类型")

    # API Key (从对应的 provider key 环境变量获取)
    api_key: str = Field(default="", description="LLM API Key")

    # 模型名称
    model: str = Field(default="deepseek/deepseek-chat", description="主模型名称")

    # 备用模型
    fallback_model: Optional[str] = Field(default=None, description="备用模型名称")

    # Base URL (可选，用于自定义端点)
    base_url: Optional[str] = Field(default=None, description="自定义 API Base URL")

    # 超时时间
    timeout: float = Field(default=60.0, description="请求超时时间(秒)")


class TradingConfig(BaseSettings):
    """交易配置"""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # 交易所配置（WEEX - 可选，仅在使用WEEX时需要）
    weex_api_key: str = Field(default="", validation_alias="WEEX_API_KEY")
    weex_api_secret: str = Field(default="", validation_alias="WEEX_API_SECRET")
    weex_passphrase: str = Field(default="", validation_alias="WEEX_PASSPHRASE")
    weex_api_url: str = Field(default="https://api-contract.weex.com")

    # 代理配置
    proxy_url: str = Field(default="")

    # ============= 交易所配置 =============
    exchange_type: Literal["weex", "binance", "bybit", "okx"] = Field(
        default="weex", validation_alias="EXCHANGE_TYPE"
    )
    use_ccxt: bool = Field(default=False, validation_alias="USE_CCXT")

    # ============= 运行模式 =============
    trading_mode: Literal["testnet", "live"] = Field(
        default="live", validation_alias="TRADING_MODE"
    )

    # ============= Testnet配置 =============
    testnet_exchange: str = Field(default="binance", validation_alias="TESTNET_EXCHANGE")
    testnet_api_key: str = Field(default="", validation_alias="TESTNET_API_KEY")
    testnet_api_secret: str = Field(default="", validation_alias="TESTNET_API_SECRET")

    # ============= Binance配置 =============
    binance_api_key: str = Field(default="", validation_alias="BINANCE_API_KEY")
    binance_api_secret: str = Field(default="", validation_alias="BINANCE_API_SECRET")

    # ============= Bybit配置 =============
    bybit_api_key: str = Field(default="", validation_alias="BYBIT_API_KEY")
    bybit_api_secret: str = Field(default="", validation_alias="BYBIT_API_SECRET")

    # ============= OKX配置 =============
    okx_api_key: str = Field(default="", validation_alias="OKX_API_KEY")
    okx_api_secret: str = Field(default="", validation_alias="OKX_API_SECRET")
    okx_passphrase: str = Field(default="", validation_alias="OKX_PASSPHRASE")

    # 交易对
    trading_symbol: str = Field(default="cmt_btcusdt")

    # AI 配置 (旧版兼容) - 已废弃，使用 LLMConfig
    openrouter_api_key: str = Field(default="", validation_alias="OPENROUTER_API_KEY")
    ai_model: str = Field(default="deepseek/deepseek-chat", validation_alias="AI_MODEL")
    ai_fallback_model: str = Field(
        default="minimax/minimax-01", validation_alias="AI_FALLBACK_MODEL"
    )

    # LLM Provider 配置 (新版)
    llm_provider: str = Field(default="openrouter", validation_alias="LLM_PROVIDER")
    llm_api_key: str = Field(default="", validation_alias="LLM_API_KEY")
    llm_model: str = Field(
        default="deepseek/deepseek-chat", validation_alias="LLM_MODEL"
    )
    llm_fallback_model: Optional[str] = Field(
        default=None, validation_alias="LLM_FALLBACK_MODEL"
    )
    llm_base_url: Optional[str] = Field(default=None, validation_alias="LLM_BASE_URL")
    llm_timeout: float = Field(default=60.0, validation_alias="LLM_TIMEOUT")

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

    # ============= Phase 4: 量化策略配置 =============
    # 决策权重
    quant_weight: float = Field(default=0.5, description="量化策略权重")
    ai_weight: float = Field(default=0.5, description="AI决策权重")

    # 功能开关
    enable_pattern_recognition: bool = Field(
        default=True, description="启用K线形态识别"
    )
    enable_quant_strategies: bool = Field(default=True, description="启用量化策略")

    # 启用的策略列表 (优化后只使用趋势跟随策略)
    enabled_strategies: list[str] = Field(
        default_factory=lambda: ["trend_following"],
        description="启用的策略列表",
    )

    # ============= 日志配置 =============
    log_level: str = Field(default="INFO")
    log_file: str = Field(default="logs/trading.log")

    # 日志翻译配置
    enable_log_translation: bool = Field(
        default=False, description="启用日志自动翻译"
    )
    log_target_language: str = Field(
        default="zh-CN", description="日志翻译目标语言 (zh-CN, ja, ko, etc.)"
    )

    @field_validator("llm_provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        """验证 Provider 类型"""
        valid_providers = ["openrouter", "deepseek", "glm", "gemini"]
        if v.lower() not in valid_providers:
            raise ValueError(f"无效的 LLM Provider: {v}. 支持的类型: {valid_providers}")
        return v.lower()

    def get_llm_config(self) -> LLMConfig:
        """获取 LLM 配置"""
        return LLMConfig(
            provider=self.llm_provider,
            api_key=self.llm_api_key or self.openrouter_api_key,
            model=self.llm_model or self.ai_model,
            fallback_model=self.llm_fallback_model or self.ai_fallback_model,
            base_url=self.llm_base_url,
            timeout=self.llm_timeout,
        )

    def get_exchange_credentials(self, exchange_type: str) -> dict:
        """Get credentials for specified exchange

        Args:
            exchange_type: Exchange type (weex, binance, bybit, okx)

        Returns:
            Dict containing api_key, api_secret, and optionally passphrase

        Raises:
            ValueError: If exchange type is not configured
        """
        credentials_map = {
            "weex": {
                "api_key": self.weex_api_key,
                "api_secret": self.weex_api_secret,
                "passphrase": self.weex_passphrase,
            },
            "binance": {
                "api_key": self.binance_api_key,
                "api_secret": self.binance_api_secret,
            },
            "bybit": {
                "api_key": self.bybit_api_key,
                "api_secret": self.bybit_api_secret,
            },
            "okx": {
                "api_key": self.okx_api_key,
                "api_secret": self.okx_api_secret,
                "passphrase": self.okx_passphrase,
            },
        }
        creds = credentials_map.get(exchange_type)
        if not creds or not creds.get("api_key") or not creds.get("api_secret"):
            raise ValueError(f"未配置{exchange_type}的API凭证")
        return creds

    @property
    def is_testnet(self) -> bool:
        """Check if running in testnet mode"""
        return self.trading_mode == "testnet"


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
