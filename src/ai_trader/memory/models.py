"""记忆系统数据模型"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
from enum import Enum


class RuleStatus(str, Enum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


@dataclass
class TradeMemoryEntry:
    """短期记忆条目 - 单笔交易完整上下文"""

    # 基础信息
    trade_id: str
    timestamp: datetime
    symbol: str

    # 决策快照
    action: str
    confidence: float
    leverage: float
    reasoning: str

    # 市场上下文
    market_state: str
    timeframe_alignment: dict = field(default_factory=dict)
    technical_snapshot: dict = field(default_factory=dict)
    patterns_detected: list[str] = field(default_factory=list)

    # 结果
    entry_price: float = 0.0
    exit_price: Optional[float] = None
    pnl_percent: Optional[float] = None
    max_adverse_excursion: float = 0.0
    max_favorable_excursion: float = 0.0
    holding_duration: Optional[timedelta] = None

    # 分析维度
    hour_of_day: int = 0
    day_of_week: int = 0
    consecutive_losses: int = 0
    is_winner: Optional[bool] = None

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "trade_id": self.trade_id,
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "action": self.action,
            "confidence": self.confidence,
            "leverage": self.leverage,
            "reasoning": self.reasoning,
            "market_state": self.market_state,
            "timeframe_alignment": self.timeframe_alignment,
            "technical_snapshot": self.technical_snapshot,
            "patterns_detected": self.patterns_detected,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "pnl_percent": self.pnl_percent,
            "max_adverse_excursion": self.max_adverse_excursion,
            "max_favorable_excursion": self.max_favorable_excursion,
            "holding_duration": str(self.holding_duration) if self.holding_duration else None,
            "hour_of_day": self.hour_of_day,
            "day_of_week": self.day_of_week,
            "consecutive_losses": self.consecutive_losses,
            "is_winner": self.is_winner,
        }


@dataclass
class DistilledRule:
    """长期记忆条目 - 提炼后的规则"""

    rule_id: str
    condition: dict
    recommendation: dict

    # 统计验证
    sample_size: int
    win_rate: float
    avg_pnl: float
    p_value: float

    # 元数据
    reasoning: str = ""
    status: str = RuleStatus.CANDIDATE.value
    validation_count: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    last_validated: Optional[datetime] = None

    # 验证阈值
    P_VALUE_THRESHOLD: float = field(default=0.05, repr=False)
    MIN_SAMPLE_SIZE: int = field(default=20, repr=False)

    def is_statistically_valid(self) -> bool:
        """检查规则是否通过统计验证"""
        return (
            self.p_value < self.P_VALUE_THRESHOLD
            and self.sample_size >= self.MIN_SAMPLE_SIZE
        )

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "rule_id": self.rule_id,
            "condition": self.condition,
            "recommendation": self.recommendation,
            "sample_size": self.sample_size,
            "win_rate": self.win_rate,
            "avg_pnl": self.avg_pnl,
            "p_value": self.p_value,
            "reasoning": self.reasoning,
            "status": self.status,
            "validation_count": self.validation_count,
            "created_at": self.created_at.isoformat(),
            "last_validated": self.last_validated.isoformat() if self.last_validated else None,
        }
