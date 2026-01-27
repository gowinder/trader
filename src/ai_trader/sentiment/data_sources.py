"""Data sources for sentiment analysis

Supports multiple news/social media sources:
- CryptoPanic API (crypto news aggregator)
- NewsAPI (general news)
- Twitter/X (requires API access - optional)
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
import httpx
from ..utils.logger import logger


class NewsItem(BaseModel):
    """Single news item"""

    source: str = Field(..., description="News source name")
    title: str = Field(..., description="News title")
    url: str = Field(..., description="News URL")
    published_at: datetime = Field(..., description="Publication time")
    content: Optional[str] = Field(None, description="Full content if available")
    sentiment_hint: Optional[str] = Field(None, description="Source's sentiment hint")


class SentimentDataSource(ABC):
    """Abstract base class for sentiment data sources"""

    def __init__(self, api_key: Optional[str] = None, timeout: float = 10.0):
        """Initialize data source

        Args:
            api_key: API key if required
            timeout: Request timeout in seconds
        """
        self.api_key = api_key
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)

    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()

    @abstractmethod
    async def fetch_news(
        self, symbol: str, limit: int = 10, hours: int = 24
    ) -> List[NewsItem]:
        """Fetch news items

        Args:
            symbol: Trading symbol (e.g., "BTC", "ETH")
            limit: Maximum number of items to return
            hours: Look back N hours

        Returns:
            List of news items
        """
        pass


class CryptoPanicSource(SentimentDataSource):
    """CryptoPanic API source

    Free tier: 100 requests/day
    Docs: https://cryptopanic.com/developers/api/
    """

    BASE_URL = "https://cryptopanic.com/api/v1/posts/"

    async def fetch_news(
        self, symbol: str, limit: int = 10, hours: int = 24
    ) -> List[NewsItem]:
        """Fetch crypto news from CryptoPanic

        Args:
            symbol: Crypto symbol (BTC, ETH, etc.)
            limit: Max items
            hours: Look back hours

        Returns:
            List of news items
        """
        if not self.api_key:
            logger.warning("CryptoPanic API key not configured, returning empty results")
            return []

        try:
            # CryptoPanic uses currency codes
            currencies = {
                "BTC": "BTC",
                "ETH": "ETH",
                "BNB": "BNB",
                "SOL": "SOL",
                "USDT": "USDT",
            }

            # Extract base currency (e.g., "BTC" from "BTCUSDT")
            base_currency = None
            for curr in currencies.keys():
                if symbol.upper().startswith(curr):
                    base_currency = currencies[curr]
                    break

            if not base_currency:
                logger.warning(f"Unknown symbol for CryptoPanic: {symbol}")
                return []

            # Build request
            params = {
                "auth_token": self.api_key,
                "currencies": base_currency,
                "kind": "news",  # news only (not media)
                "filter": "hot",  # hot/rising/bullish/bearish/important/lol
            }

            response = await self.client.get(self.BASE_URL, params=params)
            response.raise_for_status()

            data = response.json()
            items = []

            cutoff = datetime.now() - timedelta(hours=hours)

            for post in data.get("results", [])[:limit]:
                published_str = post.get("published_at")
                if not published_str:
                    continue

                # Parse timestamp (ISO format)
                published_at = datetime.fromisoformat(
                    published_str.replace("Z", "+00:00")
                )

                # Filter by time
                if published_at < cutoff:
                    continue

                # Extract sentiment votes
                votes = post.get("votes", {})
                sentiment_hint = None
                if votes:
                    positive = votes.get("positive", 0)
                    negative = votes.get("negative", 0)
                    if positive > negative * 2:
                        sentiment_hint = "bullish"
                    elif negative > positive * 2:
                        sentiment_hint = "bearish"
                    else:
                        sentiment_hint = "neutral"

                items.append(
                    NewsItem(
                        source="CryptoPanic",
                        title=post.get("title", ""),
                        url=post.get("url", ""),
                        published_at=published_at,
                        sentiment_hint=sentiment_hint,
                    )
                )

            logger.info(f"Fetched {len(items)} news items from CryptoPanic")
            return items

        except httpx.HTTPError as e:
            logger.error(f"CryptoPanic API error: {e}")
            return []
        except Exception as e:
            logger.error(f"Failed to fetch CryptoPanic news: {e}")
            return []


class NewsAPISource(SentimentDataSource):
    """NewsAPI source

    Free tier: 100 requests/day, 1 month history
    Docs: https://newsapi.org/docs
    """

    BASE_URL = "https://newsapi.org/v2/everything"

    async def fetch_news(
        self, symbol: str, limit: int = 10, hours: int = 24
    ) -> List[NewsItem]:
        """Fetch general news from NewsAPI

        Args:
            symbol: Trading symbol (e.g., "BTC")
            limit: Max items
            hours: Look back hours

        Returns:
            List of news items
        """
        if not self.api_key:
            logger.warning("NewsAPI key not configured, returning empty results")
            return []

        try:
            # Build search query
            currency_names = {
                "BTC": "Bitcoin",
                "ETH": "Ethereum",
                "BNB": "Binance",
                "SOL": "Solana",
            }

            # Extract base currency
            search_term = "cryptocurrency"
            for curr, name in currency_names.items():
                if symbol.upper().startswith(curr):
                    search_term = name
                    break

            # Calculate time range
            from_date = datetime.now() - timedelta(hours=hours)

            params = {
                "apiKey": self.api_key,
                "q": search_term,
                "language": "en",
                "sortBy": "publishedAt",
                "from": from_date.isoformat(),
                "pageSize": min(limit, 100),
            }

            response = await self.client.get(self.BASE_URL, params=params)
            response.raise_for_status()

            data = response.json()
            items = []

            for article in data.get("articles", []):
                published_str = article.get("publishedAt")
                if not published_str:
                    continue

                published_at = datetime.fromisoformat(
                    published_str.replace("Z", "+00:00")
                )

                items.append(
                    NewsItem(
                        source=article.get("source", {}).get("name", "NewsAPI"),
                        title=article.get("title", ""),
                        url=article.get("url", ""),
                        published_at=published_at,
                        content=article.get("description"),
                    )
                )

            logger.info(f"Fetched {len(items)} news items from NewsAPI")
            return items

        except httpx.HTTPError as e:
            logger.error(f"NewsAPI error: {e}")
            return []
        except Exception as e:
            logger.error(f"Failed to fetch NewsAPI news: {e}")
            return []


class TwitterSource(SentimentDataSource):
    """Twitter/X API source (optional, requires paid API access)

    Note: Twitter API v2 requires elevated access ($100/month)
    This is a placeholder for future implementation
    """

    async def fetch_news(
        self, symbol: str, limit: int = 10, hours: int = 24
    ) -> List[NewsItem]:
        """Fetch tweets (placeholder)

        Args:
            symbol: Trading symbol
            limit: Max items
            hours: Look back hours

        Returns:
            Empty list (not implemented)
        """
        logger.warning("Twitter source not implemented (requires paid API)")
        return []
