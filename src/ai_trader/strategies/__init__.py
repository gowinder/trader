"""Quantitative trading strategies module"""

from .pattern_recognition import PatternRecognizer, PatternType, Pattern, PatternSignal
from .market_classifier import MarketClassifier, MarketState, MarketClassification
from .strategy_base import (
    TradingStrategy,
    Signal,
    SignalAction,
    TrendFollowingStrategy,
    MeanReversionStrategy,
    BreakoutStrategy,
)
from .strategy_selector import StrategySelector, AggregatedSignal
from .signal_filter import SignalFilter

__all__ = [
    "PatternRecognizer",
    "PatternType",
    "Pattern",
    "PatternSignal",
    "MarketClassifier",
    "MarketState",
    "MarketClassification",
    "TradingStrategy",
    "Signal",
    "SignalAction",
    "TrendFollowingStrategy",
    "MeanReversionStrategy",
    "BreakoutStrategy",
    "StrategySelector",
    "AggregatedSignal",
    "SignalFilter",
]
