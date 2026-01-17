"""技术指标计算模块"""

import pandas as pd
import ta
from typing import List
from ..models.market import Kline, Indicators
from ..utils.logger import logger


def calculate_indicators(klines: List[Kline]) -> Indicators:
    """计算技术指标"""
    if not klines or len(klines) < 99:
        logger.warning("Not enough data for indicators")
        # Return zeros if not enough data
        return Indicators(
            ma7=0,
            ma25=0,
            ma99=0,
            rsi=0,
            macd=0,
            macd_signal=0,
            macd_histogram=0,
            boll_upper=0,
            boll_middle=0,
            boll_lower=0,
            atr=0,
        )

    # Convert to DataFrame
    df = pd.DataFrame([k.model_dump() for k in klines])

    # MA
    df["ma7"] = ta.trend.sma_indicator(df["close"], window=7)
    df["ma25"] = ta.trend.sma_indicator(df["close"], window=25)
    df["ma99"] = ta.trend.sma_indicator(df["close"], window=99)

    # RSI
    df["rsi"] = ta.momentum.rsi(df["close"], window=14)

    # MACD
    macd = ta.trend.MACD(df["close"])
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_hist"] = macd.macd_diff()

    # Bollinger Bands
    boll = ta.volatility.BollingerBands(df["close"], window=20, window_dev=2)
    df["boll_upper"] = boll.bollinger_hband()
    df["boll_mid"] = boll.bollinger_mavg()
    df["boll_lower"] = boll.bollinger_lband()

    # ATR
    df["atr"] = ta.volatility.average_true_range(
        df["high"], df["low"], df["close"], window=14
    )

    # Get last row
    last = df.iloc[-1]

    return Indicators(
        ma7=float(last["ma7"]),
        ma25=float(last["ma25"]),
        ma99=float(last["ma99"]),
        rsi=float(last["rsi"]),
        macd=float(last["macd"]),
        macd_signal=float(last["macd_signal"]),
        macd_histogram=float(last["macd_hist"]),
        boll_upper=float(last["boll_upper"]),
        boll_middle=float(last["boll_mid"]),
        boll_lower=float(last["boll_lower"]),
        atr=float(last["atr"]),
    )
