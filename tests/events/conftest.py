"""Shared test helpers for events tests."""

from ai_trader.models.market import Indicators, Kline, MarketData


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
