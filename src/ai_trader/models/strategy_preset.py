"""策略预设模型"""

from typing import Optional
from pydantic import BaseModel, Field


class StrategyPresetConfig(BaseModel):
    """策略预设的完整配置参数"""

    # 策略组合
    enabled_strategies: list[str]
    strategy_weights: dict[str, float]

    # 决策权重
    ai_weight: float = Field(ge=0, le=1)
    quant_weight: float = Field(ge=0, le=1)
    sentiment_weight: float = Field(ge=0, le=1, default=0)

    # 周期和频率
    timeframes: list[str]
    min_trade_interval_seconds: int = Field(ge=60)

    # 风控参数
    stop_loss_atr_multiplier: float = Field(ge=0.5)
    take_profit_atr_multiplier: float = Field(ge=0.5)
    max_position_pct: float = Field(ge=1, le=100)
    enable_pyramid: bool = False
    max_pyramid_times: int = Field(ge=0, default=0)

    # 开关和特殊参数
    enable_sentiment: bool = False
    min_profit_threshold: float = Field(ge=0, default=0)
    use_market_order_only: bool = False


class StrategyPreset(BaseModel):
    """策略预设模板"""

    id: Optional[int] = None
    name: str
    display_name: str
    description: str
    category: str
    risk_level: str
    config: StrategyPresetConfig
    is_system: bool = True
