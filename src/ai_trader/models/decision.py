"""决策模型"""

from pydantic import BaseModel, Field
from typing import List, Literal, Optional


class TechnicalAnalysisResult(BaseModel):
    """技术分析结果"""

    trend: Literal["strong_bullish", "bullish", "neutral", "bearish", "strong_bearish"]
    trend_confidence: float = Field(ge=0, le=100)
    support_levels: List[float]
    resistance_levels: List[float]
    volume_trend: Literal["increasing", "stable", "decreasing"]
    pattern: str
    signal_strength: Literal["strong_buy", "buy", "neutral", "sell", "strong_sell"]
    key_observations: List[str]


class RiskAssessment(BaseModel):
    """风险评估结果"""

    risk_level: Literal["very_low", "low", "medium", "high", "very_high"]
    risk_score: float = Field(ge=0, le=100)
    recommended_leverage: int
    recommended_position_percent: float
    should_trade: bool
    fee_warning: bool
    risk_factors: List[str]
    mitigation_suggestions: List[str]


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
    confidence: float = Field(ge=0, le=100)
    leverage: int
    position_size_percent: float
    entry_price: float
    stop_loss_price: Optional[float]
    take_profit_price: Optional[float]
    order_type: Literal["market", "limit"]
    reasoning: str
    execution_urgency: Literal["immediate", "wait_for_price", "low_priority"]
