"""测试 K 线形态识别模块"""

import pytest
import pandas as pd
import numpy as np
from ai_trader.strategies.pattern_recognition import (
    PatternRecognizer,
    PatternType,
    PatternSignal,
)


def _make_df(rows):
    """构造 OHLCV DataFrame"""
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"])
    return df


class TestDetectHammer:
    def test_detect_hammer(self):
        # Hammer: 小实体, 长下影, 短上影
        # open=100, close=101, high=101.5, low=95
        # body=1, range=6.5, lower_shadow=5, upper_shadow=0.5
        # body_ratio=0.154<0.3, lower_ratio=5>2, upper_ratio=0.077<0.1
        df = _make_df([[100, 101.5, 95, 101, 1000]])
        recognizer = PatternRecognizer(min_confidence=0.0)
        patterns = recognizer.detect_hammer(df)
        assert len(patterns) == 1
        assert patterns[0].pattern_type == PatternType.HAMMER
        assert patterns[0].signal == PatternSignal.BULLISH  # close > open

    def test_detect_hammer_bearish(self):
        # close < open => bearish signal
        # open=101, close=100, high=101.5, low=95
        df = _make_df([[101, 101.5, 95, 100, 1000]])
        recognizer = PatternRecognizer(min_confidence=0.0)
        patterns = recognizer.detect_hammer(df)
        assert len(patterns) == 1
        assert patterns[0].signal == PatternSignal.BEARISH


class TestDetectShootingStar:
    def test_detect_shooting_star(self):
        # Shooting star: 小实体, 长上影, 短下影
        # open=100, close=99, high=106, low=98.5
        # body=1, range=7.5, upper_shadow=6, lower_shadow=0.5
        # body_ratio=0.133<0.3, upper_ratio=6>2, lower_ratio=0.067<0.1
        df = _make_df([[100, 106, 98.5, 99, 1000]])
        recognizer = PatternRecognizer(min_confidence=0.0)
        patterns = recognizer.detect_shooting_star(df)
        assert len(patterns) == 1
        assert patterns[0].pattern_type == PatternType.SHOOTING_STAR
        assert patterns[0].signal == PatternSignal.BEARISH


class TestDetectDoji:
    def test_detect_doji(self):
        # Doji: open ≈ close
        # open=100, close=100.05, high=102, low=98
        # body=0.05, range=4, body_ratio=0.0125<0.1
        df = _make_df([[100, 102, 98, 100.05, 1000]])
        recognizer = PatternRecognizer(min_confidence=0.0)
        patterns = recognizer.detect_doji(df)
        assert len(patterns) == 1
        assert patterns[0].pattern_type == PatternType.DOJI
        assert patterns[0].signal == PatternSignal.NEUTRAL


class TestDetectEngulfing:
    def test_detect_engulfing_bullish(self):
        # 前一根: bearish (open=102, close=100)
        # 当前: bullish (open=99, close=103), 完全吞没前一根实体
        df = _make_df([
            [102, 103, 99, 100, 1000],   # prev: bearish
            [99, 104, 98, 103, 1500],     # curr: bullish engulfing
        ])
        recognizer = PatternRecognizer(min_confidence=0.0)
        patterns = recognizer.detect_engulfing(df)
        assert len(patterns) == 1
        assert patterns[0].pattern_type == PatternType.ENGULFING_BULLISH
        assert patterns[0].signal == PatternSignal.BULLISH

    def test_detect_engulfing_bearish(self):
        # 前一根: bullish (open=98, close=100)
        # 当前: bearish (open=101, close=97), 完全吞没前一根实体
        df = _make_df([
            [98, 101, 97, 100, 1000],     # prev: bullish
            [101, 102, 96, 97, 1500],      # curr: bearish engulfing
        ])
        recognizer = PatternRecognizer(min_confidence=0.0)
        patterns = recognizer.detect_engulfing(df)
        assert len(patterns) == 1
        assert patterns[0].pattern_type == PatternType.ENGULFING_BEARISH
        assert patterns[0].signal == PatternSignal.BEARISH


class TestDetectNoPattern:
    def test_detect_no_pattern(self):
        # 普通 K 线，不满足任何单根形态条件
        # body_ratio ~ 0.5, 上下影线均匀
        df = _make_df([[100, 104, 98, 103, 1000]])
        recognizer = PatternRecognizer(min_confidence=0.0)
        assert recognizer.detect_hammer(df) == []
        assert recognizer.detect_shooting_star(df) == []
        assert recognizer.detect_doji(df) == []


class TestDetectAllFilters:
    def test_detect_all_filters_by_confidence(self):
        # Doji confidence = 0.7, 用 min_confidence=0.8 过滤掉
        df = _make_df([[100, 102, 98, 100.05, 1000]])
        recognizer = PatternRecognizer(min_confidence=0.8)
        patterns = recognizer.detect_all(df)
        doji_patterns = [p for p in patterns if p.pattern_type == PatternType.DOJI]
        assert len(doji_patterns) == 0

    def test_detect_all_includes_above_threshold(self):
        # Doji confidence = 0.7, min_confidence=0.6 不过滤
        df = _make_df([[100, 102, 98, 100.05, 1000]])
        recognizer = PatternRecognizer(min_confidence=0.6)
        patterns = recognizer.detect_all(df)
        doji_patterns = [p for p in patterns if p.pattern_type == PatternType.DOJI]
        assert len(doji_patterns) == 1


class TestEmptyDataFrame:
    def test_empty_dataframe(self):
        df = _make_df([])
        recognizer = PatternRecognizer(min_confidence=0.0)
        assert recognizer.detect_hammer(df) == []
        assert recognizer.detect_shooting_star(df) == []
        assert recognizer.detect_doji(df) == []
        assert recognizer.detect_engulfing(df) == []
        assert recognizer.detect_star_pattern(df) == []
        assert recognizer.detect_double_pattern(df) == []
        assert recognizer.detect_all(df) == []


class TestDoublePatternInsufficientData:
    def test_detect_double_pattern_insufficient_data(self):
        # 少于 20 根 K 线，返回空
        rows = [[100 + i, 102 + i, 99 + i, 101 + i, 1000] for i in range(15)]
        df = _make_df(rows)
        recognizer = PatternRecognizer(min_confidence=0.0)
        patterns = recognizer.detect_double_pattern(df)
        assert patterns == []
