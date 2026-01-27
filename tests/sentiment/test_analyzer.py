"""Tests for sentiment analyzer"""

import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from ai_trader.sentiment.analyzer import (
    SentimentScore,
    SentimentResult,
)


def test_sentiment_result_numeric_score():
    """Test sentiment to numeric score conversion"""
    scores = {
        SentimentScore.VERY_BEARISH: -1.0,
        SentimentScore.BEARISH: -0.5,
        SentimentScore.NEUTRAL: 0.0,
        SentimentScore.BULLISH: 0.5,
        SentimentScore.VERY_BULLISH: 1.0,
    }

    for score, expected in scores.items():
        result = SentimentResult(
            symbol="BTC/USDT",
            score=score,
            confidence=0.8,
            news_count=10,
            reasoning="Test"
        )
        assert result.get_numeric_score() == expected, f"Score {score} should be {expected}"

    print("✓ Sentiment numeric score test passed")


def test_sentiment_adjustment():
    """Test sentiment adjustment calculation"""
    # Extreme fear: +0.15 (contrarian buy opportunity)
    result = SentimentResult(
        symbol="BTC/USDT",
        score=SentimentScore.VERY_BEARISH,
        confidence=0.8,
        news_count=10,
        reasoning="Test",
        extreme_fear=True,
    )
    assert result.get_sentiment_adjustment() == 0.15

    # Extreme greed: -0.15 (contrarian caution)
    result = SentimentResult(
        symbol="BTC/USDT",
        score=SentimentScore.VERY_BULLISH,
        confidence=0.8,
        news_count=10,
        reasoning="Test",
        extreme_greed=True,
    )
    assert result.get_sentiment_adjustment() == -0.15

    # Risk event: -0.2
    result = SentimentResult(
        symbol="BTC/USDT",
        score=SentimentScore.NEUTRAL,
        confidence=0.8,
        news_count=10,
        reasoning="Test",
        risk_event=True,
    )
    assert result.get_sentiment_adjustment() == -0.2

    # Divergence: -0.1
    result = SentimentResult(
        symbol="BTC/USDT",
        score=SentimentScore.BULLISH,
        confidence=0.8,
        news_count=10,
        reasoning="Test",
        divergence=True,
    )
    assert result.get_sentiment_adjustment() == -0.1

    # Normal bullish: +0.05 (0.5 * 0.1)
    result = SentimentResult(
        symbol="BTC/USDT",
        score=SentimentScore.BULLISH,
        confidence=0.8,
        news_count=10,
        reasoning="Test",
    )
    assert result.get_sentiment_adjustment() == 0.05

    print("✓ Sentiment adjustment test passed")


def test_sentiment_result_validation():
    """Test sentiment result field validation"""
    # Valid result
    result = SentimentResult(
        symbol="BTC/USDT",
        score=SentimentScore.BULLISH,
        confidence=0.75,
        news_count=10,
        reasoning="Market sentiment is positive"
    )
    assert result.symbol == "BTC/USDT"
    assert result.score == SentimentScore.BULLISH
    assert result.confidence == 0.75
    assert result.news_count == 10
    assert isinstance(result.timestamp, datetime)

    # Invalid confidence (should raise error)
    try:
        SentimentResult(
            symbol="BTC/USDT",
            score=SentimentScore.BULLISH,
            confidence=1.5,  # > 1.0
            news_count=10,
            reasoning="Test"
        )
        assert False, "Should raise validation error"
    except ValueError:
        pass  # Expected

    print("✓ Sentiment result validation test passed")


def test_sentiment_flags():
    """Test sentiment flags"""
    result = SentimentResult(
        symbol="BTC/USDT",
        score=SentimentScore.VERY_BEARISH,
        confidence=0.9,
        news_count=15,
        reasoning="Extreme panic selling",
        extreme_fear=True,
        extreme_greed=False,
        risk_event=True,
        divergence=False,
    )

    assert result.extreme_fear is True
    assert result.extreme_greed is False
    assert result.risk_event is True
    assert result.divergence is False

    print("✓ Sentiment flags test passed")


def main():
    """Run all tests"""
    print("=" * 60)
    print("Sentiment Analyzer Tests")
    print("=" * 60)
    print()

    test_sentiment_result_numeric_score()
    test_sentiment_adjustment()
    test_sentiment_result_validation()
    test_sentiment_flags()

    print()
    print("=" * 60)
    print("✓ All sentiment analyzer tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
