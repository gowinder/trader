"""决策引擎"""

from typing import Optional, Tuple
from ..models.market import MarketData
from ..models.order import Position
from ..models.decision import TradingDecision, TechnicalAnalysisResult, RiskAssessment
from .llm_client import LLMClient
from .analyzer import MarketAnalyzer
from ..prompts.risk import RISK_USER, RISK_SYSTEM, RISK_SCHEMA
from ..prompts.trading import TRADING_USER, TRADING_SYSTEM, TRADING_SCHEMA
from ..config import config


class DecisionEngine:
    """交易决策引擎"""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client
        self.analyzer = MarketAnalyzer(llm_client)

    async def analyze_and_decide(
        self,
        market_data: MarketData,
        current_position: Optional[Position],
        available_balance: float,
        total_equity: float,
    ) -> Tuple[TradingDecision, TechnicalAnalysisResult, RiskAssessment]:
        """执行完整决策流程：技术分析 -> 风险评估 -> 交易决策"""

        # 1. 技术分析
        tech_result = await self.analyzer.analyze_technical(market_data)

        # 2. 风险评估
        risk_result = await self._assess_risk(
            tech_result, market_data, current_position, available_balance, total_equity
        )

        # 3. 交易决策
        decision = await self._make_decision(
            tech_result, risk_result, market_data, current_position, available_balance
        )

        return decision, tech_result, risk_result

    async def _assess_risk(
        self,
        tech: TechnicalAnalysisResult,
        market: MarketData,
        pos: Optional[Position],
        balance: float,
        equity: float,
    ) -> RiskAssessment:
        """执行风险评估"""
        pos_info = "无持仓"
        if pos:
            pos_info = f"方向: {pos.side}, 数量: {pos.size}, 盈亏: {pos.unrealized_pnl} ({pos.roi}%)"

        # Calculate simple margin ratio (approx)
        used_margin = equity - balance
        margin_ratio = (used_margin / equity * 100) if equity > 0 else 0

        user_prompt = RISK_USER.format(
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
            recent_trade_count=0,  # TODO: Track recent trades
            recent_pnl=0.0,  # TODO: Track recent PnL
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
    ) -> TradingDecision:
        """做出最终决策"""
        pos_info = "无持仓"
        if pos:
            pos_info = f"方向: {pos.side}, 数量: {pos.size}, 均价: {pos.entry_price}, 盈亏: {pos.unrealized_pnl}"

        user_prompt = TRADING_USER.format(
            trend=tech.trend,
            trend_confidence=tech.trend_confidence,
            signal_strength=tech.signal_strength,
            support_levels=tech.support_levels,
            resistance_levels=tech.resistance_levels,
            volume_trend=tech.volume_trend,
            pattern=tech.pattern,
            key_observations=tech.key_observations,
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
            position_info=pos_info,
            strategy_type=config.trading_strategy,
            leverage_min=config.leverage_min,
            leverage_max=config.leverage_max,
            stop_loss_percent=config.stop_loss_percent,
            take_profit_percent=config.take_profit_percent,
            available_balance=f"{balance:.2f}",
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
