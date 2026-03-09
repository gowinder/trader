"""市场数据模型单元测试"""

from ai_trader.models.market import Indicators, Kline, MarketData


def _make_indicators(**overrides) -> Indicators:
    defaults = dict(
        ma7=100.0, ma25=99.0, ma99=98.0, rsi=55.0,
        macd=0.5, macd_signal=0.3, macd_histogram=0.2,
        boll_upper=105.0, boll_middle=100.0, boll_lower=95.0, atr=2.0,
    )
    defaults.update(overrides)
    return Indicators(**defaults)


def _make_kline(**overrides) -> Kline:
    defaults = dict(
        timestamp=1700000000, open=100.0, high=105.0,
        low=95.0, close=102.0, volume=1000.0,
    )
    defaults.update(overrides)
    return Kline(**defaults)


class TestIndicators:
    def test_indicators_create(self):
        ind = _make_indicators()
        assert ind.ma7 == 100.0
        assert ind.rsi == 55.0
        assert ind.atr == 2.0

    def test_indicators_negative_values(self):
        ind = _make_indicators(macd=-1.5, macd_histogram=-0.8)
        assert ind.macd == -1.5
        assert ind.macd_histogram == -0.8


class TestKline:
    def test_kline_create(self):
        k = _make_kline()
        assert k.timestamp == 1700000000
        assert k.open == 100.0
        assert k.close == 102.0
        assert k.volume == 1000.0


class TestMarketData:
    def test_market_data_create(self):
        klines = [_make_kline(timestamp=i) for i in range(3)]
        md = MarketData(
            symbol="BTC/USDT",
            current_price=50000.0,
            klines=klines,
            interval="1h",
            indicators=_make_indicators(),
            high_24h=51000.0,
            low_24h=49000.0,
            change_24h=2.5,
            volume_24h=1e9,
        )
        assert md.symbol == "BTC/USDT"
        assert md.current_price == 50000.0
        assert len(md.klines) == 3
        assert md.interval == "1h"
        assert md.high_24h == 51000.0

    def test_market_data_empty_klines(self):
        md = MarketData(
            symbol="ETH/USDT",
            current_price=3000.0,
            klines=[],
            interval="15m",
            indicators=_make_indicators(),
            high_24h=3100.0,
            low_24h=2900.0,
            change_24h=-1.0,
            volume_24h=5e8,
        )
        assert md.klines == []
