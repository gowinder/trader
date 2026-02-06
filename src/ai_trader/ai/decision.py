"""Decision engine with multi-timeframe analysis and professional risk management"""

from typing import Optional, Tuple
import pandas as pd
from ..models.market import MarketData
from ..models.order import Position
from ..models.decision import TradingDecision, TechnicalAnalysisResult, RiskAssessment
from ..data.multi_timeframe import MultiTimeframeData
from .client import LLMClient
from .analyzer import MarketAnalyzer
from ..prompts.risk import RISK_USER, RISK_SYSTEM, RISK_SCHEMA
from ..prompts.trading import TRADING_USER, TRADING_SYSTEM, TRADING_SCHEMA
from ..config import config

# Phase 4: Import quantitative strategy modules
from ..strategies.pattern_recognition import PatternRecognizer
from ..strategies.market_classifier import MarketClassifier, MarketState
from ..strategies.strategy_selector import StrategySelector
from ..strategies.strategy_base import SignalAction


class DecisionEngine:
    """Trading decision engine with multi-timeframe analysis support"""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client
        self.analyzer = MarketAnalyzer(llm_client)

    async def analyze_and_decide(
        self,
        market_data: MarketData,
        current_position: Optional[Position],
        available_balance: float,
        total_equity: float,
        mtf_data: Optional[MultiTimeframeData] = None,
        daily_pnl: float = 0.0,
        trades_today: int = 0,
        consecutive_losses: int = 0,
        emotional_state: str = "calm",
    ) -> Tuple[TradingDecision, TechnicalAnalysisResult, RiskAssessment]:
        """Execute complete decision flow: technical analysis -> risk assessment -> trading decision

        Args:
            market_data: Current market data for decision timeframe
            current_position: Current position if any
            available_balance: Available balance in USDT
            total_equity: Total account equity
            mtf_data: Multi-timeframe analysis data (optional)
            daily_pnl: Today's total P&L
            trades_today: Number of trades executed today
            consecutive_losses: Number of consecutive losing trades
            emotional_state: Current emotional state

        Returns:
            Tuple of (trading decision, technical analysis, risk assessment)
        """

        # 1. Technical analysis
        tech_result = await self.analyzer.analyze_technical(market_data)

        # 2. Risk assessment
        risk_result = await self._assess_risk(
            tech_result,
            market_data,
            current_position,
            available_balance,
            total_equity,
            mtf_data,
            daily_pnl,
            consecutive_losses,
        )

        # 3. Trading decision
        decision = await self._make_decision(
            tech_result,
            risk_result,
            market_data,
            current_position,
            available_balance,
            mtf_data,
            daily_pnl,
            trades_today,
            consecutive_losses,
            emotional_state,
        )

        return decision, tech_result, risk_result

    async def _assess_risk(
        self,
        tech: TechnicalAnalysisResult,
        market: MarketData,
        pos: Optional[Position],
        balance: float,
        equity: float,
        mtf_data: Optional[MultiTimeframeData],
        daily_pnl: float,
        consecutive_losses: int,
    ) -> RiskAssessment:
        """Execute risk assessment with multi-timeframe and discipline constraints"""
        pos_info = "No position"
        if pos:
            pos_info = f"Direction: {pos.side}, Size: {pos.size}, PnL: {pos.unrealized_pnl} ({pos.roi}%)"

        # Calculate margin ratio
        used_margin = equity - balance
        margin_ratio = (used_margin / equity * 100) if equity > 0 else 0

        # Build multi-timeframe summary
        mtf_summary = "No multi-timeframe data available"
        if mtf_data:
            mtf_summary = f"""- Overall Trend: {mtf_data.overall_trend.value.upper()}
- Confluence Score: {mtf_data.confluence_score:.2%}
- Recommended Action: {mtf_data.recommended_action.upper()}
- Timeframes Analyzed: {', '.join(mtf_data.analyses.keys())}
- Alignment Quality: {'HIGH' if mtf_data.confluence_score >= 0.7 else 'MEDIUM' if mtf_data.confluence_score >= 0.5 else 'LOW'}"""

        # Calculate current risk exposure
        current_risk_exposure = (used_margin / equity * 100) if equity > 0 else 0

        # Daily loss limit check
        daily_loss_limit = 3.0  # 3% default
        consecutive_loss_days = max(0, consecutive_losses // 3)  # Approximate

        user_prompt = RISK_USER.format(
            mtf_summary=mtf_summary,
            trend=tech.trend,
            trend_confidence=tech.trend_confidence,
            signal_strength=tech.signal_strength,
            support_levels=tech.support_levels,
            resistance_levels=tech.resistance_levels,
            volume_trend=tech.volume_trend,
            pattern=tech.pattern,
            key_observations=tech.key_observations,
            available_balance=f"{balance:.2f}",
            total_equity=f"{equity:.2f}",
            used_margin=f"{used_margin:.2f}",
            margin_ratio=f"{margin_ratio:.2f}",
            position_info=pos_info,
            strategy_type=config.trading_strategy,
            leverage_min=config.leverage_min,
            leverage_max=config.leverage_max,
            max_position_percent=config.max_position_percent,
            stop_loss_percent=config.stop_loss_percent,
            take_profit_percent=config.take_profit_percent,
            recent_trade_count=0,  # TODO: Track from journal
            recent_pnl=0.0,  # TODO: Track from journal
            daily_pnl=f"{daily_pnl:+.2f}",
            consecutive_loss_days=consecutive_loss_days,
            daily_loss_limit=daily_loss_limit,
            current_risk_exposure=f"{current_risk_exposure:.2f}",
        )

        response = await self.llm.chat(
            messages=[
                {"role": "system", "content": RISK_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            schema=RISK_SCHEMA,
            max_tokens=1500,
        )

        return RiskAssessment(**response)

    async def _make_decision(
        self,
        tech: TechnicalAnalysisResult,
        risk: RiskAssessment,
        market: MarketData,
        pos: Optional[Position],
        balance: float,
        mtf_data: Optional[MultiTimeframeData],
        daily_pnl: float,
        trades_today: int,
        consecutive_losses: int,
        emotional_state: str,
    ) -> TradingDecision:
        """Make final trading decision with multi-timeframe and discipline constraints"""
        pos_info = "No position"
        position_performance = ""
        position_management_context = "No active position - evaluate new entry conditions"

        if pos:
            pos_info = f"Direction: {pos.side}, Size: {pos.size}, Entry: {pos.entry_price}, PnL: {pos.unrealized_pnl}"

            # Calculate position performance metrics
            profit_pct = pos.roi if hasattr(pos, "roi") else 0.0
            position_performance = f"""
- Unrealized P&L: {pos.unrealized_pnl:+.2f} USDT ({profit_pct:+.2f}%)
- Entry Price: {pos.entry_price}
- Current Price: {market.current_price}
- Position Move: {profit_pct:+.2f}%"""

            # Position management context based on profit level
            if profit_pct > 10:
                position_management_context = "Position in Phase 4 (>10% profit) - Consider aggressive trailing stop (1-1.5× ATR) or partial profit taking"
            elif profit_pct > 4:
                position_management_context = "Position in Phase 3 (4-10% profit) - Trail with 50% profit protection or consider adding if trend strong"
            elif profit_pct > 2:
                position_management_context = "Position in Phase 2 (2-4% profit) - Move stop to break-even, evaluate pyramid scaling if trend continues"
            elif profit_pct > 0:
                position_management_context = "Position in Phase 1 (0-2% profit) - Keep initial stop, no adjustments yet"
            else:
                position_management_context = f"Position underwater ({profit_pct:.2f}%) - Respect stop loss, do not average down"

        # Build multi-timeframe summary
        mtf_summary = "No multi-timeframe data available - using single timeframe analysis"
        if mtf_data:
            mtf_summary = f"""- Overall Trend: {mtf_data.overall_trend.value.upper()}
- Confluence Score: {mtf_data.confluence_score:.2%}
- Recommended Action: {mtf_data.recommended_action.upper()}
- Timeframes Analyzed: {', '.join(mtf_data.analyses.keys())}
- Alignment Quality: {'HIGH (≥0.7)' if mtf_data.confluence_score >= 0.7 else 'MEDIUM (0.5-0.7)' if mtf_data.confluence_score >= 0.5 else 'LOW (<0.5)'}

⚠️ TRADING RULE: {'Confluence < 0.5 → MUST HOLD' if mtf_data.confluence_score < 0.5 else 'Confluence ≥ 0.7 → High confidence setup' if mtf_data.confluence_score >= 0.7 else 'Confluence 0.5-0.7 → Moderate setup'}"""

        # Limit key_observations to top 3 to save tokens
        obs_str = str(tech.key_observations[:3]) if tech.key_observations else "[]"

        # Get ATR from market indicators
        atr = market.indicators.atr if market.indicators else 0.0

        # Calculate recent win rate (placeholder - should come from journal)
        recent_win_rate = 0.0  # TODO: Calculate from recent trades

        user_prompt = TRADING_USER.format(
            mtf_summary=mtf_summary,
            trend=tech.trend,
            trend_confidence=tech.trend_confidence,
            signal_strength=tech.signal_strength,
            support_levels=tech.support_levels,
            resistance_levels=tech.resistance_levels,
            volume_trend=tech.volume_trend,
            pattern=tech.pattern,
            key_observations=obs_str,
            risk_level=risk.risk_level,
            risk_score=risk.risk_score,
            recommended_leverage=risk.recommended_leverage,
            recommended_position_percent=risk.recommended_position_percent,
            should_trade=risk.should_trade,
            fee_warning=risk.fee_warning,
            risk_factors=risk.risk_factors,
            mitigation_suggestions=risk.mitigation_suggestions,
            current_price=market.current_price,
            change_24h=market.change_24h,
            atr=f"{atr:.2f}",
            position_info=pos_info,
            position_performance=position_performance,
            daily_pnl=f"{daily_pnl:+.2f}",
            trades_today=trades_today,
            recent_win_rate=f"{recent_win_rate:.1f}",
            consecutive_losses=consecutive_losses,
            emotional_state=emotional_state,
            strategy_type=config.trading_strategy,
            leverage_min=config.leverage_min,
            leverage_max=config.leverage_max,
            stop_loss_percent=config.stop_loss_percent,
            take_profit_percent=config.take_profit_percent,
            available_balance=f"{balance:.2f}",
            position_management_context=position_management_context,
        )

        response = await self.llm.chat(
            messages=[
                {"role": "system", "content": TRADING_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            schema=TRADING_SCHEMA,
            max_tokens=1000,
        )

        decision = TradingDecision(**response)

        # Fill in missing price fields based on current price and ATR
        if decision.action in ["open_long", "open_short", "add_long", "add_short"]:
            current_price = market.current_price

            # Entry price: use current price if not set
            if decision.entry_price is None:
                decision.entry_price = current_price

            # Calculate stop loss and take profit based on ATR if not set
            if atr > 0:
                # Stop loss: 2x ATR from entry
                if decision.stop_loss_price is None:
                    if "long" in decision.action:
                        decision.stop_loss_price = current_price - (2.0 * atr)
                    else:  # short
                        decision.stop_loss_price = current_price + (2.0 * atr)

                # Take profit: 3x ATR from entry (1.5:1 risk-reward)
                if decision.take_profit_price is None:
                    if "long" in decision.action:
                        decision.take_profit_price = current_price + (3.0 * atr)
                    else:  # short
                        decision.take_profit_price = current_price - (3.0 * atr)
            else:
                # Fallback to percentage-based if ATR not available
                stop_pct = config.stop_loss_percent / 100.0
                tp_pct = config.take_profit_percent / 100.0

                if decision.stop_loss_price is None:
                    if "long" in decision.action:
                        decision.stop_loss_price = current_price * (1 - stop_pct)
                    else:
                        decision.stop_loss_price = current_price * (1 + stop_pct)

                if decision.take_profit_price is None:
                    if "long" in decision.action:
                        decision.take_profit_price = current_price * (1 + tp_pct)
                    else:
                        decision.take_profit_price = current_price * (1 - tp_pct)

            logger.info(
                f"Decision prices: entry={decision.entry_price:.2f}, "
                f"stop={decision.stop_loss_price:.2f}, "
                f"tp={decision.take_profit_price:.2f}"
            )

        return decision


class HybridDecisionEngine(DecisionEngine):
    """Hybrid decision engine integrating AI and quantitative strategies

    Decision flow:
    1. Market state classification
    2. K-line pattern recognition
    3. Quantitative strategy signal aggregation
    4. AI technical analysis + risk assessment + decision
    5. Hybrid decision fusion
    """

    def __init__(self, llm_client: LLMClient):
        super().__init__(llm_client)

        # Initialize quantitative modules if enabled
        self.pattern_recognizer = (
            PatternRecognizer() if config.enable_pattern_recognition else None
        )
        self.market_classifier = MarketClassifier()
        self.strategy_selector = (
            StrategySelector(config.enabled_strategies)
            if config.enable_quant_strategies
            else None
        )

    async def analyze_and_decide(
        self,
        market_data: MarketData,
        current_position: Optional[Position],
        available_balance: float,
        total_equity: float,
        mtf_data: Optional[MultiTimeframeData] = None,
        daily_pnl: float = 0.0,
        trades_today: int = 0,
        consecutive_losses: int = 0,
        emotional_state: str = "calm",
    ) -> Tuple[TradingDecision, TechnicalAnalysisResult, RiskAssessment]:
        """Execute hybrid decision flow with quantitative and AI integration

        Args:
            Same as DecisionEngine.analyze_and_decide

        Returns:
            Tuple of (hybrid trading decision, technical analysis, risk assessment)
        """
        # Prepare market data as DataFrame for quantitative analysis
        df = self._prepare_dataframe(market_data)

        # Step 1: Market state classification
        market_class = self.market_classifier.classify(df)

        # Step 2: Pattern recognition
        patterns = []
        if self.pattern_recognizer:
            patterns = self.pattern_recognizer.detect_all(df)

        # Step 3: Quantitative strategy signal aggregation
        quant_signal = None
        if self.strategy_selector:
            quant_signal = self.strategy_selector.aggregate_signals(df, market_class)

        # Step 4: AI analysis (technical, risk, decision)
        ai_decision, tech_result, risk_result = await super().analyze_and_decide(
            market_data=market_data,
            current_position=current_position,
            available_balance=available_balance,
            total_equity=total_equity,
            mtf_data=mtf_data,
            daily_pnl=daily_pnl,
            trades_today=trades_today,
            consecutive_losses=consecutive_losses,
            emotional_state=emotional_state,
        )

        # Step 5: Hybrid decision fusion
        final_decision = self._fuse_decisions(
            quant_signal=quant_signal,
            ai_decision=ai_decision,
            market_class=market_class,
            patterns=patterns,
        )

        return final_decision, tech_result, risk_result

    def _prepare_dataframe(self, market_data: MarketData) -> pd.DataFrame:
        """Prepare OHLCV DataFrame from market data

        Args:
            market_data: Market data object

        Returns:
            DataFrame with columns: open, high, low, close, volume
        """
        # Convert klines to DataFrame
        if not market_data.klines:
            # Fallback: create single row from current data
            return pd.DataFrame(
                {
                    "open": [market_data.current_price],
                    "high": [market_data.high_24h],
                    "low": [market_data.low_24h],
                    "close": [market_data.current_price],
                    "volume": [market_data.volume_24h],
                }
            )

        data = []
        for kline in market_data.klines:
            data.append(
                {
                    "open": kline["open"],
                    "high": kline["high"],
                    "low": kline["low"],
                    "close": kline["close"],
                    "volume": kline["volume"],
                }
            )

        return pd.DataFrame(data)

    def _fuse_decisions(
        self,
        quant_signal,
        ai_decision: TradingDecision,
        market_class,
        patterns: list,
    ) -> TradingDecision:
        """Fuse quantitative and AI decisions

        Fusion rules:
        1. Double confirmation (quant + AI agree): boost confidence
        2. Strong trend (ADX > 25): quant weight 0.7, AI weight 0.3
        3. Range bound / sideways: quant weight 0.4, AI weight 0.6
        4. Conflict (opposite signals): return HOLD

        Args:
            quant_signal: Quantitative aggregated signal (or None)
            ai_decision: AI trading decision
            market_class: Market classification
            patterns: Detected patterns

        Returns:
            Final hybrid decision
        """
        # If no quant signal, use AI decision
        if not quant_signal:
            return ai_decision

        # Map SignalAction to TradingDecision action
        quant_action = self._map_signal_action(quant_signal.action)
        ai_action = ai_decision.action

        # Check for double confirmation
        if self._actions_aligned(quant_action, ai_action):
            # Both agree - boost confidence
            final_confidence = max(
                quant_signal.confidence * 100, ai_decision.confidence
            ) + 15.0
            final_confidence = min(95.0, final_confidence)

            # Use more conservative stop loss
            final_stop_loss = self._conservative_stop_loss(
                quant_signal.stop_loss, ai_decision.stop_loss_price, quant_action
            )

            # Average take profit
            final_take_profit = self._average_take_profit(
                quant_signal.take_profit, ai_decision.take_profit_price
            )

            return TradingDecision(
                action=quant_action,
                confidence=final_confidence,
                leverage=ai_decision.leverage,
                position_size_percent=ai_decision.position_size_percent,
                entry_price=quant_signal.entry_price or ai_decision.entry_price,
                stop_loss_price=final_stop_loss,
                take_profit_price=final_take_profit,
                order_type=ai_decision.order_type,
                reasoning=f"DOUBLE CONFIRMATION - Quant ({quant_signal.confidence:.0%}) + AI ({ai_decision.confidence:.0f}%) agree. Market: {market_class.state.value}, {quant_signal.reason}",
                execution_urgency=ai_decision.execution_urgency,
            )

        # Check for conflict
        if self._actions_conflict(quant_action, ai_action):
            return TradingDecision(
                action="hold",
                confidence=50.0,
                leverage=1,
                position_size_percent=0.0,
                reasoning=f"CONFLICT - Quant suggests {quant_action}, AI suggests {ai_action}. Market: {market_class.state.value}. Waiting for alignment.",
                execution_urgency="low_priority",
            )

        # Weight-based fusion
        if market_class.state == MarketState.STRONG_TREND:
            # Strong trend: favor quantitative (0.7 vs 0.3)
            quant_weight = config.quant_weight * 1.4  # 0.7
            ai_weight = config.ai_weight * 0.6  # 0.3
        elif market_class.state in [MarketState.RANGE_BOUND, MarketState.SIDEWAYS]:
            # Range bound: favor AI (0.4 vs 0.6)
            quant_weight = config.quant_weight * 0.8  # 0.4
            ai_weight = config.ai_weight * 1.2  # 0.6
        else:
            # Default weights
            quant_weight = config.quant_weight
            ai_weight = config.ai_weight

        # Calculate weighted scores
        quant_score = quant_signal.confidence * 100 * quant_weight
        ai_score = ai_decision.confidence * ai_weight

        # Choose action with higher score
        if quant_score > ai_score:
            final_action = quant_action
            final_confidence = min(95.0, quant_signal.confidence * 100)
            final_stop_loss = quant_signal.stop_loss
            final_take_profit = quant_signal.take_profit
            final_entry = quant_signal.entry_price
            reason_prefix = f"QUANT PRIORITY ({quant_score:.0f} vs {ai_score:.0f})"
        else:
            final_action = ai_action
            final_confidence = min(95.0, ai_decision.confidence)
            final_stop_loss = ai_decision.stop_loss_price
            final_take_profit = ai_decision.take_profit_price
            final_entry = ai_decision.entry_price
            reason_prefix = f"AI PRIORITY ({ai_score:.0f} vs {quant_score:.0f})"

        return TradingDecision(
            action=final_action,
            confidence=final_confidence,
            leverage=ai_decision.leverage,
            position_size_percent=ai_decision.position_size_percent,
            entry_price=final_entry,
            stop_loss_price=final_stop_loss,
            take_profit_price=final_take_profit,
            order_type=ai_decision.order_type,
            reasoning=f"{reason_prefix} - Market: {market_class.state.value} (ADX: {market_class.adx_value:.1f}). {ai_decision.reasoning}",
            execution_urgency=ai_decision.execution_urgency,
        )

    def _map_signal_action(self, signal_action: SignalAction) -> str:
        """Map SignalAction to TradingDecision action string"""
        mapping = {
            SignalAction.LONG: "open_long",
            SignalAction.SHORT: "open_short",
            SignalAction.CLOSE_LONG: "close_long",
            SignalAction.CLOSE_SHORT: "close_short",
            SignalAction.HOLD: "hold",
        }
        return mapping.get(signal_action, "hold")

    def _actions_aligned(self, action1: str, action2: str) -> bool:
        """Check if two actions are aligned (same direction)"""
        long_actions = ["open_long", "add_long"]
        short_actions = ["open_short", "add_short"]
        close_long_actions = ["close_long", "reduce_long"]
        close_short_actions = ["close_short", "reduce_short"]

        if action1 in long_actions and action2 in long_actions:
            return True
        if action1 in short_actions and action2 in short_actions:
            return True
        if action1 in close_long_actions and action2 in close_long_actions:
            return True
        if action1 in close_short_actions and action2 in close_short_actions:
            return True

        return action1 == action2

    def _actions_conflict(self, action1: str, action2: str) -> bool:
        """Check if two actions conflict (opposite directions)"""
        long_actions = ["open_long", "add_long"]
        short_actions = ["open_short", "add_short"]

        if (action1 in long_actions and action2 in short_actions) or (
            action1 in short_actions and action2 in long_actions
        ):
            return True

        return False

    def _conservative_stop_loss(
        self, quant_sl: Optional[float], ai_sl: Optional[float], action: str
    ) -> Optional[float]:
        """Choose more conservative stop loss"""
        if not quant_sl:
            return ai_sl
        if not ai_sl:
            return quant_sl

        # For long positions, higher stop loss is more conservative
        if action in ["open_long", "add_long"]:
            return max(quant_sl, ai_sl)
        # For short positions, lower stop loss is more conservative
        else:
            return min(quant_sl, ai_sl)

    def _average_take_profit(
        self, quant_tp: Optional[float], ai_tp: Optional[float]
    ) -> Optional[float]:
        """Average take profit prices"""
        if not quant_tp:
            return ai_tp
        if not ai_tp:
            return quant_tp
        return (quant_tp + ai_tp) / 2
