"""Sentiment analyzer using LLM to analyze market sentiment"""

from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime

from .data_sources import SentimentDataSource, NewsItem
from .cache import SentimentCache
from ..ai.llm_client import LLMClient
from ..utils.logger import logger


class SentimentScore(str, Enum):
    """Sentiment score enumeration"""

    VERY_BEARISH = "very_bearish"  # Extreme fear
    BEARISH = "bearish"  # Fear
    NEUTRAL = "neutral"  # Neutral
    BULLISH = "bullish"  # Greed
    VERY_BULLISH = "very_bullish"  # Extreme greed


class SentimentResult(BaseModel):
    """Sentiment analysis result"""

    symbol: str = Field(..., description="Trading symbol")
    score: SentimentScore = Field(..., description="Overall sentiment score")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence level")
    news_count: int = Field(..., description="Number of news items analyzed")
    reasoning: str = Field(..., description="LLM reasoning")
    timestamp: datetime = Field(default_factory=datetime.now)

    # Sentiment adjustment factors
    extreme_fear: bool = Field(default=False, description="Extreme fear detected")
    extreme_greed: bool = Field(default=False, description="Extreme greed detected")
    risk_event: bool = Field(default=False, description="Major risk event detected")
    divergence: bool = Field(
        default=False, description="Sentiment-price divergence detected"
    )

    def get_numeric_score(self) -> float:
        """Convert sentiment to numeric score (-1 to +1)

        Returns:
            Numeric score: -1 (very bearish) to +1 (very bullish)
        """
        score_map = {
            SentimentScore.VERY_BEARISH: -1.0,
            SentimentScore.BEARISH: -0.5,
            SentimentScore.NEUTRAL: 0.0,
            SentimentScore.BULLISH: 0.5,
            SentimentScore.VERY_BULLISH: 1.0,
        }
        return score_map[self.score]

    def get_sentiment_adjustment(self) -> float:
        """Get sentiment-based decision adjustment

        Returns:
            Adjustment factor for decision confidence (-0.2 to +0.2)
        """
        if self.extreme_fear:
            # Contrarian: extreme fear may signal buying opportunity
            return +0.15
        elif self.extreme_greed:
            # Contrarian: extreme greed may signal caution
            return -0.15
        elif self.risk_event:
            # Major risk event: reduce confidence
            return -0.2
        elif self.divergence:
            # Divergence: reduce confidence
            return -0.1
        else:
            # Normal sentiment influence (aligned with score)
            return self.get_numeric_score() * 0.1


class SentimentAnalyzer:
    """Sentiment analyzer using LLM

    Analyzes market sentiment from news sources and provides
    sentiment-adjusted trading signals.
    """

    SENTIMENT_PROMPT = """You are a professional cryptocurrency market sentiment analyst.

Analyze the following {news_count} recent news headlines about {symbol} and provide a comprehensive sentiment analysis.

News headlines:
{news_headlines}

Instructions:
1. Analyze the overall market sentiment (very bearish, bearish, neutral, bullish, very bullish)
2. Assess confidence level (0.0-1.0) based on consistency and clarity of signals
3. Detect extreme conditions:
   - Extreme fear: panic selling, capitulation, extreme FUD
   - Extreme greed: FOMO, euphoria, irrational exuberance
   - Risk events: major hacks, regulatory crackdowns, black swan events
4. Provide clear reasoning for your assessment

Respond in JSON format:
{{
  "score": "very_bearish|bearish|neutral|bullish|very_bullish",
  "confidence": 0.75,
  "extreme_fear": false,
  "extreme_greed": false,
  "risk_event": false,
  "reasoning": "Detailed explanation of sentiment analysis"
}}"""

    def __init__(
        self,
        data_sources: List[SentimentDataSource],
        llm_client: LLMClient,
        cache: Optional[SentimentCache] = None,
        min_news_count: int = 3,
    ):
        """Initialize sentiment analyzer

        Args:
            data_sources: List of sentiment data sources
            llm_client: LLM client for analysis
            cache: Sentiment cache (creates new if None)
            min_news_count: Minimum news items required for analysis
        """
        self.data_sources = data_sources
        self.llm_client = llm_client
        self.cache = cache or SentimentCache()
        self.min_news_count = min_news_count

    async def analyze(
        self,
        symbol: str,
        current_price: Optional[float] = None,
        price_change_24h: Optional[float] = None,
    ) -> Optional[SentimentResult]:
        """Analyze market sentiment

        Args:
            symbol: Trading symbol (e.g., "BTC/USDT")
            current_price: Current price (for divergence detection)
            price_change_24h: 24h price change percentage

        Returns:
            Sentiment analysis result or None if insufficient data
        """
        # Extract base symbol (e.g., "BTC" from "BTC/USDT")
        base_symbol = symbol.split("/")[0]

        # Check cache first
        cached = self.cache.get("sentiment", base_symbol)
        if cached:
            logger.info(f"Using cached sentiment for {base_symbol}")
            return cached

        # Collect news from all sources
        all_news: List[NewsItem] = []
        for source in self.data_sources:
            source_name = source.__class__.__name__

            # Check rate limit
            if not self.cache.can_request(source_name):
                wait_time = self.cache.get_wait_time(source_name)
                logger.warning(
                    f"Skipping {source_name} due to rate limit (wait: {wait_time:.0f}s)"
                )
                continue

            # Check source-specific cache first
            cached_news = self.cache.get(source_name, base_symbol)
            if cached_news:
                all_news.extend(cached_news)
                logger.info(f"Using cached {len(cached_news)} news from {source_name}")
                continue

            try:
                # Free tier: limit to 10 items, 48h history (24h delay + 24h window)
                news = await source.fetch_news(base_symbol, limit=10, hours=48)
                if news:
                    # Cache per-source results with source-specific TTL
                    source_ttl = self.cache.get_source_ttl(source_name)
                    self.cache.set(source_name, base_symbol, news, ttl=source_ttl)
                all_news.extend(news)
                logger.info(f"Fetched {len(news)} news from {source_name}")
            except Exception as e:
                logger.error(f"Failed to fetch news from {source_name}: {e}")

        # Check if we have enough news
        if len(all_news) < self.min_news_count:
            logger.warning(
                f"Insufficient news for sentiment analysis: {len(all_news)}/{self.min_news_count}"
            )
            return None

        # Sort by publish time (most recent first)
        all_news.sort(key=lambda x: x.published_at, reverse=True)

        # Prepare news headlines for LLM
        news_headlines = "\n".join(
            [
                f"[{news.published_at.strftime('%Y-%m-%d %H:%M')}] {news.title} ({news.source})"
                for news in all_news[:20]  # Use top 20
            ]
        )

        # Generate prompt
        prompt = self.SENTIMENT_PROMPT.format(
            symbol=base_symbol,
            news_count=len(all_news[:20]),
            news_headlines=news_headlines,
        )

        # Analyze with LLM
        try:
            # 定义 JSON schema
            schema = {
                "type": "object",
                "properties": {
                    "score": {
                        "type": "string",
                        "enum": ["very_bearish", "bearish", "neutral", "bullish", "very_bullish"]
                    },
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "extreme_fear": {"type": "boolean"},
                    "extreme_greed": {"type": "boolean"},
                    "risk_event": {"type": "boolean"},
                    "reasoning": {"type": "string"}
                },
                "required": ["score", "confidence", "reasoning"],
                "additionalProperties": False
            }

            result_data = await self.llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                schema=schema,
            )

            # 结果可能直接是 dict 或包含在 content 中
            if isinstance(result_data, dict) and "content" in result_data:
                import json
                analysis = json.loads(result_data["content"]) if isinstance(result_data["content"], str) else result_data["content"]
            else:
                analysis = result_data

            # Detect divergence if price data available
            divergence = False
            if current_price and price_change_24h is not None:
                sentiment_score_map = {
                    "very_bearish": -2,
                    "bearish": -1,
                    "neutral": 0,
                    "bullish": 1,
                    "very_bullish": 2,
                }
                sentiment_numeric = sentiment_score_map.get(analysis["score"], 0)

                # Divergence: sentiment and price move in opposite directions
                if sentiment_numeric > 0 and price_change_24h < -5:
                    divergence = True  # Bullish sentiment but price dropping
                elif sentiment_numeric < 0 and price_change_24h > 5:
                    divergence = True  # Bearish sentiment but price rising

            result = SentimentResult(
                symbol=symbol,
                score=SentimentScore(analysis["score"]),
                confidence=analysis["confidence"],
                news_count=len(all_news),
                reasoning=analysis["reasoning"],
                extreme_fear=analysis.get("extreme_fear", False),
                extreme_greed=analysis.get("extreme_greed", False),
                risk_event=analysis.get("risk_event", False),
                divergence=divergence,
            )

            # Cache result
            self.cache.set("sentiment", base_symbol, result)

            logger.info(
                f"Sentiment analysis: {result.score.value} "
                f"(confidence: {result.confidence:.2f}, news: {result.news_count})"
            )

            return result

        except Exception as e:
            logger.error(f"Sentiment analysis failed: {e}")
            return None

    async def close(self):
        """Close resources"""
        for source in self.data_sources:
            await source.close()
        await self.cache.stop_cleanup_task()
