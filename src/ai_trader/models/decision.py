"""决策模型"""

from pydantic import BaseModel, Field, PrivateAttr, field_validator
from typing import List, Literal, Optional


class TechnicalAnalysisResult(BaseModel):
    """技术分析结果"""

    trend: Literal["strong_bullish", "bullish", "neutral", "bearish", "strong_bearish"]
    trend_confidence: float = Field(default=50.0, ge=0, le=100)
    support_levels: List[float] = Field(default_factory=list)
    resistance_levels: List[float] = Field(default_factory=list)
    volume_trend: Literal["increasing", "stable", "decreasing"] = "stable"
    pattern: str = Field(default="")
    signal_strength: Literal["strong_buy", "buy", "neutral", "sell", "strong_sell"] = (
        "neutral"
    )
    key_observations: List[str] = Field(default_factory=list)


class RiskAssessment(BaseModel):
    """风险评估结果"""

    risk_level: Literal["very_low", "low", "medium", "high", "very_high"] = "medium"
    risk_score: float = Field(default=50.0, ge=0, le=100)
    recommended_leverage: int = Field(default=1, ge=1)
    recommended_position_percent: float = 10.0
    should_trade: bool = False
    fee_warning: bool = False
    risk_factors: List[str] = Field(default_factory=list)
    mitigation_suggestions: List[str] = Field(default_factory=list)


class TradingDecision(BaseModel):
    """最终交易决策"""

    action: Literal[
        "open_long",
        "open_short",
        "close_long",
        "close_short",
        "add_long",
        "add_short",
        "reduce_long",
        "reduce_short",
        "hold",
    ]
    confidence: float = Field(default=50.0, ge=0, le=100)
    leverage: int = 1
    position_size_percent: float = 10.0
    entry_price: Optional[float] = None
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    order_type: Literal["market", "limit"] = "market"
    reasoning: str = Field(default="")
    reasoning_zh: str = Field(default="")
    execution_urgency: Literal["immediate", "wait_for_price", "low_priority"] = (
        "wait_for_price"
    )
    _llm_raw_output: str = PrivateAttr(default="")

    @field_validator("leverage")
    @classmethod
    def validate_leverage(cls, v):
        if v < 1:
            return 1
        return v
