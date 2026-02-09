"""Hybrid decision engine with quantitative, AI, and sentiment analysis

Phase 5: Integrated sentiment analysis into decision making
Phase 6: Decision persistence to Dashboard database
"""

from typing import Optional, Tuple
import pandas as pd

from ..models.market import MarketData
from ..models.order import Position
from ..models.decision import TradingDecision, TechnicalAnalysisResult, RiskAssessment
from ..data.multi_timeframe import MultiTimeframeData
from .client import LLMClient
from .decision import DecisionEngine
from ..sentiment.analyzer import SentimentAnalyzer, SentimentResult
from ..sentiment.data_sources import CryptoPanicSource, NewsAPISource
from ..sentiment.cache import SentimentCache
from ..strategies.market_classifier import MarketClassifier
from ..strategies.strategy_selector import StrategySelector
from ..strategies.strategy_base import SignalAction
from ..persistence import DatabaseManager, DecisionPersistenceService
from ..config import config
from ..utils.logger import logger


class HybridDecisionEngine(DecisionEngine):
    """Hybrid decision engine with sentiment analysis integration

    Decision weights (configurable):
    - Quantitative strategies: quant_weight (default: 0.5)
    - AI analysis: ai_weight (default: 0.5)
    - Sentiment analysis: sentiment_weight (default: 0.2, only if enabled)

    When sentiment is enabled, weights are normalized to sum to 1.0
    When sentiment is disabled, quant + AI weights are normalized to 1.0
    """

    def __init__(self, llm_client: LLMClient):
        """Initialize hybrid decision engine

        Args:
            llm_client: LLM client for AI analysis and sentiment analysis
        """
        super().__init__(llm_client)

        # Phase 4: Quantitative strategy components
        if config.enable_quant_strategies:
            self.market_classifier = MarketClassifier()
            self.strategy_selector = StrategySelector(config.enabled_strategies)
        else:
            self.market_classifier = None
            self.strategy_selector = None

        # Phase 5: Sentiment analysis components
        self.sentiment_analyzer: Optional[SentimentAnalyzer] = None
        if config.enable_sentiment_analysis:
            self._init_sentiment_analyzer()

        # Phase 6: Decision persistence
        self.db_manager: Optional[DatabaseManager] = None
        self.persistence_service: Optional[DecisionPersistenceService] = None
        self._persistence_initialized = False

        # 当前激活的策略预设名称
        self.active_preset_name: Optional[str] = None

    def _init_sentiment_analyzer(self):
        """Initialize sentiment analyzer with configured data sources"""
        data_sources = []

        # Add CryptoPanic source
        if config.cryptopanic_api_key:
            data_sources.append(
                CryptoPanicSource(api_key=config.cryptopanic_api_key)
            )
            logger.info("CryptoPanic sentiment source enabled")
        else:
            logger.warning("CryptoPanic API key not configured")

        # Add NewsAPI source
        if config.newsapi_key:
            data_sources.append(NewsAPISource(api_key=config.newsapi_key))
            logger.info("NewsAPI sentiment source enabled")
        else:
            logger.warning("NewsAPI key not configured")

        if not data_sources:
            logger.warning("No sentiment data sources configured, sentiment analysis disabled")
            config.enable_sentiment_analysis = False
            return

        # Create sentiment analyzer
        cache = SentimentCache(
            default_ttl=config.sentiment_cache_ttl,
            max_requests_per_hour=config.sentiment_max_requests_per_hour,
        )

        self.sentiment_analyzer = SentimentAnalyzer(
            data_sources=data_sources,
            llm_client=self.llm,
            cache=cache,
            min_news_count=3,
        )

        logger.info("Sentiment analyzer initialized")

    async def _init_persistence(self):
        """Initialize decision persistence service"""
        if self._persistence_initialized:
            return

        if not config.enable_decision_persistence:
            return

        if not config.dashboard_database_url:
            logger.warning("Dashboard database URL not configured, persistence disabled")
            return

        try:
            self.db_manager = DatabaseManager(config.dashboard_database_url)
            await self.db_manager.connect()
            self.persistence_service = DecisionPersistenceService(self.db_manager)
            self._persistence_initialized = True
            logger.info("Decision persistence service initialized")
        except Exception as e:
            logger.error(f"Failed to initialize persistence service: {e}")
            self.db_manager = None
            self.persistence_service = None

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
        """Execute hybrid decision flow with sentiment analysis

        Flow:
        1. Technical analysis (AI)
        2. Quantitative strategy signals (if enabled)
        3. Sentiment analysis (if enabled)
        4. Risk assessment
        5. Hybrid decision fusion

        Args:
            market_data: Current market data
            current_position: Current position if any
            available_balance: Available balance
            total_equity: Total equity
            mtf_data: Multi-timeframe data
            daily_pnl: Today's P&L
            trades_today: Today's trade count
            consecutive_losses: Consecutive losses
            emotional_state: Emotional state

        Returns:
            Tuple of (decision, technical analysis, risk assessment)
        """
        # Initialize persistence if enabled
        await self._init_persistence()

        # Step 1: Technical analysis (AI)
        tech_result = await self.analyzer.analyze_technical(market_data)

        # Step 2: Quantitative strategy signals
        quant_signal = None
        if self.strategy_selector and config.enable_quant_strategies:
            try:
                # Classify market state
                # Convert Kline objects to dicts for DataFrame
                klines_data = [k.model_dump() for k in market_data.klines]
                df = pd.DataFrame(klines_data)
                market_state = self.market_classifier.classify(df)

                # Generate quantitative signal
                quant_signal = self.strategy_selector.aggregate_signals(df, market_state)

                logger.info(
                    f"Quant signal: {quant_signal.action.value}, "
                    f"confidence: {quant_signal.confidence:.2f}"
                )
            except Exception as e:
                logger.error(f"Quantitative analysis failed: {e}")

        # Step 3: Sentiment analysis
        sentiment_result: Optional[SentimentResult] = None
        if self.sentiment_analyzer and config.enable_sentiment_analysis:
            try:
                # Get current price and 24h change from MarketData
                current_price = market_data.current_price
                # Use change_24h from market_data if available
                price_change_24h = market_data.change_24h if market_data.change_24h else None

                sentiment_result = await self.sentiment_analyzer.analyze(
                    symbol=market_data.symbol,
                    current_price=current_price,
                    price_change_24h=price_change_24h,
                )

                if sentiment_result:
                    logger.info(
                        f"Sentiment: {sentiment_result.score.value}, "
                        f"confidence: {sentiment_result.confidence:.2f}, "
                        f"news: {sentiment_result.news_count}, "
                        f"risk_event: {sentiment_result.risk_event}, "
                        f"extreme_fear: {sentiment_result.extreme_fear}, "
                        f"extreme_greed: {sentiment_result.extreme_greed}"
                    )
            except Exception as e:
                logger.error(f"Sentiment analysis failed: {e}")

        # Step 4: Risk assessment
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

        # Step 5: Hybrid decision
        decision = await self._make_hybrid_decision(
            tech_result=tech_result,
            risk_result=risk_result,
            quant_signal=quant_signal,
            sentiment_result=sentiment_result,
            market_data=market_data,
            current_position=current_position,
            available_balance=available_balance,
            mtf_data=mtf_data,
            daily_pnl=daily_pnl,
            trades_today=trades_today,
            consecutive_losses=consecutive_losses,
            emotional_state=emotional_state,
        )

        # Step 6: Persist decision to database
        if self.persistence_service:
            try:
                await self.persistence_service.save_decision(
                    decision=decision,
                    technical=tech_result,
                    risk=risk_result,
                    market_data=market_data,
                    sentiment=sentiment_result,
                    llm_provider=config.llm_provider,
                    llm_model=config.llm_model,
                    strategy_preset=self.active_preset_name,
                )
            except Exception as e:
                logger.error(f"Failed to persist decision: {e}")

        return decision, tech_result, risk_result

    async def _make_hybrid_decision(
        self,
        tech_result: TechnicalAnalysisResult,
        risk_result: RiskAssessment,
        quant_signal: Optional[any],
        sentiment_result: Optional[SentimentResult],
        market_data: MarketData,
        current_position: Optional[Position],
        available_balance: float,
        mtf_data: Optional[MultiTimeframeData],
        daily_pnl: float,
        trades_today: int,
        consecutive_losses: int,
        emotional_state: str,
    ) -> TradingDecision:
        """Make hybrid trading decision by fusing multiple signals

        Fusion logic:
        1. Calculate weighted scores for each enabled component
        2. Normalize weights to sum to 1.0
        3. Apply sentiment adjustments (if enabled)
        4. Make final decision based on fused signal

        Args:
            tech_result: Technical analysis result
            risk_result: Risk assessment result
            quant_signal: Quantitative strategy signal (optional)
            sentiment_result: Sentiment analysis result (optional)
            ... (other parameters)

        Returns:
            Trading decision
        """

        # Call base AI decision (this generates AI signal)
        base_decision = await self._make_decision(
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

        # If quant strategies not enabled, return base decision
        if not quant_signal and not sentiment_result:
            return base_decision

        # Fusion logic: weighted combination
        # Normalize weights
        weights = {
            "ai": config.ai_weight,
            "quant": config.quant_weight if quant_signal else 0.0,
            "sentiment": config.sentiment_weight if sentiment_result else 0.0,
        }

        total_weight = sum(weights.values())
        if total_weight > 0:
            weights = {k: v / total_weight for k, v in weights.items()}

        logger.info(f"Decision weights: {weights}")

        # Convert signals to numeric scores (-1 to +1)
        # AI signal
        ai_score = 0.0
        if "long" in base_decision.action.lower():
            ai_score = 0.5
        elif "short" in base_decision.action.lower():
            ai_score = -0.5

        ai_confidence = base_decision.confidence / 100.0  # Normalize to 0-1

        # Quant signal
        quant_score = 0.0
        quant_confidence = 0.0
        if quant_signal:
            if quant_signal.action == SignalAction.LONG:
                quant_score = 0.5
            elif quant_signal.action == SignalAction.SHORT:
                quant_score = -0.5
            quant_confidence = quant_signal.confidence

        # Sentiment adjustment
        sentiment_adjustment = 0.0
        if sentiment_result:
            sentiment_adjustment = sentiment_result.get_sentiment_adjustment()
            logger.info(f"Sentiment adjustment: {sentiment_adjustment:+.2f}")

        # Calculate weighted direction score (decoupled from confidence)
        weighted_direction = (
            ai_score * weights["ai"] +
            quant_score * weights["quant"]
        )

        # Apply sentiment adjustment
        final_score = weighted_direction + sentiment_adjustment * weights.get("sentiment", 0.0)

        # Calculate weighted confidence (all in 0-1 scale)
        final_confidence = (
            ai_confidence * weights["ai"] +
            quant_confidence * weights["quant"]
        )

        if sentiment_result:
            final_confidence += sentiment_result.confidence * weights["sentiment"]

        # Determine final action
        SCORE_THRESHOLD = 0.15
        CONFIDENCE_THRESHOLD = 0.5
        action = "hold"
        if final_score > SCORE_THRESHOLD and final_confidence > CONFIDENCE_THRESHOLD:
            action = "open_long"
        elif final_score < -SCORE_THRESHOLD and final_confidence > CONFIDENCE_THRESHOLD:
            action = "open_short"

        # Apply sentiment safety checks
        if sentiment_result:
            # Extreme fear: reduce bearish, encourage contrarian long
            if sentiment_result.extreme_fear and action == "open_short":
                action = "hold"
                logger.info("Sentiment override: extreme fear, avoiding short")

            # Extreme greed: reduce bullish, encourage contrarian short
            if sentiment_result.extreme_greed and action == "open_long":
                action = "hold"
                logger.info("Sentiment override: extreme greed, avoiding long")

            # Risk event: hold all positions
            if sentiment_result.risk_event:
                action = "hold"
                logger.info("Sentiment override: risk event detected, holding")

        # Update decision
        decision = base_decision.model_copy(deep=True)
        decision.action = action
        decision.confidence = final_confidence * 100.0  # Convert back to 0-100 for TradingDecision model
        decision.reasoning += (
            f"\n\nHybrid Decision Fusion:\n"
            f"- AI score: {ai_score:+.2f} (confidence: {ai_confidence:.2f}, weight: {weights['ai']:.2f})\n"
            f"- Quant score: {quant_score:+.2f} (confidence: {quant_confidence:.2f}, weight: {weights['quant']:.2f})\n"
        )

        if sentiment_result:
            decision.reasoning += (
                f"- Sentiment: {sentiment_result.score.value} "
                f"(adjustment: {sentiment_adjustment:+.2f}, weight: {weights['sentiment']:.2f})\n"
                f"  Flags: fear={sentiment_result.extreme_fear}, "
                f"greed={sentiment_result.extreme_greed}, "
                f"risk={sentiment_result.risk_event}, "
                f"divergence={sentiment_result.divergence}\n"
            )

        decision.reasoning += (
            f"- Final score: {final_score:+.2f} (confidence: {final_confidence:.2f})\n"
            f"- Action: {action}"
        )

        logger.info(
            f"Hybrid decision: {action} "
            f"(score: {final_score:+.2f}, confidence: {final_confidence:.2f})"
        )

        return decision

    async def close(self):
        """Close resources"""
        if self.sentiment_analyzer:
            await self.sentiment_analyzer.close()
        if self.db_manager:
            await self.db_manager.close()
