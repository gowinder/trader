# AI量化交易系统 - Phase 4: 量化策略模型集成

> 本文档是 [AI量化交易系统升级规划](./ai_quant_system_plan.md) 的子文档

**预计时间**: 16天

---

## 目标

引入传统量化策略，实现K线形态识别、市场状态分类、混合决策系统。

---

## 关键任务

### 4.1 引入量化库

**依赖更新**:
```toml
[dependencies]
pandas-ta = ">=0.3.14"  # 高级技术指标
scipy = ">=1.11.0"      # 数学计算
```

---

### 4.2 K线形态识别

**文件**: `src/ai_trader/strategies/pattern_recognition.py`

实现形态：
- 锤子线/上吊线（反转信号）
- 吞没形态（反转）
- 十字星（变盘）
- 头肩顶/底（大级别反转）
- 双顶/双底（M/W形态）
- 三角形整理（突破待确认）

```python
"""K线形态识别模块"""

from typing import List, Optional
from enum import Enum
from pydantic import BaseModel
from datetime import datetime

from ..models.market import Kline


class PatternType(str, Enum):
    """形态类型"""
    # 反转形态
    HAMMER = "hammer"              # 锤子线 (看涨)
    HANGING_MAN = "hanging_man"    # 上吊线 (看跌)
    BULLISH_ENGULFING = "bullish_engulfing"  # 看涨吞没
    BEARISH_ENGULFING = "bearish_engulfing"  # 看跌吞没
    DOJI = "doji"                  # 十字星
    MORNING_STAR = "morning_star"  # 早晨之星 (看涨)
    EVENING_STAR = "evening_star"  # 黄昏之星 (看跌)

    # 整理形态
    DOUBLE_TOP = "double_top"      # 双顶 (看跌)
    DOUBLE_BOTTOM = "double_bottom"  # 双底 (看涨)
    HEAD_SHOULDERS = "head_shoulders"  # 头肩顶
    INV_HEAD_SHOULDERS = "inv_head_shoulders"  # 头肩底


class PatternSignal(str, Enum):
    """形态信号"""
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class Pattern(BaseModel):
    """识别到的形态"""
    pattern_type: PatternType
    signal: PatternSignal
    confidence: float  # 0-1
    start_index: int
    end_index: int
    description: str


class PatternRecognizer:
    """K线形态识别器"""

    def __init__(self):
        self.min_body_ratio = 0.1  # 最小实体比例

    def detect_all(self, klines: List[Kline]) -> List[Pattern]:
        """检测所有形态"""
        if len(klines) < 3:
            return []

        patterns = []

        # 单K线形态
        hammer = self.detect_hammer(klines)
        if hammer:
            patterns.append(hammer)

        doji = self.detect_doji(klines)
        if doji:
            patterns.append(doji)

        # 双K线形态
        engulfing = self.detect_engulfing(klines)
        if engulfing:
            patterns.append(engulfing)

        # 三K线形态
        star = self.detect_star_pattern(klines)
        if star:
            patterns.append(star)

        # 多K线形态 (需要更多数据)
        if len(klines) >= 20:
            double = self.detect_double_pattern(klines)
            if double:
                patterns.append(double)

        return patterns

    def detect_hammer(self, klines: List[Kline]) -> Optional[Pattern]:
        """检测锤子线/上吊线

        特征:
        - 小实体在K线顶部
        - 下影线长度 >= 实体 * 2
        - 几乎没有上影线
        """
        if len(klines) < 5:
            return None

        candle = klines[-1]
        body = abs(candle.close - candle.open)
        upper_shadow = candle.high - max(candle.open, candle.close)
        lower_shadow = min(candle.open, candle.close) - candle.low

        # 检测条件
        if body == 0:
            return None
        if lower_shadow < body * 2:
            return None
        if upper_shadow > body * 0.3:
            return None

        # 判断趋势方向 (用前4根K线判断)
        prev_closes = [k.close for k in klines[-5:-1]]
        is_downtrend = prev_closes[-1] < prev_closes[0]
        is_uptrend = prev_closes[-1] > prev_closes[0]

        if is_downtrend:
            return Pattern(
                pattern_type=PatternType.HAMMER,
                signal=PatternSignal.BULLISH,
                confidence=0.7,
                start_index=len(klines) - 1,
                end_index=len(klines) - 1,
                description="锤子线：下跌趋势中出现，可能反转上涨",
            )
        elif is_uptrend:
            return Pattern(
                pattern_type=PatternType.HANGING_MAN,
                signal=PatternSignal.BEARISH,
                confidence=0.6,
                start_index=len(klines) - 1,
                end_index=len(klines) - 1,
                description="上吊线：上涨趋势中出现，可能反转下跌",
            )

        return None

    def detect_doji(self, klines: List[Kline]) -> Optional[Pattern]:
        """检测十字星

        特征: 开盘价 ≈ 收盘价，实体极小
        """
        candle = klines[-1]
        body = abs(candle.close - candle.open)
        total_range = candle.high - candle.low

        if total_range == 0:
            return None

        body_ratio = body / total_range

        if body_ratio < 0.1:  # 实体占比小于10%
            return Pattern(
                pattern_type=PatternType.DOJI,
                signal=PatternSignal.NEUTRAL,
                confidence=0.6,
                start_index=len(klines) - 1,
                end_index=len(klines) - 1,
                description="十字星：市场犹豫，可能变盘",
            )

        return None

    def detect_engulfing(self, klines: List[Kline]) -> Optional[Pattern]:
        """检测吞没形态

        看涨吞没: 阴线后出现大阳线，完全覆盖前一根
        看跌吞没: 阳线后出现大阴线，完全覆盖前一根
        """
        if len(klines) < 2:
            return None

        prev = klines[-2]
        curr = klines[-1]

        prev_body = prev.close - prev.open
        curr_body = curr.close - curr.open

        # 看涨吞没: 前阴后阳，阳线完全覆盖阴线
        if prev_body < 0 and curr_body > 0:
            if curr.open <= prev.close and curr.close >= prev.open:
                return Pattern(
                    pattern_type=PatternType.BULLISH_ENGULFING,
                    signal=PatternSignal.BULLISH,
                    confidence=0.75,
                    start_index=len(klines) - 2,
                    end_index=len(klines) - 1,
                    description="看涨吞没：强烈看涨反转信号",
                )

        # 看跌吞没: 前阳后阴，阴线完全覆盖阳线
        if prev_body > 0 and curr_body < 0:
            if curr.open >= prev.close and curr.close <= prev.open:
                return Pattern(
                    pattern_type=PatternType.BEARISH_ENGULFING,
                    signal=PatternSignal.BEARISH,
                    confidence=0.75,
                    start_index=len(klines) - 2,
                    end_index=len(klines) - 1,
                    description="看跌吞没：强烈看跌反转信号",
                )

        return None

    def detect_star_pattern(self, klines: List[Kline]) -> Optional[Pattern]:
        """检测早晨之星/黄昏之星

        早晨之星: 大阴线 → 小实体(星线) → 大阳线
        黄昏之星: 大阳线 → 小实体(星线) → 大阴线
        """
        if len(klines) < 3:
            return None

        first = klines[-3]
        star = klines[-2]
        third = klines[-1]

        first_body = first.close - first.open
        star_body = abs(star.close - star.open)
        third_body = third.close - third.open

        avg_body = sum(abs(k.close - k.open) for k in klines[-10:-3]) / 7 if len(klines) >= 10 else star_body * 3

        # 早晨之星: 大阴线 + 小星线 + 大阳线
        if first_body < -avg_body * 0.5 and star_body < avg_body * 0.3 and third_body > avg_body * 0.5:
            if third.close > (first.open + first.close) / 2:  # 阳线收盘超过阴线中点
                return Pattern(
                    pattern_type=PatternType.MORNING_STAR,
                    signal=PatternSignal.BULLISH,
                    confidence=0.8,
                    start_index=len(klines) - 3,
                    end_index=len(klines) - 1,
                    description="早晨之星：强烈看涨反转信号",
                )

        # 黄昏之星: 大阳线 + 小星线 + 大阴线
        if first_body > avg_body * 0.5 and star_body < avg_body * 0.3 and third_body < -avg_body * 0.5:
            if third.close < (first.open + first.close) / 2:  # 阴线收盘低于阳线中点
                return Pattern(
                    pattern_type=PatternType.EVENING_STAR,
                    signal=PatternSignal.BEARISH,
                    confidence=0.8,
                    start_index=len(klines) - 3,
                    end_index=len(klines) - 1,
                    description="黄昏之星：强烈看跌反转信号",
                )

        return None

    def detect_double_pattern(self, klines: List[Kline]) -> Optional[Pattern]:
        """检测双顶/双底形态"""
        if len(klines) < 20:
            return None

        highs = [k.high for k in klines[-20:]]
        lows = [k.low for k in klines[-20:]]

        # 找局部高点
        local_highs = []
        for i in range(2, len(highs) - 2):
            if highs[i] > highs[i-1] and highs[i] > highs[i-2] and \
               highs[i] > highs[i+1] and highs[i] > highs[i+2]:
                local_highs.append((i, highs[i]))

        # 找局部低点
        local_lows = []
        for i in range(2, len(lows) - 2):
            if lows[i] < lows[i-1] and lows[i] < lows[i-2] and \
               lows[i] < lows[i+1] and lows[i] < lows[i+2]:
                local_lows.append((i, lows[i]))

        # 检测双顶
        if len(local_highs) >= 2:
            h1, h2 = local_highs[-2], local_highs[-1]
            if abs(h1[1] - h2[1]) / h1[1] < 0.02:  # 两个高点相差不超过2%
                return Pattern(
                    pattern_type=PatternType.DOUBLE_TOP,
                    signal=PatternSignal.BEARISH,
                    confidence=0.7,
                    start_index=len(klines) - 20 + h1[0],
                    end_index=len(klines) - 1,
                    description="双顶形态：可能向下突破",
                )

        # 检测双底
        if len(local_lows) >= 2:
            l1, l2 = local_lows[-2], local_lows[-1]
            if abs(l1[1] - l2[1]) / l1[1] < 0.02:  # 两个低点相差不超过2%
                return Pattern(
                    pattern_type=PatternType.DOUBLE_BOTTOM,
                    signal=PatternSignal.BULLISH,
                    confidence=0.7,
                    start_index=len(klines) - 20 + l1[0],
                    end_index=len(klines) - 1,
                    description="双底形态：可能向上突破",
                )

        return None
```

---

### 4.3 市场状态分类

**文件**: `src/ai_trader/strategies/market_classifier.py`

市场状态：
- 强趋势（ADX>25）→ 趋势跟随策略
- 震荡（ADX<20）→ 区间交易策略
- 突破（放量突破）→ 追单策略
- 横盘 → 观望

```python
"""市场状态分类器"""

from typing import List, Tuple
from enum import Enum
from pydantic import BaseModel
import numpy as np

from ..models.market import MarketData, Kline


class MarketState(str, Enum):
    """市场状态"""
    STRONG_TREND = "strong_trend"    # 强趋势
    WEAK_TREND = "weak_trend"        # 弱趋势
    RANGE_BOUND = "range_bound"      # 震荡区间
    BREAKOUT = "breakout"            # 突破
    SIDEWAYS = "sideways"            # 横盘


class TrendDirection(str, Enum):
    """趋势方向"""
    UP = "up"
    DOWN = "down"
    NONE = "none"


class MarketClassification(BaseModel):
    """市场分类结果"""
    state: MarketState
    direction: TrendDirection
    adx: float
    volatility: float  # ATR百分比
    volume_ratio: float  # 当前成交量/平均成交量
    confidence: float


class MarketClassifier:
    """市场状态分类器

    使用ADX判断趋势强度，结合成交量和波动率进行分类
    """

    def __init__(self):
        self.adx_period = 14
        self.atr_period = 14

    def classify(self, market_data: MarketData) -> MarketClassification:
        """分类市场状态"""
        klines = market_data.klines

        if len(klines) < 30:
            return MarketClassification(
                state=MarketState.SIDEWAYS,
                direction=TrendDirection.NONE,
                adx=0,
                volatility=0,
                volume_ratio=1.0,
                confidence=0.3,
            )

        # 计算ADX
        adx, plus_di, minus_di = self.calculate_adx(klines)

        # 计算波动率 (ATR / 价格)
        atr = self.calculate_atr(klines)
        volatility = (atr / klines[-1].close) * 100

        # 计算成交量比率
        volume_ratio = self._calculate_volume_ratio(klines)

        # 判断趋势方向
        direction = self._determine_direction(plus_di, minus_di, klines)

        # 分类市场状态
        state, confidence = self._classify_state(
            adx, volatility, volume_ratio, klines
        )

        return MarketClassification(
            state=state,
            direction=direction,
            adx=adx,
            volatility=volatility,
            volume_ratio=volume_ratio,
            confidence=confidence,
        )

    def calculate_adx(self, klines: List[Kline], period: int = 14) -> Tuple[float, float, float]:
        """计算ADX指标

        Returns:
            (ADX, +DI, -DI)
        """
        if len(klines) < period * 2:
            return 0.0, 0.0, 0.0

        highs = np.array([k.high for k in klines])
        lows = np.array([k.low for k in klines])
        closes = np.array([k.close for k in klines])

        # 计算True Range
        tr = np.maximum(
            highs[1:] - lows[1:],
            np.maximum(
                np.abs(highs[1:] - closes[:-1]),
                np.abs(lows[1:] - closes[:-1])
            )
        )

        # 计算+DM和-DM
        plus_dm = np.where(
            (highs[1:] - highs[:-1]) > (lows[:-1] - lows[1:]),
            np.maximum(highs[1:] - highs[:-1], 0),
            0
        )
        minus_dm = np.where(
            (lows[:-1] - lows[1:]) > (highs[1:] - highs[:-1]),
            np.maximum(lows[:-1] - lows[1:], 0),
            0
        )

        # 平滑计算
        atr = self._ema(tr, period)
        plus_di = 100 * self._ema(plus_dm, period) / atr
        minus_di = 100 * self._ema(minus_dm, period) / atr

        # 计算DX和ADX
        dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)
        adx = self._ema(dx, period)

        return float(adx[-1]), float(plus_di[-1]), float(minus_di[-1])

    def calculate_atr(self, klines: List[Kline], period: int = 14) -> float:
        """计算ATR"""
        if len(klines) < period:
            return 0.0

        highs = np.array([k.high for k in klines])
        lows = np.array([k.low for k in klines])
        closes = np.array([k.close for k in klines])

        tr = np.maximum(
            highs[1:] - lows[1:],
            np.maximum(
                np.abs(highs[1:] - closes[:-1]),
                np.abs(lows[1:] - closes[:-1])
            )
        )

        atr = self._ema(tr, period)
        return float(atr[-1])

    def _ema(self, data: np.ndarray, period: int) -> np.ndarray:
        """计算EMA"""
        alpha = 2 / (period + 1)
        result = np.zeros_like(data)
        result[0] = data[0]
        for i in range(1, len(data)):
            result[i] = alpha * data[i] + (1 - alpha) * result[i - 1]
        return result

    def _calculate_volume_ratio(self, klines: List[Kline]) -> float:
        """计算成交量比率"""
        if len(klines) < 20:
            return 1.0

        current_volume = klines[-1].volume
        avg_volume = np.mean([k.volume for k in klines[-20:-1]])

        if avg_volume == 0:
            return 1.0

        return current_volume / avg_volume

    def _determine_direction(
        self, plus_di: float, minus_di: float, klines: List[Kline]
    ) -> TrendDirection:
        """判断趋势方向"""
        # 使用DI判断
        if plus_di > minus_di + 5:
            return TrendDirection.UP
        elif minus_di > plus_di + 5:
            return TrendDirection.DOWN

        # 使用价格判断
        if len(klines) >= 10:
            recent_closes = [k.close for k in klines[-10:]]
            if recent_closes[-1] > recent_closes[0] * 1.02:
                return TrendDirection.UP
            elif recent_closes[-1] < recent_closes[0] * 0.98:
                return TrendDirection.DOWN

        return TrendDirection.NONE

    def _classify_state(
        self,
        adx: float,
        volatility: float,
        volume_ratio: float,
        klines: List[Kline],
    ) -> Tuple[MarketState, float]:
        """分类市场状态"""
        confidence = 0.5

        # 突破检测: 高成交量 + 价格突破
        if volume_ratio > 2.0 and self._is_breakout(klines):
            return MarketState.BREAKOUT, 0.8

        # 强趋势: ADX > 25
        if adx > 25:
            confidence = min(0.9, 0.5 + (adx - 25) / 50)
            return MarketState.STRONG_TREND, confidence

        # 弱趋势: 20 < ADX <= 25
        if 20 < adx <= 25:
            return MarketState.WEAK_TREND, 0.6

        # 震荡: ADX < 20 且有波动
        if adx < 20 and volatility > 1.0:
            return MarketState.RANGE_BOUND, 0.7

        # 横盘: ADX极低且波动小
        return MarketState.SIDEWAYS, 0.6

    def _is_breakout(self, klines: List[Kline]) -> bool:
        """检测是否突破"""
        if len(klines) < 20:
            return False

        current_close = klines[-1].close
        recent_highs = [k.high for k in klines[-20:-1]]
        recent_lows = [k.low for k in klines[-20:-1]]

        # 向上突破
        if current_close > max(recent_highs):
            return True

        # 向下突破
        if current_close < min(recent_lows):
            return True

        return False
```

---

### 4.4 策略库系统

**文件**: `src/ai_trader/strategies/strategy_base.py`

```python
"""交易策略基类与具体策略实现"""

from abc import ABC, abstractmethod
from typing import List, Optional
from enum import Enum
from pydantic import BaseModel

from ..models.market import MarketData
from .market_classifier import MarketState


class SignalAction(str, Enum):
    """交易信号动作"""
    LONG = "long"
    SHORT = "short"
    HOLD = "hold"
    CLOSE_LONG = "close_long"
    CLOSE_SHORT = "close_short"


class Signal(BaseModel):
    """交易信号"""
    action: SignalAction
    confidence: float  # 0-1
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    reason: str = ""


class TradingStrategy(ABC):
    """交易策略抽象基类"""

    name: str = "base_strategy"
    suitable_market_states: List[MarketState] = []

    @abstractmethod
    def generate_signal(self, market_data: MarketData) -> Signal:
        """生成交易信号"""
        pass

    def is_suitable(self, state: MarketState) -> bool:
        """判断策略是否适合当前市场状态"""
        return state in self.suitable_market_states


class TrendFollowingStrategy(TradingStrategy):
    """趋势跟随策略

    条件：
    - MA金叉/死叉
    - MACD确认
    - 适用于强趋势市场
    """

    name = "trend_following"
    suitable_market_states = [MarketState.STRONG_TREND, MarketState.WEAK_TREND]

    def generate_signal(self, market_data: MarketData) -> Signal:
        ind = market_data.indicators
        price = market_data.current_price

        # MA金叉: MA7 > MA25 > MA99
        ma_bullish = ind.ma7 > ind.ma25 > ind.ma99
        ma_bearish = ind.ma7 < ind.ma25 < ind.ma99

        # MACD确认
        macd_bullish = ind.macd > ind.macd_signal and ind.macd_histogram > 0
        macd_bearish = ind.macd < ind.macd_signal and ind.macd_histogram < 0

        # 做多信号
        if ma_bullish and macd_bullish:
            stop_loss = price - ind.atr * 2
            take_profit = price + ind.atr * 4
            return Signal(
                action=SignalAction.LONG,
                confidence=0.75,
                entry_price=price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                reason="MA多头排列 + MACD金叉确认",
            )

        # 做空信号
        if ma_bearish and macd_bearish:
            stop_loss = price + ind.atr * 2
            take_profit = price - ind.atr * 4
            return Signal(
                action=SignalAction.SHORT,
                confidence=0.75,
                entry_price=price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                reason="MA空头排列 + MACD死叉确认",
            )

        return Signal(action=SignalAction.HOLD, confidence=0.5, reason="趋势不明确")


class MeanReversionStrategy(TradingStrategy):
    """均值回归策略

    条件：
    - RSI超买/超卖
    - 价格触及布林带边界
    - 适用于震荡市场
    """

    name = "mean_reversion"
    suitable_market_states = [MarketState.RANGE_BOUND]

    def generate_signal(self, market_data: MarketData) -> Signal:
        ind = market_data.indicators
        price = market_data.current_price

        # RSI超卖 + 布林带下轨 = 做多
        if ind.rsi < 30 and price <= ind.boll_lower:
            stop_loss = ind.boll_lower - ind.atr
            take_profit = ind.boll_middle
            return Signal(
                action=SignalAction.LONG,
                confidence=0.7,
                entry_price=price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                reason=f"RSI超卖({ind.rsi:.1f}) + 触及布林带下轨",
            )

        # RSI超买 + 布林带上轨 = 做空
        if ind.rsi > 70 and price >= ind.boll_upper:
            stop_loss = ind.boll_upper + ind.atr
            take_profit = ind.boll_middle
            return Signal(
                action=SignalAction.SHORT,
                confidence=0.7,
                entry_price=price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                reason=f"RSI超买({ind.rsi:.1f}) + 触及布林带上轨",
            )

        return Signal(action=SignalAction.HOLD, confidence=0.5, reason="未达到均值回归条件")


class BreakoutStrategy(TradingStrategy):
    """突破策略

    条件：
    - 价格突破前高/前低
    - 成交量放大确认
    - 适用于突破行情
    """

    name = "breakout"
    suitable_market_states = [MarketState.BREAKOUT]

    def __init__(self):
        self.lookback_period = 20

    def generate_signal(self, market_data: MarketData) -> Signal:
        klines = market_data.klines
        price = market_data.current_price
        ind = market_data.indicators

        if len(klines) < self.lookback_period:
            return Signal(action=SignalAction.HOLD, confidence=0.3, reason="数据不足")

        # 计算前期高低点
        recent = klines[-self.lookback_period:-1]
        prev_high = max(k.high for k in recent)
        prev_low = min(k.low for k in recent)

        # 计算成交量比率
        current_vol = klines[-1].volume
        avg_vol = sum(k.volume for k in recent) / len(recent)
        vol_ratio = current_vol / avg_vol if avg_vol > 0 else 1.0

        # 向上突破: 价格突破前高 + 放量
        if price > prev_high and vol_ratio > 1.5:
            stop_loss = prev_high - ind.atr
            take_profit = price + (price - prev_low)  # 目标 = 突破幅度
            return Signal(
                action=SignalAction.LONG,
                confidence=0.8,
                entry_price=price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                reason=f"向上突破前高({prev_high:.2f})，成交量放大{vol_ratio:.1f}倍",
            )

        # 向下突破: 价格突破前低 + 放量
        if price < prev_low and vol_ratio > 1.5:
            stop_loss = prev_low + ind.atr
            take_profit = price - (prev_high - price)
            return Signal(
                action=SignalAction.SHORT,
                confidence=0.8,
                entry_price=price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                reason=f"向下突破前低({prev_low:.2f})，成交量放大{vol_ratio:.1f}倍",
            )

        return Signal(action=SignalAction.HOLD, confidence=0.5, reason="未检测到有效突破")


# 策略注册表
STRATEGY_REGISTRY = {
    "trend_following": TrendFollowingStrategy,
    "mean_reversion": MeanReversionStrategy,
    "breakout": BreakoutStrategy,
}


def get_strategy(name: str) -> TradingStrategy:
    """获取策略实例"""
    strategy_class = STRATEGY_REGISTRY.get(name)
    if strategy_class is None:
        raise ValueError(f"未知策略: {name}")
    return strategy_class()
```

---

### 4.5 策略选择器

**文件**: `src/ai_trader/strategies/strategy_selector.py`

```python
"""策略选择器 - 根据市场状态选择和综合多策略信号"""

from typing import List, Dict, Optional
from pydantic import BaseModel

from .strategy_base import (
    TradingStrategy, Signal, SignalAction,
    STRATEGY_REGISTRY, get_strategy
)
from .market_classifier import MarketState, MarketClassification
from ..config import config


class StrategyWeight(BaseModel):
    """策略权重配置"""
    strategy_name: str
    weight: float


class AggregatedSignal(BaseModel):
    """聚合后的信号"""
    action: SignalAction
    confidence: float
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    source_strategies: List[str]
    reasoning: str

    def is_valid_for_trading(self) -> bool:
        """检查信号是否包含有效的交易参数"""
        if self.action == SignalAction.HOLD:
            return True  # HOLD不需要价格参数
        return (
            self.entry_price is not None and self.entry_price > 0 and
            self.stop_loss is not None and self.stop_loss > 0
        )


class StrategySelector:
    """策略选择器

    功能：
    1. 根据市场状态选择适合的策略
    2. 综合多策略信号（投票 + 加权）
    """

    STRATEGY_WEIGHTS = {
        "trend_following": 1.0,
        "mean_reversion": 0.8,
        "breakout": 0.9,
    }

    def __init__(self):
        self.enabled_strategies = config.get_enabled_strategies()
        self.strategies: Dict[str, TradingStrategy] = {}

        for name in self.enabled_strategies:
            if name in STRATEGY_REGISTRY:
                self.strategies[name] = get_strategy(name)

    def select_strategies(
        self, market_state: MarketState
    ) -> List[TradingStrategy]:
        """根据市场状态选择适合的策略"""
        suitable = []
        for name, strategy in self.strategies.items():
            if strategy.is_suitable(market_state):
                suitable.append(strategy)

        if not suitable:
            return list(self.strategies.values())

        return suitable

    def aggregate_signals(
        self, signals: Dict[str, Signal], market_class: MarketClassification
    ) -> AggregatedSignal:
        """综合多策略信号"""
        if not signals:
            return self._hold_signal("无有效信号")

        votes: Dict[SignalAction, float] = {}
        details: Dict[SignalAction, List[Signal]] = {}

        for strategy_name, signal in signals.items():
            action = signal.action
            weight = self.STRATEGY_WEIGHTS.get(strategy_name, 1.0)
            score = weight * signal.confidence

            if action not in votes:
                votes[action] = 0
                details[action] = []

            votes[action] += score
            details[action].append(signal)

        best_action = max(votes.keys(), key=lambda a: votes[a])
        best_score = votes[best_action]

        # 检查冲突
        conflicting_actions = [SignalAction.LONG, SignalAction.SHORT]
        if best_action in conflicting_actions:
            opposite = SignalAction.SHORT if best_action == SignalAction.LONG else SignalAction.LONG
            if opposite in votes:
                if votes[opposite] > best_score * 0.7:
                    return self._hold_signal(
                        f"信号冲突: {best_action.value}({best_score:.2f}) vs {opposite.value}({votes[opposite]:.2f})"
                    )

        if best_action == SignalAction.HOLD:
            return self._hold_signal("多策略一致观望")

        same_direction_signals = details[best_action]
        source_strategies = list(signals.keys())

        entry_prices = []
        stop_losses = []
        take_profits = []
        reasons = []

        for sig in same_direction_signals:
            if sig.entry_price:
                entry_prices.append(sig.entry_price)
            if sig.stop_loss:
                stop_losses.append(sig.stop_loss)
            if sig.take_profit:
                take_profits.append(sig.take_profit)
            if sig.reason:
                reasons.append(sig.reason)

        avg_entry = sum(entry_prices) / len(entry_prices) if entry_prices else None
        conservative_sl = (
            min(stop_losses) if best_action == SignalAction.LONG else max(stop_losses)
        ) if stop_losses else None
        avg_tp = sum(take_profits) / len(take_profits) if take_profits else None

        final_confidence = min(0.95, best_score / len(signals))

        return AggregatedSignal(
            action=best_action,
            confidence=final_confidence,
            entry_price=avg_entry,
            stop_loss=conservative_sl,
            take_profit=avg_tp,
            source_strategies=[
                name for name, sig in signals.items()
                if sig.action == best_action
            ],
            reasoning=" | ".join(reasons[:3]),
        )

    def _hold_signal(self, reason: str) -> AggregatedSignal:
        """返回观望信号"""
        return AggregatedSignal(
            action=SignalAction.HOLD,
            confidence=0.5,
            entry_price=None,
            stop_loss=None,
            take_profit=None,
            source_strategies=[],
            reasoning=reason,
        )
```

---

### 4.6 混合决策系统

**文件**: `src/ai_trader/ai/decision.py`（重构）

详见 [交易分析流程图 - 混合决策详细流程](./ai_quant_plan_flow.md#混合决策详细流程)

混合逻辑：
- **双重确认**: 量化和LLM一致 → 提高置信度
- **量化优先**: 强趋势市场 → 信任量化
- **LLM优先**: 震荡市/复杂市况 → LLM判断
- **保守策略**: 信号冲突 → 观望

---

### 4.7 回测框架

**文件**: `src/ai_trader/backtest/engine.py`

回测引擎支持：
1. 历史K线数据回测
2. 策略信号生成
3. 模拟交易执行
4. 绩效统计

**输出指标**:
- 总交易次数、胜率
- 总盈亏、盈亏比
- 最大回撤
- 夏普比率

---

## 验证方法

1. **单元测试**: 每个策略独立测试
2. **历史回测**: 1年历史数据验证
3. **对比测试**: 纯LLM vs 纯量化 vs 混合模式
4. **Testnet实盘**: 模拟环境验证

---

## 风险控制

- 过拟合 → out-of-sample验证
- 信号冲突 → 清晰的冲突解决规则
- 延迟累积 → 性能监控

---

## 相关文档

- [主文档](./ai_quant_system_plan.md)
- [交易分析流程图](./ai_quant_plan_flow.md)
- [Phase 3: 专业交易员流程](./ai_quant_plan_phase3_trading.md)
- [Phase 5: 情绪分析集成](./ai_quant_plan_phase5_sentiment.md)
