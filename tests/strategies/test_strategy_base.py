"""Unit tests for strategy_base: Signal model and TradingStrategy base class"""

import pytest
import numpy as np
import pandas as pd
from pydantic import ValidationError
from ai_trader.strategies.strategy_base import (
    Signal,
    SignalAction,
    TradingStrategy,
    TrendFollowingStrategy,
)


class ConcreteStrategy(TradingStrategy):
    """Minimal concrete subclass for testing base methods."""

    def __init__(self):
        super().__init__("TestStrategy")

    def generate_signal(self, df: pd.DataFrame) -> Signal:
        return Signal(action=SignalAction.HOLD, confidence=0.0, reason="test")


def make_ohlcv(n: int, base: float = 100.0) -> pd.DataFrame:
    np.random.seed(0)
    close = base + np.cumsum(np.random.randn(n) * 0.5)
    return pd.DataFrame({
        "open": close + np.random.randn(n) * 0.1,
        "high": close + np.abs(np.random.randn(n)),
        "low": close - np.abs(np.random.randn(n)),
        "close": close,
        "volume": np.abs(np.random.randn(n) * 100 + 1000),
    })


class TestSignalModel:

    def test_signal_valid_creation(self):
        s = Signal(
            action=SignalAction.LONG,
            confidence=0.8,
            entry_price=100.0,
            stop_loss=95.0,
            take_profit=110.0,
            reason="test signal",
        )
        assert s.action == SignalAction.LONG
        assert s.confidence == 0.8
        assert s.reason == "test signal"

    def test_signal_confidence_bounds(self):
        # confidence > 1 should fail
        with pytest.raises(ValidationError):
            Signal(action=SignalAction.HOLD, confidence=1.5, reason="bad")
        # confidence < 0 should fail
        with pytest.raises(ValidationError):
            Signal(action=SignalAction.HOLD, confidence=-0.1, reason="bad")
        # boundary values should succeed
        Signal(action=SignalAction.HOLD, confidence=0.0, reason="ok")
        Signal(action=SignalAction.HOLD, confidence=1.0, reason="ok")


class TestTradingStrategyBase:

    def setup_method(self):
        self.strategy = ConcreteStrategy()

    def test_calculate_ma_normal(self):
        series = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        ma = self.strategy.calculate_ma(series, period=3)
        # mean of last 3: (3+4+5)/3 = 4.0
        assert ma == pytest.approx(4.0)

    def test_calculate_ma_insufficient_data(self):
        series = pd.Series([1.0, 2.0])
        ma = self.strategy.calculate_ma(series, period=5)
        # Falls back to full mean: (1+2)/2 = 1.5
        assert ma == pytest.approx(1.5)

    def test_calculate_ema(self):
        series = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
        ema = self.strategy.calculate_ema(series, period=5)
        # EMA should be closer to recent values
        assert 7.0 < ema < 10.0

    def test_calculate_rsi_default_50(self):
        series = pd.Series([1.0, 2.0, 3.0])
        rsi = self.strategy.calculate_rsi(series, period=14)
        assert rsi == 50.0

    def test_calculate_rsi_normal(self):
        # Uptrend data should give RSI > 50
        series = pd.Series(list(range(1, 30)), dtype=float)
        rsi = self.strategy.calculate_rsi(series, period=14)
        assert 50.0 < rsi <= 100.0

    def test_calculate_macd_insufficient_data(self):
        series = pd.Series([1.0, 2.0, 3.0])
        macd, signal, hist = self.strategy.calculate_macd(series)
        assert (macd, signal, hist) == (0.0, 0.0, 0.0)

    def test_calculate_atr_insufficient_data(self):
        df = make_ohlcv(5)
        atr = self.strategy.calculate_atr(df, period=14)
        assert atr == 0.0

    def test_calculate_bollinger_bands_normal(self):
        series = pd.Series(list(range(1, 30)), dtype=float)
        upper, middle, lower = self.strategy.calculate_bollinger_bands(series, period=20)
        assert upper > middle > lower
        # Middle should be mean of last 20
        expected_middle = series.iloc[-20:].mean()
        assert middle == pytest.approx(expected_middle)

    def test_calculate_bollinger_bands_insufficient_data(self):
        series = pd.Series([1.0, 2.0, 3.0])
        upper, middle, lower = self.strategy.calculate_bollinger_bands(series, period=20)
        # All three should be the same (mean of series)
        mean_val = series.mean()
        assert upper == pytest.approx(mean_val)
        assert middle == pytest.approx(mean_val)
        assert lower == pytest.approx(mean_val)
