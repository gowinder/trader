"""Multi-timeframe analysis module for professional trading strategies"""

from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum
from ..exchange.base import BaseExchange
from ..models.market import MarketData, Kline, Indicators
from .market_data import MarketDataManager
from .indicators import calculate_indicators
from ..utils.logger import logger


class TrendDirection(str, Enum):
    """Trend direction classification"""

    UPTREND = "uptrend"
    DOWNTREND = "downtrend"
    SIDEWAYS = "sideways"


class MACDSignal(str, Enum):
    """MACD signal classification"""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


@dataclass
class TimeframeAnalysis:
    """Single timeframe analysis result"""

    interval: str  # "15m", "1h", "4h", "1d"
    trend: TrendDirection  # Overall trend direction
    ma_alignment: bool  # MA bullish/bearish alignment (EMA20 > EMA50 > EMA100 for uptrend)
    macd_signal: MACDSignal  # MACD signal classification
    support_levels: List[float]  # Key support levels
    resistance_levels: List[float]  # Key resistance levels
    confidence: float  # Analysis confidence (0.0-1.0)
    current_price: float  # Current price at analysis time
    atr: float  # Average True Range for volatility measurement

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization"""
        return {
            "interval": self.interval,
            "trend": self.trend.value,
            "ma_alignment": self.ma_alignment,
            "macd_signal": self.macd_signal.value,
            "support_levels": self.support_levels,
            "resistance_levels": self.resistance_levels,
            "confidence": self.confidence,
            "current_price": self.current_price,
            "atr": self.atr,
        }


@dataclass
class MultiTimeframeData:
    """Aggregated multi-timeframe analysis"""

    symbol: str
    analyses: Dict[str, TimeframeAnalysis]  # {interval: analysis}
    overall_trend: TrendDirection  # Aggregated trend across timeframes
    confluence_score: float  # Multi-timeframe alignment score (0-1)
    recommended_action: str  # "buy", "sell", "hold"

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization"""
        return {
            "symbol": self.symbol,
            "analyses": {k: v.to_dict() for k, v in self.analyses.items()},
            "overall_trend": self.overall_trend.value,
            "confluence_score": self.confluence_score,
            "recommended_action": self.recommended_action,
        }


class MultiTimeframeManager:
    """Manager for multi-timeframe analysis following professional trader methodology"""

    # Default timeframe combinations (4:1 ratio recommended)
    DAYTRADING_TIMEFRAMES = ["15m", "1h", "4h"]  # For day trading
    SWING_TRADING_TIMEFRAMES = ["1h", "4h", "1d"]  # For swing trading
    POSITION_TRADING_TIMEFRAMES = ["4h", "1d", "1w"]  # For position trading

    def __init__(self, client: BaseExchange):
        self.client = client
        self.market_mgr = MarketDataManager(client)

    async def get_multi_timeframe_data(
        self,
        symbol: str,
        timeframes: Optional[List[str]] = None,
        limit: int = 150,
    ) -> Optional[MultiTimeframeData]:
        """Fetch and analyze data across multiple timeframes in parallel

        Args:
            symbol: Trading pair symbol
            timeframes: List of intervals to analyze (default: DAYTRADING_TIMEFRAMES)
            limit: Number of klines to fetch per timeframe

        Returns:
            MultiTimeframeData with aggregated analysis or None on error
        """
        if timeframes is None:
            timeframes = self.DAYTRADING_TIMEFRAMES

        logger.info(f"Fetching multi-timeframe data for {symbol}: {timeframes}")

        analyses = {}
        try:
            # Fetch data for each timeframe sequentially (could be parallelized with asyncio.gather)
            for interval in timeframes:
                market_data = await self.market_mgr.get_market_data(
                    symbol, interval, limit
                )
                if not market_data:
                    logger.warning(
                        f"Failed to fetch data for {symbol} on {interval} timeframe"
                    )
                    continue

                analysis = self._analyze_timeframe(interval, market_data)
                analyses[interval] = analysis

            if not analyses:
                logger.error(f"No successful timeframe analysis for {symbol}")
                return None

            # Aggregate analyses across timeframes
            overall_trend = self._determine_overall_trend(analyses)
            confluence_score = self._calculate_confluence_score(analyses)
            recommended_action = self._recommend_action(analyses, overall_trend)

            return MultiTimeframeData(
                symbol=symbol,
                analyses=analyses,
                overall_trend=overall_trend,
                confluence_score=confluence_score,
                recommended_action=recommended_action,
            )

        except Exception as e:
            logger.error(f"Error in multi-timeframe analysis: {e}")
            return None

    def _analyze_timeframe(
        self, interval: str, market_data: MarketData
    ) -> TimeframeAnalysis:
        """Analyze single timeframe for trend, MA alignment, MACD signal, and key levels

        Implements professional trader methodology:
        - Trend identification via MA alignment
        - MACD confirmation
        - Support/resistance from pivot points and previous highs/lows
        """
        indicators = market_data.indicators
        klines = market_data.klines
        current_price = market_data.current_price

        # Trend identification: MA alignment + MACD
        trend = self._determine_trend(indicators, current_price)
        ma_alignment = self._check_ma_alignment(indicators, current_price, trend)
        macd_signal = self._classify_macd(indicators)

        # Support/resistance levels
        support_levels, resistance_levels = self._calculate_key_levels(
            klines, current_price
        )

        # Confidence calculation
        confidence = self._calculate_confidence(
            ma_alignment, macd_signal, trend, indicators
        )

        return TimeframeAnalysis(
            interval=interval,
            trend=trend,
            ma_alignment=ma_alignment,
            macd_signal=macd_signal,
            support_levels=support_levels,
            resistance_levels=resistance_levels,
            confidence=confidence,
            current_price=current_price,
            atr=indicators.atr,
        )

    def _determine_trend(self, indicators: Indicators, current_price: float) -> TrendDirection:
        """Determine trend direction using MA alignment and price position

        Methodology:
        - Uptrend: MA7 > MA25 > MA99 and price > MA7
        - Downtrend: MA7 < MA25 < MA99 and price < MA7
        - Sideways: MA convergence or price oscillating around MAs
        """
        ma7 = indicators.ma7
        ma25 = indicators.ma25
        ma99 = indicators.ma99

        # Check MA ordering
        ma_uptrend = ma7 > ma25 > ma99
        ma_downtrend = ma7 < ma25 < ma99

        # Check price position
        price_above_mas = current_price > ma7
        price_below_mas = current_price < ma7

        if ma_uptrend and price_above_mas:
            return TrendDirection.UPTREND
        elif ma_downtrend and price_below_mas:
            return TrendDirection.DOWNTREND
        else:
            return TrendDirection.SIDEWAYS

    def _check_ma_alignment(
        self, indicators: Indicators, current_price: float, trend: TrendDirection
    ) -> bool:
        """Check if MAs are properly aligned for the identified trend

        Returns True if MA alignment confirms the trend
        """
        ma7 = indicators.ma7
        ma25 = indicators.ma25
        ma99 = indicators.ma99

        if trend == TrendDirection.UPTREND:
            return ma7 > ma25 > ma99 and current_price > ma7
        elif trend == TrendDirection.DOWNTREND:
            return ma7 < ma25 < ma99 and current_price < ma7
        else:
            return False  # Sideways has no clear alignment

    def _classify_macd(self, indicators: Indicators) -> MACDSignal:
        """Classify MACD signal as bullish/bearish/neutral

        Methodology:
        - Bullish: MACD > Signal and Histogram increasing
        - Bearish: MACD < Signal and Histogram decreasing
        - Neutral: Otherwise
        """
        macd = indicators.macd
        macd_signal = indicators.macd_signal
        macd_histogram = indicators.macd_histogram

        # MACD above signal line is bullish
        if macd > macd_signal and macd_histogram > 0:
            return MACDSignal.BULLISH
        # MACD below signal line is bearish
        elif macd < macd_signal and macd_histogram < 0:
            return MACDSignal.BEARISH
        else:
            return MACDSignal.NEUTRAL

    def _calculate_key_levels(
        self, klines: List[Kline], current_price: float
    ) -> tuple[List[float], List[float]]:
        """Calculate support and resistance levels using pivot points and previous highs/lows

        Methodology:
        - Pivot Point: PP = (High + Low + Close) / 3
        - Support levels: Recent lows, Fibonacci retracements
        - Resistance levels: Recent highs, round numbers
        """
        if not klines or len(klines) < 20:
            return [], []

        # Get last N klines for analysis
        recent_klines = klines[-50:]  # Last 50 candles

        # Calculate pivot point from last candle
        last_kline = klines[-1]
        pivot_point = (last_kline.high + last_kline.low + last_kline.close) / 3

        # Find recent lows and highs
        lows = [k.low for k in recent_klines]
        highs = [k.high for k in recent_klines]

        # Support levels: pivot, recent lows below current price
        support_levels = [pivot_point] if pivot_point < current_price else []
        support_levels.extend(
            sorted([low for low in lows if low < current_price], reverse=True)[:3]
        )

        # Resistance levels: pivot, recent highs above current price
        resistance_levels = [pivot_point] if pivot_point > current_price else []
        resistance_levels.extend(
            sorted([high for high in highs if high > current_price])[:3]
        )

        # Deduplicate and sort
        support_levels = sorted(list(set(support_levels)), reverse=True)[:5]
        resistance_levels = sorted(list(set(resistance_levels)))[:5]

        return support_levels, resistance_levels

    def _calculate_confidence(
        self,
        ma_alignment: bool,
        macd_signal: MACDSignal,
        trend: TrendDirection,
        indicators: Indicators,
    ) -> float:
        """Calculate analysis confidence score (0.0-1.0)

        Factors:
        - MA alignment: +0.3
        - MACD confirmation: +0.3
        - RSI not extreme: +0.2
        - Clear trend (not sideways): +0.2
        """
        confidence = 0.0

        # MA alignment
        if ma_alignment:
            confidence += 0.3

        # MACD confirmation
        if macd_signal != MACDSignal.NEUTRAL:
            confidence += 0.3

        # RSI not in extreme zones (not oversold or overbought)
        rsi = indicators.rsi
        if 30 < rsi < 70:
            confidence += 0.2

        # Clear trend
        if trend != TrendDirection.SIDEWAYS:
            confidence += 0.2

        return round(confidence, 2)

    def _determine_overall_trend(
        self, analyses: Dict[str, TimeframeAnalysis]
    ) -> TrendDirection:
        """Determine overall trend by aggregating trends across timeframes

        Methodology: Higher timeframes have more weight
        - 4h/1d/1w: Weight 3
        - 1h: Weight 2
        - 15m: Weight 1
        """
        if not analyses:
            return TrendDirection.SIDEWAYS

        # Assign weights to timeframes
        timeframe_weights = {
            "15m": 1,
            "1h": 2,
            "4h": 3,
            "1d": 3,
            "1w": 3,
        }

        uptrend_score = 0.0
        downtrend_score = 0.0
        total_weight = 0.0

        for interval, analysis in analyses.items():
            weight = timeframe_weights.get(interval, 2)  # Default weight 2
            total_weight += weight

            if analysis.trend == TrendDirection.UPTREND:
                uptrend_score += weight
            elif analysis.trend == TrendDirection.DOWNTREND:
                downtrend_score += weight

        # Calculate trend strength
        uptrend_pct = uptrend_score / total_weight if total_weight > 0 else 0
        downtrend_pct = downtrend_score / total_weight if total_weight > 0 else 0

        # Require >50% agreement for clear trend
        if uptrend_pct > 0.5:
            return TrendDirection.UPTREND
        elif downtrend_pct > 0.5:
            return TrendDirection.DOWNTREND
        else:
            return TrendDirection.SIDEWAYS

    def _calculate_confluence_score(
        self, analyses: Dict[str, TimeframeAnalysis]
    ) -> float:
        """Calculate confluence score (0-1) representing multi-timeframe alignment

        High confluence (>0.7) means all timeframes agree - high-quality signal
        Low confluence (<0.4) means conflicting signals - avoid trading
        """
        if not analyses:
            return 0.0

        # Check how many timeframes agree with overall trend
        overall_trend = self._determine_overall_trend(analyses)

        agreeing_timeframes = 0
        total_timeframes = len(analyses)

        for analysis in analyses.values():
            if analysis.trend == overall_trend:
                agreeing_timeframes += 1

        # Also consider MACD alignment
        bullish_macd = sum(
            1 for a in analyses.values() if a.macd_signal == MACDSignal.BULLISH
        )
        bearish_macd = sum(
            1 for a in analyses.values() if a.macd_signal == MACDSignal.BEARISH
        )

        # MACD alignment score
        macd_alignment = max(bullish_macd, bearish_macd) / total_timeframes

        # Final confluence: weighted average of trend agreement and MACD alignment
        trend_agreement = agreeing_timeframes / total_timeframes
        confluence = (trend_agreement * 0.7) + (macd_alignment * 0.3)

        return round(confluence, 2)

    def _recommend_action(
        self,
        analyses: Dict[str, TimeframeAnalysis],
        overall_trend: TrendDirection,
    ) -> str:
        """Recommend trading action based on multi-timeframe analysis

        Rules:
        - Only trade if confluence score > 0.6
        - Uptrend + high confluence -> "buy"
        - Downtrend + high confluence -> "sell"
        - Otherwise -> "hold"
        """
        confluence_score = self._calculate_confluence_score(analyses)

        # Require high confluence for action
        if confluence_score < 0.6:
            return "hold"

        if overall_trend == TrendDirection.UPTREND:
            return "buy"
        elif overall_trend == TrendDirection.DOWNTREND:
            return "sell"
        else:
            return "hold"
