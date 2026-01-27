"""K-line pattern recognition module"""

from enum import Enum
from typing import Optional
import pandas as pd
import numpy as np
from pydantic import BaseModel, Field


class PatternType(Enum):
    """Pattern type enumeration"""

    HAMMER = "hammer"  # Hammer
    SHOOTING_STAR = "shooting_star"  # Shooting star
    DOJI = "doji"  # Doji
    ENGULFING_BULLISH = "engulfing_bullish"  # Bullish engulfing
    ENGULFING_BEARISH = "engulfing_bearish"  # Bearish engulfing
    MORNING_STAR = "morning_star"  # Morning star
    EVENING_STAR = "evening_star"  # Evening star
    DOUBLE_TOP = "double_top"  # Double top
    DOUBLE_BOTTOM = "double_bottom"  # Double bottom
    HEAD_SHOULDERS = "head_shoulders"  # Head and shoulders
    INVERSE_HEAD_SHOULDERS = "inverse_head_shoulders"  # Inverse head and shoulders
    UNKNOWN = "unknown"  # Unknown pattern


class PatternSignal(Enum):
    """Pattern signal enumeration"""

    BULLISH = "bullish"  # Bullish signal
    BEARISH = "bearish"  # Bearish signal
    NEUTRAL = "neutral"  # Neutral signal


class Pattern(BaseModel):
    """Pattern recognition result"""

    pattern_type: PatternType = Field(..., description="Pattern type")
    signal: PatternSignal = Field(..., description="Signal type")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence level")
    description: str = Field(..., description="Pattern description")
    location: int = Field(..., description="Pattern location (candle index)")


class PatternRecognizer:
    """K-line pattern recognizer"""

    def __init__(self, min_confidence: float = 0.6):
        """Initialize pattern recognizer

        Args:
            min_confidence: Minimum confidence threshold
        """
        self.min_confidence = min_confidence

    def detect_all(self, df: pd.DataFrame, lookback: int = 50) -> list[Pattern]:
        """Detect all patterns

        Args:
            df: OHLCV data (columns: open, high, low, close, volume)
            lookback: Lookback window size

        Returns:
            List of detected patterns
        """
        patterns = []

        # Limit detection range
        start_idx = max(0, len(df) - lookback)
        df_recent = df.iloc[start_idx:].copy()

        # Single candlestick patterns
        patterns.extend(self.detect_hammer(df_recent))
        patterns.extend(self.detect_shooting_star(df_recent))
        patterns.extend(self.detect_doji(df_recent))

        # Two candlestick patterns
        patterns.extend(self.detect_engulfing(df_recent))

        # Three candlestick patterns
        patterns.extend(self.detect_star_pattern(df_recent))

        # Chart patterns
        patterns.extend(self.detect_double_pattern(df_recent))
        patterns.extend(self.detect_head_shoulders(df_recent))

        # Filter by confidence
        patterns = [p for p in patterns if p.confidence >= self.min_confidence]

        return patterns

    def detect_hammer(self, df: pd.DataFrame) -> list[Pattern]:
        """Detect hammer/hanging man patterns

        Rules:
        - Body < 0.3 * (high - low)
        - Lower shadow > 2 * body
        - Upper shadow < 0.1 * (high - low)
        """
        patterns = []

        for i in range(len(df)):
            row = df.iloc[i]
            open_price = row["open"]
            high_price = row["high"]
            low_price = row["low"]
            close_price = row["close"]

            # Calculate components
            body = abs(close_price - open_price)
            total_range = high_price - low_price
            lower_shadow = min(open_price, close_price) - low_price
            upper_shadow = high_price - max(open_price, close_price)

            if total_range == 0:
                continue

            # Hammer rules
            body_ratio = body / total_range
            lower_ratio = lower_shadow / body if body > 0 else float("inf")
            upper_ratio = upper_shadow / total_range

            if body_ratio < 0.3 and lower_ratio > 2.0 and upper_ratio < 0.1:
                # Bullish hammer if appears in downtrend
                # Simplified: use close position to determine
                signal = (
                    PatternSignal.BULLISH
                    if close_price > open_price
                    else PatternSignal.BEARISH
                )
                confidence = min(0.9, 0.6 + (lower_ratio - 2.0) * 0.1)

                patterns.append(
                    Pattern(
                        pattern_type=PatternType.HAMMER,
                        signal=signal,
                        confidence=confidence,
                        description=f"Hammer pattern at index {i}",
                        location=i,
                    )
                )

        return patterns

    def detect_shooting_star(self, df: pd.DataFrame) -> list[Pattern]:
        """Detect shooting star patterns

        Rules:
        - Body < 0.3 * (high - low)
        - Upper shadow > 2 * body
        - Lower shadow < 0.1 * (high - low)
        """
        patterns = []

        for i in range(len(df)):
            row = df.iloc[i]
            open_price = row["open"]
            high_price = row["high"]
            low_price = row["low"]
            close_price = row["close"]

            body = abs(close_price - open_price)
            total_range = high_price - low_price
            lower_shadow = min(open_price, close_price) - low_price
            upper_shadow = high_price - max(open_price, close_price)

            if total_range == 0:
                continue

            body_ratio = body / total_range
            upper_ratio = upper_shadow / body if body > 0 else float("inf")
            lower_ratio = lower_shadow / total_range

            if body_ratio < 0.3 and upper_ratio > 2.0 and lower_ratio < 0.1:
                signal = PatternSignal.BEARISH
                confidence = min(0.9, 0.6 + (upper_ratio - 2.0) * 0.1)

                patterns.append(
                    Pattern(
                        pattern_type=PatternType.SHOOTING_STAR,
                        signal=signal,
                        confidence=confidence,
                        description=f"Shooting star pattern at index {i}",
                        location=i,
                    )
                )

        return patterns

    def detect_doji(self, df: pd.DataFrame) -> list[Pattern]:
        """Detect doji patterns

        Rules:
        - abs(close - open) < 0.1 * (high - low)
        """
        patterns = []

        for i in range(len(df)):
            row = df.iloc[i]
            open_price = row["open"]
            high_price = row["high"]
            low_price = row["low"]
            close_price = row["close"]

            body = abs(close_price - open_price)
            total_range = high_price - low_price

            if total_range == 0:
                continue

            body_ratio = body / total_range

            if body_ratio < 0.1:
                signal = PatternSignal.NEUTRAL
                confidence = 0.7

                patterns.append(
                    Pattern(
                        pattern_type=PatternType.DOJI,
                        signal=signal,
                        confidence=confidence,
                        description=f"Doji pattern at index {i}",
                        location=i,
                    )
                )

        return patterns

    def detect_engulfing(self, df: pd.DataFrame) -> list[Pattern]:
        """Detect engulfing patterns

        Rules:
        - Second candle completely engulfs first candle's body
        """
        patterns = []

        for i in range(1, len(df)):
            prev_row = df.iloc[i - 1]
            curr_row = df.iloc[i]

            prev_open = prev_row["open"]
            prev_close = prev_row["close"]
            curr_open = curr_row["open"]
            curr_close = curr_row["close"]

            prev_body_top = max(prev_open, prev_close)
            prev_body_bottom = min(prev_open, prev_close)
            curr_body_top = max(curr_open, curr_close)
            curr_body_bottom = min(curr_open, curr_close)

            # Bullish engulfing
            if (
                prev_close < prev_open  # Previous bearish
                and curr_close > curr_open  # Current bullish
                and curr_body_bottom < prev_body_bottom
                and curr_body_top > prev_body_top
            ):
                confidence = 0.75
                patterns.append(
                    Pattern(
                        pattern_type=PatternType.ENGULFING_BULLISH,
                        signal=PatternSignal.BULLISH,
                        confidence=confidence,
                        description=f"Bullish engulfing at index {i}",
                        location=i,
                    )
                )

            # Bearish engulfing
            elif (
                prev_close > prev_open  # Previous bullish
                and curr_close < curr_open  # Current bearish
                and curr_body_top > prev_body_top
                and curr_body_bottom < prev_body_bottom
            ):
                confidence = 0.75
                patterns.append(
                    Pattern(
                        pattern_type=PatternType.ENGULFING_BEARISH,
                        signal=PatternSignal.BEARISH,
                        confidence=confidence,
                        description=f"Bearish engulfing at index {i}",
                        location=i,
                    )
                )

        return patterns

    def detect_star_pattern(self, df: pd.DataFrame) -> list[Pattern]:
        """Detect morning star and evening star patterns

        Rules (morning star):
        - First candle: bearish
        - Second candle: small body (gap down)
        - Third candle: bullish (closes above first candle's midpoint)
        """
        patterns = []

        for i in range(2, len(df)):
            first = df.iloc[i - 2]
            second = df.iloc[i - 1]
            third = df.iloc[i]

            first_body = abs(first["close"] - first["open"])
            second_body = abs(second["close"] - second["open"])
            third_body = abs(third["close"] - third["open"])

            # Morning star
            if (
                first["close"] < first["open"]  # First bearish
                and second_body < first_body * 0.5  # Small second body
                and third["close"] > third["open"]  # Third bullish
                and third["close"]
                > (first["open"] + first["close"]) / 2  # Above midpoint
            ):
                confidence = 0.8
                patterns.append(
                    Pattern(
                        pattern_type=PatternType.MORNING_STAR,
                        signal=PatternSignal.BULLISH,
                        confidence=confidence,
                        description=f"Morning star at index {i}",
                        location=i,
                    )
                )

            # Evening star
            elif (
                first["close"] > first["open"]  # First bullish
                and second_body < first_body * 0.5  # Small second body
                and third["close"] < third["open"]  # Third bearish
                and third["close"]
                < (first["open"] + first["close"]) / 2  # Below midpoint
            ):
                confidence = 0.8
                patterns.append(
                    Pattern(
                        pattern_type=PatternType.EVENING_STAR,
                        signal=PatternSignal.BEARISH,
                        confidence=confidence,
                        description=f"Evening star at index {i}",
                        location=i,
                    )
                )

        return patterns

    def detect_double_pattern(self, df: pd.DataFrame) -> list[Pattern]:
        """Detect double top and double bottom patterns

        Rules:
        - Two peaks/troughs at similar price levels
        - Separated by at least 10 candles
        - Price tolerance: 2%
        """
        patterns = []

        if len(df) < 20:
            return patterns

        highs = df["high"].values
        lows = df["low"].values

        # Double top
        for i in range(10, len(df) - 10):
            left_peak = highs[i]
            # Find second peak
            for j in range(i + 10, min(i + 30, len(df))):
                right_peak = highs[j]
                # Check if similar levels (within 2%)
                if abs(right_peak - left_peak) / left_peak < 0.02:
                    # Check if peaks are local maxima
                    if (
                        left_peak == max(highs[i - 5 : i + 5])
                        and right_peak == max(highs[j - 5 : j + 5])
                    ):
                        confidence = 0.7
                        patterns.append(
                            Pattern(
                                pattern_type=PatternType.DOUBLE_TOP,
                                signal=PatternSignal.BEARISH,
                                confidence=confidence,
                                description=f"Double top at indices {i}, {j}",
                                location=j,
                            )
                        )
                        break

        # Double bottom
        for i in range(10, len(df) - 10):
            left_trough = lows[i]
            for j in range(i + 10, min(i + 30, len(df))):
                right_trough = lows[j]
                if abs(right_trough - left_trough) / left_trough < 0.02:
                    if (
                        left_trough == min(lows[i - 5 : i + 5])
                        and right_trough == min(lows[j - 5 : j + 5])
                    ):
                        confidence = 0.7
                        patterns.append(
                            Pattern(
                                pattern_type=PatternType.DOUBLE_BOTTOM,
                                signal=PatternSignal.BULLISH,
                                confidence=confidence,
                                description=f"Double bottom at indices {i}, {j}",
                                location=j,
                            )
                        )
                        break

        return patterns

    def detect_head_shoulders(self, df: pd.DataFrame) -> list[Pattern]:
        """Detect head and shoulders patterns

        Rules:
        - Three peaks: left shoulder, head (highest), right shoulder
        - Shoulders at similar levels
        """
        patterns = []

        if len(df) < 30:
            return patterns

        highs = df["high"].values
        lows = df["low"].values

        # Head and shoulders (bearish)
        for i in range(10, len(df) - 20):
            left_shoulder = highs[i]
            # Find head (10-15 candles later)
            for j in range(i + 5, i + 15):
                head = highs[j]
                # Head must be higher than left shoulder
                if head <= left_shoulder * 1.05:
                    continue
                # Find right shoulder
                for k in range(j + 5, min(j + 15, len(df))):
                    right_shoulder = highs[k]
                    # Shoulders at similar levels (within 3%)
                    if abs(right_shoulder - left_shoulder) / left_shoulder > 0.03:
                        continue
                    # Right shoulder lower than head
                    if right_shoulder >= head * 0.95:
                        continue
                    # Verify local peaks
                    if (
                        left_shoulder == max(highs[i - 3 : i + 3])
                        and head == max(highs[j - 3 : j + 3])
                        and right_shoulder == max(highs[k - 3 : k + 3])
                    ):
                        confidence = 0.75
                        patterns.append(
                            Pattern(
                                pattern_type=PatternType.HEAD_SHOULDERS,
                                signal=PatternSignal.BEARISH,
                                confidence=confidence,
                                description=f"Head and shoulders at {i}, {j}, {k}",
                                location=k,
                            )
                        )

        # Inverse head and shoulders (bullish)
        for i in range(10, len(df) - 20):
            left_shoulder = lows[i]
            for j in range(i + 5, i + 15):
                head = lows[j]
                if head >= left_shoulder * 0.95:
                    continue
                for k in range(j + 5, min(j + 15, len(df))):
                    right_shoulder = lows[k]
                    if abs(right_shoulder - left_shoulder) / left_shoulder > 0.03:
                        continue
                    if right_shoulder <= head * 1.05:
                        continue
                    if (
                        left_shoulder == min(lows[i - 3 : i + 3])
                        and head == min(lows[j - 3 : j + 3])
                        and right_shoulder == min(lows[k - 3 : k + 3])
                    ):
                        confidence = 0.75
                        patterns.append(
                            Pattern(
                                pattern_type=PatternType.INVERSE_HEAD_SHOULDERS,
                                signal=PatternSignal.BULLISH,
                                confidence=confidence,
                                description=f"Inverse H&S at {i}, {j}, {k}",
                                location=k,
                            )
                        )

        return patterns
