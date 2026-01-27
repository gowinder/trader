"""Market state classification module"""

from enum import Enum
import pandas as pd
import numpy as np
from pydantic import BaseModel, Field


class MarketState(Enum):
    """Market state enumeration"""

    STRONG_TREND = "strong_trend"  # Strong trend (ADX > 25)
    WEAK_TREND = "weak_trend"  # Weak trend (20 < ADX <= 25)
    RANGE_BOUND = "range_bound"  # Range bound (ADX < 20, high volatility)
    SIDEWAYS = "sideways"  # Sideways (ADX < 20, low volatility)
    BREAKOUT = "breakout"  # Breakout (volume spike + price breakout)


class MarketClassification(BaseModel):
    """Market classification result"""

    state: MarketState = Field(..., description="Market state")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence level")
    adx_value: float = Field(..., description="ADX value")
    volatility: float = Field(..., description="Volatility (ATR percentage)")
    volume_ratio: float = Field(..., description="Volume ratio (current/average)")
    trend_direction: int = Field(..., description="Trend direction (1: up, -1: down, 0: neutral)")


class MarketClassifier:
    """Market state classifier"""

    def __init__(self, adx_period: int = 14, atr_period: int = 14, volume_period: int = 20):
        """Initialize market classifier

        Args:
            adx_period: ADX calculation period
            atr_period: ATR calculation period
            volume_period: Volume average period
        """
        self.adx_period = adx_period
        self.atr_period = atr_period
        self.volume_period = volume_period

    def classify(self, df: pd.DataFrame) -> MarketClassification:
        """Classify market state

        Args:
            df: OHLCV data (columns: open, high, low, close, volume)

        Returns:
            Market classification result
        """
        # Calculate indicators
        adx_value = self.calculate_adx(df)
        volatility = self.calculate_volatility(df)
        volume_ratio = self.calculate_volume_ratio(df)
        trend_direction = self.calculate_trend_direction(df)

        # Classify state
        state, confidence = self._classify_state(adx_value, volatility, volume_ratio, df)

        return MarketClassification(
            state=state,
            confidence=confidence,
            adx_value=adx_value,
            volatility=volatility,
            volume_ratio=volume_ratio,
            trend_direction=trend_direction,
        )

    def calculate_adx(self, df: pd.DataFrame) -> float:
        """Calculate ADX (Average Directional Index)

        ADX algorithm:
        1. Calculate True Range (TR)
        2. Calculate +DM and -DM
        3. Smooth TR, +DM, -DM with EMA
        4. Calculate +DI and -DI
        5. Calculate DX
        6. Smooth DX with EMA to get ADX

        Args:
            df: OHLCV data

        Returns:
            ADX value (0-100)
        """
        # Need at least adx_period * 2 + 1 candles for ADX calculation
        min_length = self.adx_period * 2 + 1
        if len(df) < min_length:
            return 0.0

        high = df["high"].values
        low = df["low"].values
        close = df["close"].values

        # Calculate True Range
        tr1 = high[1:] - low[1:]
        tr2 = np.abs(high[1:] - close[:-1])
        tr3 = np.abs(low[1:] - close[:-1])
        tr = np.maximum(tr1, np.maximum(tr2, tr3))

        # Calculate +DM and -DM
        high_diff = high[1:] - high[:-1]
        low_diff = low[:-1] - low[1:]

        plus_dm = np.where((high_diff > low_diff) & (high_diff > 0), high_diff, 0)
        minus_dm = np.where((low_diff > high_diff) & (low_diff > 0), low_diff, 0)

        # Smooth with EMA (Wilder's smoothing)
        alpha = 1.0 / self.adx_period

        # Initialize smoothed values
        tr_smooth = np.zeros_like(tr)
        plus_dm_smooth = np.zeros_like(plus_dm)
        minus_dm_smooth = np.zeros_like(minus_dm)

        # Check if we have enough data for smoothing
        if len(tr) < self.adx_period:
            return 0.0

        # First value is simple average
        tr_smooth[self.adx_period - 1] = tr[: self.adx_period].mean()
        plus_dm_smooth[self.adx_period - 1] = plus_dm[: self.adx_period].mean()
        minus_dm_smooth[self.adx_period - 1] = minus_dm[: self.adx_period].mean()

        # Apply Wilder's smoothing
        for i in range(self.adx_period, len(tr)):
            tr_smooth[i] = tr_smooth[i - 1] * (1 - alpha) + tr[i] * alpha
            plus_dm_smooth[i] = plus_dm_smooth[i - 1] * (1 - alpha) + plus_dm[i] * alpha
            minus_dm_smooth[i] = minus_dm_smooth[i - 1] * (1 - alpha) + minus_dm[i] * alpha

        # Calculate +DI and -DI
        plus_di = np.zeros_like(tr_smooth)
        minus_di = np.zeros_like(tr_smooth)

        valid_idx = tr_smooth > 0
        plus_di[valid_idx] = 100 * plus_dm_smooth[valid_idx] / tr_smooth[valid_idx]
        minus_di[valid_idx] = 100 * minus_dm_smooth[valid_idx] / tr_smooth[valid_idx]

        # Calculate DX
        dx = np.zeros_like(plus_di)
        di_sum = plus_di + minus_di
        valid_idx = di_sum > 0
        dx[valid_idx] = 100 * np.abs(plus_di[valid_idx] - minus_di[valid_idx]) / di_sum[valid_idx]

        # Smooth DX to get ADX
        adx = np.zeros_like(dx)

        # Need enough data for second smoothing
        if len(dx) < self.adx_period * 2 - 1:
            return 0.0

        adx[self.adx_period * 2 - 2] = dx[self.adx_period - 1 : self.adx_period * 2 - 1].mean()

        for i in range(self.adx_period * 2 - 1, len(adx)):
            adx[i] = adx[i - 1] * (1 - alpha) + dx[i] * alpha

        # Return latest ADX value
        return float(adx[-1]) if len(adx) > 0 and adx[-1] > 0 else 0.0

    def calculate_volatility(self, df: pd.DataFrame) -> float:
        """Calculate volatility (ATR percentage)

        Args:
            df: OHLCV data

        Returns:
            Volatility as percentage of price
        """
        if len(df) < self.atr_period + 1:
            return 0.0

        high = df["high"].values
        low = df["low"].values
        close = df["close"].values

        # Calculate True Range
        tr1 = high[1:] - low[1:]
        tr2 = np.abs(high[1:] - close[:-1])
        tr3 = np.abs(low[1:] - close[:-1])
        tr = np.maximum(tr1, np.maximum(tr2, tr3))

        # Calculate ATR using EMA
        atr = tr[-self.atr_period :].mean()

        # Return as percentage of current price
        current_price = close[-1]
        volatility_pct = (atr / current_price) * 100 if current_price > 0 else 0.0

        return float(volatility_pct)

    def calculate_volume_ratio(self, df: pd.DataFrame) -> float:
        """Calculate volume ratio (current volume / average volume)

        Args:
            df: OHLCV data

        Returns:
            Volume ratio
        """
        if len(df) < self.volume_period + 1:
            return 1.0

        volumes = df["volume"].values
        current_volume = volumes[-1]
        avg_volume = volumes[-self.volume_period :].mean()

        return float(current_volume / avg_volume) if avg_volume > 0 else 1.0

    def calculate_trend_direction(self, df: pd.DataFrame) -> int:
        """Calculate trend direction using moving averages

        Args:
            df: OHLCV data

        Returns:
            1 (uptrend), -1 (downtrend), 0 (neutral)
        """
        if len(df) < 50:
            return 0

        close = df["close"].values
        ma20 = close[-20:].mean()
        ma50 = close[-50:].mean()

        if ma20 > ma50 * 1.02:
            return 1
        elif ma20 < ma50 * 0.98:
            return -1
        else:
            return 0

    def _classify_state(
        self, adx: float, volatility: float, volume_ratio: float, df: pd.DataFrame
    ) -> tuple[MarketState, float]:
        """Classify market state based on indicators

        Classification rules:
        - Breakout: volume_ratio > 2.0 + price breakout
        - Strong trend: ADX > 25
        - Weak trend: 20 < ADX <= 25
        - Range bound: ADX < 20 + volatility > 1.0%
        - Sideways: ADX < 20 + volatility <= 1.0%

        Args:
            adx: ADX value
            volatility: Volatility percentage
            volume_ratio: Volume ratio
            df: OHLCV data

        Returns:
            Tuple of (state, confidence)
        """
        # Check for breakout
        if volume_ratio > 2.0:
            # Check if price breaks recent high/low
            recent_high = df["high"].iloc[-20:].max()
            recent_low = df["low"].iloc[-20:].max()
            current_close = df["close"].iloc[-1]

            if current_close > recent_high or current_close < recent_low:
                confidence = min(0.9, 0.6 + (volume_ratio - 2.0) * 0.1)
                return MarketState.BREAKOUT, confidence

        # Classify by ADX
        if adx > 25:
            # Strong trend
            confidence = min(0.95, 0.7 + (adx - 25) * 0.01)
            return MarketState.STRONG_TREND, confidence

        elif adx > 20:
            # Weak trend
            confidence = 0.7
            return MarketState.WEAK_TREND, confidence

        else:
            # ADX < 20: Range bound or sideways
            if volatility > 1.0:
                confidence = 0.75
                return MarketState.RANGE_BOUND, confidence
            else:
                confidence = 0.8
                return MarketState.SIDEWAYS, confidence
