"""Tests for all 7 market event detectors."""

from unittest.mock import MagicMock

import pytest

from ai_trader.events.detectors import (
    BollingerBreakDetector,
    MACDCrossDetector,
    MarketStateChangeDetector,
    PositionPnLDetector,
    PriceSurgeDetector,
    RSIExtremeDetector,
    VolumeSpikeDetector,
)
from ai_trader.events.models import TriggerEvent
from ai_trader.models.market import Indicators, Kline, MarketData


# ── helpers ──────────────────────────────────────────────────────────


def _make_indicators(**overrides) -> Indicators:
    defaults = dict(
        ma7=100.0,
        ma25=100.0,
        ma99=100.0,
        rsi=50.0,
        macd=0.0,
        macd_signal=0.0,
        macd_histogram=0.0,
        boll_upper=110.0,
        boll_middle=100.0,
        boll_lower=90.0,
        atr=2.0,
    )
    defaults.update(overrides)
    return Indicators(**defaults)


def _make_kline(close: float, volume: float = 1000.0, ts_offset: int = 0) -> Kline:
    return Kline(
        timestamp=1700000000 + ts_offset * 60,
        open=close,
        high=close + 1,
        low=close - 1,
        close=close,
        volume=volume,
    )


def _make_market_data(
    current_price: float = 100.0,
    indicators: Indicators | None = None,
    klines: list[Kline] | None = None,
    interval: str = "5m",
) -> MarketData:
    if indicators is None:
        indicators = _make_indicators()
    if klines is None:
        klines = [_make_kline(100.0, ts_offset=i) for i in range(30)]
    return MarketData(
        symbol="BTCUSDT",
        current_price=current_price,
        klines=klines,
        interval=interval,
        indicators=indicators,
        high_24h=105.0,
        low_24h=95.0,
        change_24h=1.0,
        volume_24h=50000.0,
    )


# ── PriceSurgeDetector ───────────────────────────────────────────────


class TestPriceSurgeDetector:
    def test_no_trigger_normal_price(self):
        """Price within ATR range -> no trigger."""
        det = PriceSurgeDetector(atr_multiplier=1.5, lookback_seconds=300)
        md = _make_market_data(current_price=100.0)
        result = det.check(md, md.indicators, None)
        assert result is None

    def test_trigger_on_price_drop(self):
        """Price drops 4+ with ATR=2 -> trigger (abs 4 > 2*1.5=3)."""
        det = PriceSurgeDetector(atr_multiplier=1.5, lookback_seconds=300)
        # 5m interval, lookback_seconds=300 -> 1 bar ago
        # Build klines: older bars at close=104, latest at close=100
        klines = [_make_kline(104.0, ts_offset=i) for i in range(30)]
        md = _make_market_data(
            current_price=100.0,
            indicators=_make_indicators(atr=2.0),
            klines=klines,
        )
        result = det.check(md, md.indicators, None)
        assert result is not None
        assert isinstance(result, TriggerEvent)
        assert result.event_type == "price_surge"
        assert result.key_data["direction"] == "down"

    def test_severity_high_when_gt_2x_atr(self):
        """abs(change) > 2*ATR -> severity high."""
        det = PriceSurgeDetector(atr_multiplier=1.5, lookback_seconds=300)
        klines = [_make_kline(106.0, ts_offset=i) for i in range(30)]
        md = _make_market_data(
            current_price=100.0,
            indicators=_make_indicators(atr=2.0),
            klines=klines,
        )
        result = det.check(md, md.indicators, None)
        assert result is not None
        assert result.severity == "high"


# ── VolumeSpikeDetector ──────────────────────────────────────────────


class TestVolumeSpikeDetector:
    def test_no_trigger_normal_volume(self):
        det = VolumeSpikeDetector(volume_multiplier=2.5)
        klines = [_make_kline(100.0, volume=1000.0, ts_offset=i) for i in range(25)]
        md = _make_market_data(klines=klines)
        result = det.check(md, md.indicators, None)
        assert result is None

    def test_trigger_on_volume_spike(self):
        """Latest volume 3x average -> trigger (3.0 > 2.5)."""
        det = VolumeSpikeDetector(volume_multiplier=2.5)
        klines = [_make_kline(100.0, volume=1000.0, ts_offset=i) for i in range(24)]
        klines.append(_make_kline(100.0, volume=3000.0, ts_offset=24))
        md = _make_market_data(klines=klines)
        result = det.check(md, md.indicators, None)
        assert result is not None
        assert result.event_type == "volume_spike"
        assert result.severity == "medium"

    def test_severity_high_on_extreme_spike(self):
        det = VolumeSpikeDetector(volume_multiplier=2.5)
        klines = [_make_kline(100.0, volume=1000.0, ts_offset=i) for i in range(24)]
        klines.append(_make_kline(100.0, volume=5000.0, ts_offset=24))
        md = _make_market_data(klines=klines)
        result = det.check(md, md.indicators, None)
        assert result is not None
        assert result.severity == "high"


# ── RSIExtremeDetector ───────────────────────────────────────────────


class TestRSIExtremeDetector:
    def test_no_trigger_at_50(self):
        det = RSIExtremeDetector()
        md = _make_market_data(indicators=_make_indicators(rsi=50.0))
        result = det.check(md, md.indicators, None)
        assert result is None

    def test_trigger_oversold(self):
        det = RSIExtremeDetector(upper_threshold=75, lower_threshold=25)
        md = _make_market_data(indicators=_make_indicators(rsi=20.0))
        result = det.check(md, md.indicators, None)
        assert result is not None
        assert result.event_type == "rsi_extreme"
        assert "超卖" in result.description or "oversold" in result.description.lower()

    def test_trigger_overbought(self):
        det = RSIExtremeDetector(upper_threshold=75, lower_threshold=25)
        md = _make_market_data(indicators=_make_indicators(rsi=80.0))
        result = det.check(md, md.indicators, None)
        assert result is not None
        assert "超买" in result.description or "overbought" in result.description.lower()


# ── MACDCrossDetector ────────────────────────────────────────────────


class TestMACDCrossDetector:
    def test_no_trigger_first_call(self):
        det = MACDCrossDetector()
        md = _make_market_data(indicators=_make_indicators(macd=1.0, macd_signal=0.5))
        result = det.check(md, md.indicators, None)
        assert result is None

    def test_trigger_golden_cross(self):
        det = MACDCrossDetector()
        # First call: MACD < signal
        md1 = _make_market_data(indicators=_make_indicators(macd=-0.5, macd_signal=0.5))
        det.check(md1, md1.indicators, None)

        # Second call: MACD > signal -> golden cross
        md2 = _make_market_data(indicators=_make_indicators(macd=1.0, macd_signal=0.5))
        result = det.check(md2, md2.indicators, None)
        assert result is not None
        assert result.event_type == "macd_cross"
        assert result.key_data["cross_type"] == "golden"

    def test_trigger_death_cross(self):
        det = MACDCrossDetector()
        md1 = _make_market_data(indicators=_make_indicators(macd=1.0, macd_signal=0.5))
        det.check(md1, md1.indicators, None)

        md2 = _make_market_data(indicators=_make_indicators(macd=-0.5, macd_signal=0.5))
        result = det.check(md2, md2.indicators, None)
        assert result is not None
        assert result.key_data["cross_type"] == "death"


# ── BollingerBreakDetector ───────────────────────────────────────────


class TestBollingerBreakDetector:
    def test_no_trigger_within_bands(self):
        det = BollingerBreakDetector()
        md = _make_market_data(
            current_price=100.0,
            indicators=_make_indicators(boll_upper=110.0, boll_lower=90.0),
        )
        result = det.check(md, md.indicators, None)
        assert result is None

    def test_trigger_above_upper(self):
        det = BollingerBreakDetector()
        md = _make_market_data(
            current_price=112.0,
            indicators=_make_indicators(boll_upper=110.0, boll_middle=100.0),
        )
        result = det.check(md, md.indicators, None)
        assert result is not None
        assert result.event_type == "bollinger_break"
        assert result.key_data["direction"] == "upper"

    def test_trigger_below_lower(self):
        det = BollingerBreakDetector()
        md = _make_market_data(
            current_price=88.0,
            indicators=_make_indicators(boll_lower=90.0, boll_middle=100.0),
        )
        result = det.check(md, md.indicators, None)
        assert result is not None
        assert result.key_data["direction"] == "lower"


# ── MarketStateChangeDetector ────────────────────────────────────────


class TestMarketStateChangeDetector:
    def test_no_trigger_first_call(self):
        det = MarketStateChangeDetector()
        result = det.check_state_change("sideways")
        assert result is None

    def test_no_trigger_same_state(self):
        det = MarketStateChangeDetector()
        det.check_state_change("sideways")
        result = det.check_state_change("sideways")
        assert result is None

    def test_trigger_on_state_change(self):
        det = MarketStateChangeDetector()
        det.check_state_change("sideways")
        result = det.check_state_change("breakout")
        assert result is not None
        assert result.event_type == "market_state_change"
        assert result.severity == "high"

    def test_severity_medium_for_non_breakout(self):
        det = MarketStateChangeDetector()
        det.check_state_change("sideways")
        result = det.check_state_change("trending")
        assert result is not None
        assert result.severity == "medium"


# ── PositionPnLDetector ──────────────────────────────────────────────


class TestPositionPnLDetector:
    def test_no_trigger_no_position(self):
        det = PositionPnLDetector()
        md = _make_market_data()
        result = det.check(md, md.indicators, None)
        assert result is None

    def test_no_trigger_zero_size(self):
        det = PositionPnLDetector()
        pos = MagicMock()
        pos.size = 0
        pos.roi = 5.0
        md = _make_market_data()
        result = det.check(md, md.indicators, pos)
        assert result is None

    def test_trigger_profit_threshold(self):
        det = PositionPnLDetector(profit_threshold=3.0, loss_threshold=-2.0)
        pos = MagicMock()
        pos.size = 1.0
        pos.roi = 4.0
        pos.symbol = "BTCUSDT"
        md = _make_market_data()
        result = det.check(md, md.indicators, pos)
        assert result is not None
        assert result.event_type == "position_pnl"
        assert result.severity == "medium"

    def test_trigger_loss_threshold(self):
        det = PositionPnLDetector(profit_threshold=3.0, loss_threshold=-2.0)
        pos = MagicMock()
        pos.size = 1.0
        pos.roi = -3.0
        pos.symbol = "BTCUSDT"
        md = _make_market_data()
        result = det.check(md, md.indicators, pos)
        assert result is not None
        assert result.severity == "high"
