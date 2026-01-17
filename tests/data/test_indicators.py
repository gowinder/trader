import pytest
import pandas as pd
import numpy as np
from ai_trader.models.market import Kline
from ai_trader.data.indicators import calculate_indicators


def create_mock_klines(count=100):
    """Create mock klines with a trend"""
    klines = []
    price = 10000.0
    for i in range(count):
        price += np.random.randn() * 10
        timestamp = 1600000000 + i * 60
        klines.append(
            Kline(
                timestamp=timestamp,
                open=price,
                high=price + 5,
                low=price - 5,
                close=price + 2,
                volume=100.0,
            )
        )
    return klines


def test_calculate_indicators():
    """Test indicator calculation"""
    klines = create_mock_klines(200)
    indicators = calculate_indicators(klines)

    assert indicators.ma7 > 0
    assert indicators.ma25 > 0
    assert indicators.ma99 > 0
    assert 0 <= indicators.rsi <= 100
    assert indicators.boll_upper > indicators.boll_lower
