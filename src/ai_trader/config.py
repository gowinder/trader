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
    testnet_initial_equity: float = Field(
        default=10000.0, validation_alias="TESTNET_INITIAL_EQUITY",
        description="Testnet 虚拟账户初始权益 (USDT)",
    )

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

    # 交易对 (支持多个，逗号分隔)
    trading_symbol: str = Field(default="cmt_btcusdt")
    trading_symbols: str = Field(
        default="BTC/USDT:USDT,ETH/USDT:USDT,SOL/USDT:USDT",
        validation_alias="TRADING_SYMBOLS",
        description="多交易对配置，逗号分隔，如 'BTC/USDT:USDT,ETH/USDT:USDT'"
    )

    @property
    def symbols_list(self) -> list[str]:
        """获取交易对列表"""
        if self.trading_symbols:
            return [s.strip() for s in self.trading_symbols.split(",") if s.strip()]
        # 兼容旧版单交易对配置
        return [self.trading_symbol]

    # AI 配置 (旧版兼容) - 已废弃，使用 LLMConfig
    openrouter_api_key: str = Field(default="", validation_alias="OPENROUTER_API_KEY")
    ai_model: str = Field(default="deepseek/deepseek-v3.2", validation_alias="AI_MODEL")
    ai_fallback_model: str = Field(
        default="deepseek/deepseek-chat", validation_alias="AI_FALLBACK_MODEL"
    )

    # LLM Provider 配置 (新版)
    llm_provider: str = Field(default="openrouter", validation_alias="LLM_PROVIDER")
    llm_api_key: str = Field(default="", validation_alias="LLM_API_KEY")
    llm_model: str = Field(
        default="deepseek/deepseek-v3.2", validation_alias="LLM_MODEL"
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

    # ============= Phase 5: 情绪分析配置 =============
    # 功能开关
    enable_sentiment_analysis: bool = Field(
        default=False, description="启用情绪分析（默认关闭，需要API Key）"
    )

    # API Keys (optional)
    cryptopanic_api_key: str = Field(default="", validation_alias="CRYPTOPANIC_API_KEY")
    newsapi_key: str = Field(default="", validation_alias="NEWSAPI_KEY")

    # 情绪分析权重（仅在启用时生效）
    sentiment_weight: float = Field(default=0.2, description="情绪分析权重")

    # 缓存配置 (针对免费版 API 优化)
    # CryptoPanic: 100 req/月, NewsAPI: 100 req/天
    sentiment_cache_ttl: int = Field(default=3600, description="情绪缓存TTL（秒），默认1小时")
    sentiment_max_requests_per_hour: int = Field(
        default=4, description="每小时最大API请求数（免费版保守设置）"
    )

    # ============= Dashboard 数据库配置 =============
    dashboard_database_url: str = Field(
        default="", validation_alias="DASHBOARD_DATABASE_URL"
    )
    enable_decision_persistence: bool = Field(
        default=False, description="启用决策数据持久化到 Dashboard 数据库"
    )

    # ============= 资金安全 / 风控 =============
    daily_loss_limit_percent: float = Field(
        default=3.0, validation_alias="DAILY_LOSS_LIMIT_PERCENT",
        description="Daily max loss as % of account equity, triggers trading halt",
    )
    consecutive_halt_days_for_break: int = Field(
        default=2, validation_alias="CONSECUTIVE_HALT_DAYS_FOR_BREAK",
        description="How many consecutive halt-days trigger a forced break",
    )
    forced_break_days: int = Field(
        default=7, validation_alias="FORCED_BREAK_DAYS",
        description="Days to pause trading after consecutive halt-days exceeded",
    )
    signal_min_interval_hours: float = Field(
        default=4.0, validation_alias="SIGNAL_MIN_INTERVAL_HOURS",
        description="Min hours between same-direction open signals per symbol",
    )
    signal_reverse_cooldown_hours: float = Field(
        default=12.0, validation_alias="SIGNAL_REVERSE_COOLDOWN_HOURS",
        description="Cooldown hours before allowing direction flip (LONG->SHORT)",
    )
    min_confidence_to_trade: float = Field(
        default=60.0, validation_alias="MIN_CONFIDENCE_TO_TRADE",
        description="Min confidence score to allow opening a position",
    )
    min_confluence_to_trade: float = Field(
        default=0.5, validation_alias="MIN_CONFLUENCE_TO_TRADE",
        description="Min confluence score to allow opening a position",
    )

    # ============= 记忆与自优化配置 =============
    enable_auto_optimization: bool = Field(
        default=False, description="启用自动参数优化"
    )
    reflection_trade_count: int = Field(
        default=10, description="触发复盘的交易数量"
    )
    short_term_memory_size: int = Field(
        default=100, description="短期记忆保留笔数"
    )
    shadow_run_min_trades: int = Field(
        default=10, description="影子运行最少交易数"
    )
    redis_url: str = Field(
        default="redis://localhost:6379", description="Redis 连接 URL"
    )

    # ============= AI Advisory 配置 =============
    advisory_enabled: bool = Field(
        default=False, validation_alias="ADVISORY_ENABLED",
        description="启用 AI 顾问系统"
    )
    advisory_interval_minutes: int = Field(
        default=60, validation_alias="ADVISORY_INTERVAL_MINUTES",
        description="定时检查间隔（分钟）"
    )
    advisory_auto_execute: bool = Field(
        default=False, validation_alias="ADVISORY_AUTO_EXECUTE",
        description="自动执行 advisory 建议（跳过手动确认）"
    )

    # Advisory LLM 配置通过 Dashboard/Redis 管理，不再从 .env 读取

    # Telegram 通知
    telegram_bot_token: str = Field(
        default="", validation_alias="TELEGRAM_BOT_TOKEN"
    )
    telegram_chat_id: str = Field(
        default="", validation_alias="TELEGRAM_CHAT_ID"
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
        valid_providers = ["openrouter", "deepseek", "glm", "gemini", "qwen", "qwen-code", "codex"]
        if v.lower() not in valid_providers:
            raise ValueError(f"无效的 LLM Provider: {v}. 支持的类型: {valid_providers}")
        return v.lower()

    def apply_preset(self, config_json: dict):
        """从策略预设配置覆盖交易参数"""
        if "enabled_strategies" in config_json:
            self.enabled_strategies = config_json["enabled_strategies"]
        if "ai_weight" in config_json:
            self.ai_weight = config_json["ai_weight"]
        if "quant_weight" in config_json:
            self.quant_weight = config_json["quant_weight"]
        if "sentiment_weight" in config_json:
            self.sentiment_weight = config_json["sentiment_weight"]
        if "enable_sentiment" in config_json:
            self.enable_sentiment_analysis = config_json["enable_sentiment"]

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
