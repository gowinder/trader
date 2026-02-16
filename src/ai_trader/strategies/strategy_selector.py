"""Strategy selector and signal aggregator"""

from typing import Optional
import pandas as pd
from pydantic import BaseModel, Field

from .market_classifier import MarketState, MarketClassification
from .strategy_base import (
    TradingStrategy,
    Signal,
    SignalAction,
    TrendFollowingStrategy,
    MeanReversionStrategy,
    BreakoutStrategy,
)


class AggregatedSignal(BaseModel):
    """Aggregated signal from multiple strategies"""

    action: SignalAction = Field(..., description="Final aggregated action")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Aggregated confidence")
    entry_price: Optional[float] = Field(None, description="Aggregated entry price")
    stop_loss: Optional[float] = Field(None, description="Aggregated stop loss")
    take_profit: Optional[float] = Field(None, description="Aggregated take profit")
    contributing_strategies: list[str] = Field(..., description="Contributing strategy names")
    reason: str = Field(..., description="Aggregation reason")


class StrategySelector:
    """Strategy selector and signal aggregator"""

    def __init__(self, enabled_strategies: list[str]):
        """Initialize strategy selector

        Args:
            enabled_strategies: List of enabled strategy names
                ("trend_following", "mean_reversion", "breakout")
        """
        self.strategies: dict[str, TradingStrategy] = {}
        self._weight_overrides: dict[str, dict[str, float]] = {}

        # Initialize enabled strategies
        if "trend_following" in enabled_strategies:
            self.strategies["trend_following"] = TrendFollowingStrategy()
        if "mean_reversion" in enabled_strategies:
            self.strategies["mean_reversion"] = MeanReversionStrategy()
        if "breakout" in enabled_strategies:
            self.strategies["breakout"] = BreakoutStrategy()

    def update_weights(self, market_state: str, weights: dict[str, float]) -> None:
        """动态更新特定市场状态的策略权重"""
        self._weight_overrides[market_state] = weights

    def select_strategies(self, market_state: MarketState) -> dict[str, float]:
        """Select strategies based on market state

        优先使用动态覆盖的权重，fallback 到硬编码默认值。

        Args:
            market_state: Current market state

        Returns:
            Dict of strategy name to weight
        """
        # 优先使用动态权重覆盖
        state_key = market_state.value
        if state_key in self._weight_overrides:
            overrides = self._weight_overrides[state_key]
            # 只保留已启用策略的权重
            return {name: overrides.get(name, 0.0) for name in self.strategies}

        weights = {name: 0.0 for name in self.strategies.keys()}

        if market_state == MarketState.STRONG_TREND:
            if "trend_following" in weights:
                weights["trend_following"] = 0.7
            if "breakout" in weights:
                weights["breakout"] = 0.3

        elif market_state == MarketState.WEAK_TREND:
            if "trend_following" in weights:
                weights["trend_following"] = 0.6
            if "mean_reversion" in weights:
                weights["mean_reversion"] = 0.4

        elif market_state == MarketState.RANGE_BOUND:
            if "mean_reversion" in weights:
                weights["mean_reversion"] = 0.8
            if "trend_following" in weights:
                weights["trend_following"] = 0.2

        elif market_state == MarketState.SIDEWAYS:
            if "mean_reversion" in weights:
                weights["mean_reversion"] = 0.9
            if "trend_following" in weights:
                weights["trend_following"] = 0.1

        elif market_state == MarketState.BREAKOUT:
            if "breakout" in weights:
                weights["breakout"] = 0.8
            if "trend_following" in weights:
                weights["trend_following"] = 0.2

        return weights

    def aggregate_signals(
        self, df: pd.DataFrame, market_class: MarketClassification
    ) -> AggregatedSignal:
        """Aggregate signals from multiple strategies

        Aggregation logic:
        1. Calculate weighted score for each signal
        2. Detect conflicts (opposite signals with high confidence)
        3. Aggregate parameters (entry, stop loss, take profit)
        4. Calculate final confidence

        Args:
            df: OHLCV data
            market_class: Market classification

        Returns:
            Aggregated signal
        """
        # Get strategy weights
        strategy_weights = self.select_strategies(market_class.state)

        # Generate signals from each strategy
        signals: dict[str, tuple[Signal, float]] = {}
        for name, strategy in self.strategies.items():
            weight = strategy_weights.get(name, 0.0)
            if weight > 0:
                signal = strategy.generate_signal(df)
                signals[name] = (signal, weight)

        # If no signals, return HOLD
        if not signals:
            return AggregatedSignal(
                action=SignalAction.HOLD,
                confidence=0.0,
                contributing_strategies=[],
                reason="No active strategies",
            )

        # Calculate weighted scores by action
        action_scores: dict[SignalAction, float] = {}
        action_signals: dict[SignalAction, list[tuple[str, Signal, float]]] = {}

        for name, (signal, weight) in signals.items():
            action = signal.action
            score = signal.confidence * weight

            if action not in action_scores:
                action_scores[action] = 0.0
                action_signals[action] = []

            action_scores[action] += score
            action_signals[action].append((name, signal, weight))

        # Find best action
        best_action = max(action_scores.items(), key=lambda x: x[1])[0]
        best_score = action_scores[best_action]

        # Detect conflicts (opposite signals)
        opposite_action = self._get_opposite_action(best_action)
        opposite_score = action_scores.get(opposite_action, 0.0)

        # If opposite signal is strong (>70% of best), return HOLD
        if opposite_score > best_score * 0.7:
            return AggregatedSignal(
                action=SignalAction.HOLD,
                confidence=0.0,
                contributing_strategies=list(signals.keys()),
                reason=f"Conflicting signals: {best_action.value} ({best_score:.2f}) vs {opposite_action.value} ({opposite_score:.2f})",
            )

        # Aggregate parameters
        contributing = action_signals[best_action]
        entry_prices = [s.entry_price for _, s, _ in contributing if s.entry_price]
        stop_losses = [s.stop_loss for _, s, _ in contributing if s.stop_loss]
        take_profits = [s.take_profit for _, s, _ in contributing if s.take_profit]

        entry_price = sum(entry_prices) / len(entry_prices) if entry_prices else None
        take_profit = sum(take_profits) / len(take_profits) if take_profits else None

        # Stop loss: use conservative value
        if stop_losses:
            if best_action in [SignalAction.LONG, SignalAction.CLOSE_SHORT]:
                stop_loss = min(stop_losses)  # Most conservative for long
            else:
                stop_loss = max(stop_losses)  # Most conservative for short
        else:
            stop_loss = None

        # Calculate final confidence
        total_weight = sum(w for _, _, w in contributing)
        final_confidence = min(0.95, best_score / total_weight) if total_weight > 0 else 0.0

        # Build reason
        strategy_names = [name for name, _, _ in contributing]
        reason = f"{len(strategy_names)} strategies agree on {best_action.value}: {', '.join(strategy_names)}"

        return AggregatedSignal(
            action=best_action,
            confidence=final_confidence,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            contributing_strategies=strategy_names,
            reason=reason,
        )

    def _get_opposite_action(self, action: SignalAction) -> SignalAction:
        """Get opposite action

        Args:
            action: Current action

        Returns:
            Opposite action
        """
        opposites = {
            SignalAction.LONG: SignalAction.SHORT,
            SignalAction.SHORT: SignalAction.LONG,
            SignalAction.CLOSE_LONG: SignalAction.CLOSE_SHORT,
            SignalAction.CLOSE_SHORT: SignalAction.CLOSE_LONG,
            SignalAction.HOLD: SignalAction.HOLD,
        }
        return opposites.get(action, SignalAction.HOLD)
