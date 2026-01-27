"""Trading strategy base classes and implementations"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional
import pandas as pd
import numpy as np
from pydantic import BaseModel, Field


class SignalAction(Enum):
    """Signal action enumeration"""

    LONG = "long"  # Open long position
    SHORT = "short"  # Open short position
    HOLD = "hold"  # Hold current position
    CLOSE_LONG = "close_long"  # Close long position
    CLOSE_SHORT = "close_short"  # Close short position


class Signal(BaseModel):
    """Trading signal"""

    action: SignalAction = Field(..., description="Signal action")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence level")
    entry_price: Optional[float] = Field(None, description="Suggested entry price")
    stop_loss: Optional[float] = Field(None, description="Stop loss price")
    take_profit: Optional[float] = Field(None, description="Take profit price")
    reason: str = Field(..., description="Signal reason")


class TradingStrategy(ABC):
    """Abstract base class for trading strategies"""

    def __init__(self, name: str):
        """Initialize strategy

        Args:
            name: Strategy name
        """
        self.name = name

    @abstractmethod
    def generate_signal(self, df: pd.DataFrame) -> Signal:
        """Generate trading signal

        Args:
            df: OHLCV data (columns: open, high, low, close, volume)

        Returns:
            Trading signal
        """
        pass

    def calculate_ma(self, series: pd.Series, period: int) -> float:
        """Calculate moving average

        Args:
            series: Price series
            period: MA period

        Returns:
            Moving average value
        """
        if len(series) < period:
            return series.mean()
        return float(series.iloc[-period:].mean())

    def calculate_ema(self, series: pd.Series, period: int) -> float:
        """Calculate exponential moving average

        Args:
            series: Price series
            period: EMA period

        Returns:
            EMA value
        """
        if len(series) < period:
            return series.mean()
        return float(series.ewm(span=period, adjust=False).mean().iloc[-1])

    def calculate_rsi(self, series: pd.Series, period: int = 14) -> float:
        """Calculate RSI

        Args:
            series: Price series
            period: RSI period

        Returns:
            RSI value (0-100)
        """
        if len(series) < period + 1:
            return 50.0

        delta = series.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)

        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return float(rsi.iloc[-1])

    def calculate_macd(
        self, series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
    ) -> tuple[float, float, float]:
        """Calculate MACD

        Args:
            series: Price series
            fast: Fast EMA period
            slow: Slow EMA period
            signal: Signal line period

        Returns:
            Tuple of (MACD, signal line, histogram)
        """
        if len(series) < slow:
            return 0.0, 0.0, 0.0

        ema_fast = series.ewm(span=fast, adjust=False).mean()
        ema_slow = series.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line

        return (
            float(macd_line.iloc[-1]),
            float(signal_line.iloc[-1]),
            float(histogram.iloc[-1]),
        )

    def calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calculate ATR

        Args:
            df: OHLCV data
            period: ATR period

        Returns:
            ATR value
        """
        if len(df) < period + 1:
            return 0.0

        high = df["high"].values
        low = df["low"].values
        close = df["close"].values

        tr1 = high[1:] - low[1:]
        tr2 = np.abs(high[1:] - close[:-1])
        tr3 = np.abs(low[1:] - close[:-1])
        tr = np.maximum(tr1, np.maximum(tr2, tr3))

        atr = tr[-period:].mean()
        return float(atr)

    def calculate_bollinger_bands(
        self, series: pd.Series, period: int = 20, std_dev: float = 2.0
    ) -> tuple[float, float, float]:
        """Calculate Bollinger Bands

        Args:
            series: Price series
            period: Period
            std_dev: Standard deviation multiplier

        Returns:
            Tuple of (upper band, middle band, lower band)
        """
        if len(series) < period:
            mean = series.mean()
            return mean, mean, mean

        middle = series.iloc[-period:].mean()
        std = series.iloc[-period:].std()
        upper = middle + std_dev * std
        lower = middle - std_dev * std

        return float(upper), float(middle), float(lower)


class TrendFollowingStrategy(TradingStrategy):
    """Trend following strategy

    Logic:
    - MA crossover + MACD confirmation
    - Stop loss: price ± ATR × 2
    - Take profit: price ± ATR × 4
    """

    def __init__(self):
        super().__init__("TrendFollowing")
        self.fast_ma_period = 10
        self.slow_ma_period = 30

    def generate_signal(self, df: pd.DataFrame) -> Signal:
        """Generate signal based on trend following logic"""
        if len(df) < self.slow_ma_period:
            return Signal(
                action=SignalAction.HOLD,
                confidence=0.0,
                reason="Insufficient data for trend following",
            )

        close = df["close"]
        current_price = float(close.iloc[-1])

        # Calculate indicators
        fast_ma = self.calculate_ma(close, self.fast_ma_period)
        slow_ma = self.calculate_ma(close, self.slow_ma_period)
        macd, signal_line, histogram = self.calculate_macd(close)
        atr = self.calculate_atr(df)

        # Check for golden cross (bullish)
        if fast_ma > slow_ma and macd > signal_line and histogram > 0:
            confidence = min(0.85, 0.6 + abs(histogram) * 0.01)
            stop_loss = current_price - atr * 2
            take_profit = current_price + atr * 4

            return Signal(
                action=SignalAction.LONG,
                confidence=confidence,
                entry_price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                reason=f"Golden cross: MA{self.fast_ma_period} > MA{self.slow_ma_period}, MACD bullish",
            )

        # Check for death cross (bearish)
        elif fast_ma < slow_ma and macd < signal_line and histogram < 0:
            confidence = min(0.85, 0.6 + abs(histogram) * 0.01)
            stop_loss = current_price + atr * 2
            take_profit = current_price - atr * 4

            return Signal(
                action=SignalAction.SHORT,
                confidence=confidence,
                entry_price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                reason=f"Death cross: MA{self.fast_ma_period} < MA{self.slow_ma_period}, MACD bearish",
            )

        else:
            return Signal(
                action=SignalAction.HOLD,
                confidence=0.5,
                reason="No clear trend signal",
            )


class MeanReversionStrategy(TradingStrategy):
    """Mean reversion strategy

    Logic:
    - RSI overbought (>70) / oversold (<30) + Bollinger Bands
    - Take profit: reversion to middle band
    """

    def __init__(self):
        super().__init__("MeanReversion")
        self.rsi_period = 14
        self.bb_period = 20
        self.bb_std = 2.0

    def generate_signal(self, df: pd.DataFrame) -> Signal:
        """Generate signal based on mean reversion logic"""
        if len(df) < self.bb_period:
            return Signal(
                action=SignalAction.HOLD,
                confidence=0.0,
                reason="Insufficient data for mean reversion",
            )

        close = df["close"]
        current_price = float(close.iloc[-1])

        # Calculate indicators
        rsi = self.calculate_rsi(close, self.rsi_period)
        upper_bb, middle_bb, lower_bb = self.calculate_bollinger_bands(
            close, self.bb_period, self.bb_std
        )
        atr = self.calculate_atr(df)

        # Oversold condition (bullish)
        if rsi < 30 and current_price <= lower_bb:
            confidence = min(0.8, 0.5 + (30 - rsi) * 0.01)
            stop_loss = current_price - atr * 1.5
            take_profit = middle_bb

            return Signal(
                action=SignalAction.LONG,
                confidence=confidence,
                entry_price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                reason=f"Oversold: RSI={rsi:.1f}, price at lower BB",
            )

        # Overbought condition (bearish)
        elif rsi > 70 and current_price >= upper_bb:
            confidence = min(0.8, 0.5 + (rsi - 70) * 0.01)
            stop_loss = current_price + atr * 1.5
            take_profit = middle_bb

            return Signal(
                action=SignalAction.SHORT,
                confidence=confidence,
                entry_price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                reason=f"Overbought: RSI={rsi:.1f}, price at upper BB",
            )

        else:
            return Signal(
                action=SignalAction.HOLD,
                confidence=0.5,
                reason="No mean reversion signal",
            )


class BreakoutStrategy(TradingStrategy):
    """Breakout strategy

    Logic:
    - Price breaks previous high/low + volume surge (1.5x)
    - Take profit: breakout magnitude
    """

    def __init__(self):
        super().__init__("Breakout")
        self.lookback_period = 20
        self.volume_threshold = 1.5

    def generate_signal(self, df: pd.DataFrame) -> Signal:
        """Generate signal based on breakout logic"""
        if len(df) < self.lookback_period + 1:
            return Signal(
                action=SignalAction.HOLD,
                confidence=0.0,
                reason="Insufficient data for breakout",
            )

        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        current_price = float(close.iloc[-1])
        current_volume = float(volume.iloc[-1])

        # Calculate recent high/low and average volume
        recent_high = float(high.iloc[-self.lookback_period : -1].max())
        recent_low = float(low.iloc[-self.lookback_period : -1].min())
        avg_volume = float(volume.iloc[-self.lookback_period : -1].mean())

        atr = self.calculate_atr(df)

        # Bullish breakout
        if current_price > recent_high and current_volume > avg_volume * self.volume_threshold:
            breakout_magnitude = current_price - recent_high
            confidence = min(
                0.85, 0.6 + (current_volume / avg_volume - self.volume_threshold) * 0.1
            )
            stop_loss = recent_high - atr
            take_profit = current_price + breakout_magnitude

            return Signal(
                action=SignalAction.LONG,
                confidence=confidence,
                entry_price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                reason=f"Bullish breakout: price > {recent_high:.2f}, volume x{current_volume/avg_volume:.1f}",
            )

        # Bearish breakout
        elif current_price < recent_low and current_volume > avg_volume * self.volume_threshold:
            breakout_magnitude = recent_low - current_price
            confidence = min(
                0.85, 0.6 + (current_volume / avg_volume - self.volume_threshold) * 0.1
            )
            stop_loss = recent_low + atr
            take_profit = current_price - breakout_magnitude

            return Signal(
                action=SignalAction.SHORT,
                confidence=confidence,
                entry_price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                reason=f"Bearish breakout: price < {recent_low:.2f}, volume x{current_volume/avg_volume:.1f}",
            )

        else:
            return Signal(
                action=SignalAction.HOLD,
                confidence=0.5,
                reason="No breakout detected",
            )
