"""Unit tests for MarketClassifier"""

import pytest
import numpy as np
import pandas as pd
from ai_trader.strategies.market_classifier import MarketClassifier, MarketState


def make_ohlcv(n: int, base_price: float = 100.0, volatility: float = 1.0, volume: float = 1000.0) -> pd.DataFrame:
    """Generate synthetic OHLCV data."""
    np.random.seed(42)
    close = base_price + np.cumsum(np.random.randn(n) * volatility)
    high = close + np.abs(np.random.randn(n) * volatility)
    low = close - np.abs(np.random.randn(n) * volatility)
    open_ = close + np.random.randn(n) * volatility * 0.5
    volumes = np.full(n, volume) + np.random.randn(n) * volume * 0.1
    return pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": np.abs(volumes),
    })


class TestMarketClassifier:

    def setup_method(self):
        self.mc = MarketClassifier(adx_period=14, atr_period=14, volume_period=20)

    # --- ADX ---
    def test_adx_insufficient_data(self):
        df = make_ohlcv(10)
        assert self.mc.calculate_adx(df) == 0.0

    def test_adx_with_sufficient_data(self):
        df = make_ohlcv(100, volatility=2.0)
        adx = self.mc.calculate_adx(df)
        assert 0.0 <= adx <= 100.0
        # With random walk data ADX should be some positive value
        assert adx >= 0.0

    # --- Volatility ---
    def test_volatility_insufficient_data(self):
        df = make_ohlcv(5)
        assert self.mc.calculate_volatility(df) == 0.0

    # --- Volume ratio ---
    def test_volume_ratio_insufficient_data(self):
        df = make_ohlcv(10)
        assert self.mc.calculate_volume_ratio(df) == 1.0

    def test_volume_ratio_normal(self):
        df = make_ohlcv(50, volume=1000.0)
        ratio = self.mc.calculate_volume_ratio(df)
        # With roughly constant volume, ratio should be near 1.0
        assert 0.5 < ratio < 2.0

    # --- Trend direction ---
    def test_trend_direction_insufficient_data(self):
        df = make_ohlcv(30)
        assert self.mc.calculate_trend_direction(df) == 0

    def test_trend_direction_uptrend(self):
        # Construct data where ma20 > ma50 * 1.02
        n = 60
        # First 40 values low, last 20 values high
        close = np.concatenate([np.full(40, 100.0), np.full(20, 115.0)])
        df = pd.DataFrame({
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": np.full(n, 1000.0),
        })
        assert self.mc.calculate_trend_direction(df) == 1

    def test_trend_direction_downtrend(self):
        n = 60
        close = np.concatenate([np.full(40, 100.0), np.full(20, 85.0)])
        df = pd.DataFrame({
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": np.full(n, 1000.0),
        })
        assert self.mc.calculate_trend_direction(df) == -1

    # --- _classify_state ---
    def test_classify_state_strong_trend(self):
        df = make_ohlcv(50)
        state, confidence = self.mc._classify_state(adx=30.0, volatility=0.5, volume_ratio=1.0, df=df)
        assert state == MarketState.STRONG_TREND
        assert 0.0 <= confidence <= 1.0

    def test_classify_state_weak_trend(self):
        df = make_ohlcv(50)
        state, confidence = self.mc._classify_state(adx=22.0, volatility=0.5, volume_ratio=1.0, df=df)
        assert state == MarketState.WEAK_TREND
        assert confidence == 0.7

    def test_classify_state_range_bound(self):
        df = make_ohlcv(50)
        state, confidence = self.mc._classify_state(adx=15.0, volatility=1.5, volume_ratio=1.0, df=df)
        assert state == MarketState.RANGE_BOUND
        assert confidence == 0.75

    def test_classify_state_sideways(self):
        df = make_ohlcv(50)
        state, confidence = self.mc._classify_state(adx=15.0, volatility=0.5, volume_ratio=1.0, df=df)
        assert state == MarketState.SIDEWAYS
        assert confidence == 0.8
