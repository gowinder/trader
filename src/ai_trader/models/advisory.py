"""AI Advisory 模型"""
from enum import Enum
from typing import List, Dict, Any
from pydantic import BaseModel, Field


class Urgency(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SuggestionType(str, Enum):
    PARAM_ADJUST = "param_adjust"
    POSITION_ACTION = "position_action"
    SYMBOL_CHANGE = "symbol_change"


class SuggestionStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CONFIRMED = "confirmed"
    EXECUTED = "executed"
    FAILED = "failed"


class AdvisoryStatus(str, Enum):
    PENDING = "pending"
    RESOLVED = "resolved"


class TriggerType(str, Enum):
    SCHEDULED = "scheduled"
    PRICE_VOLATILITY = "price_volatility"
    CONSECUTIVE_LOSS = "consecutive_loss"
    UNREALIZED_PNL = "unrealized_pnl"
    SENTIMENT_SHIFT = "sentiment_shift"


class Suggestion(BaseModel):
    type: SuggestionType
    target: str
    action: str
    detail: Dict[str, Any] = Field(default_factory=dict)
    reasoning: str
    risk_note: str
    status: SuggestionStatus = SuggestionStatus.PENDING


class AdvisoryResult(BaseModel):
    urgency: Urgency
    suggestions: List[Suggestion]
    market_summary: str
