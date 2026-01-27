"""Decision engine with multi-timeframe analysis and professional risk management"""

from typing import Optional, Tuple
from ..models.market import MarketData
from ..models.order import Position
from ..models.decision import TradingDecision, TechnicalAnalysisResult, RiskAssessment
from ..data.multi_timeframe import MultiTimeframeData
from .client import LLMClient
from .analyzer import MarketAnalyzer
from ..prompts.risk import RISK_USER, RISK_SYSTEM, RISK_SCHEMA
from ..prompts.trading import TRADING_USER, TRADING_SYSTEM, TRADING_SCHEMA
from ..config import config


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

        return TradingDecision(**response)
