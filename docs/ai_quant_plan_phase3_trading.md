# AI量化交易系统 - Phase 3: 专业交易员流程

> 本文档是 [AI量化交易系统升级规划](./ai_quant_system_plan.md) 的子文档

**预计时间**: 11天

---

## 目标

研究专业交易员逻辑，结构化为AI可执行模块。

---

## 关键任务

### 3.1 交易员流程调研

**输出**: `docs/professional_trading_research.md`

研究方向：
1. **多时间框架分析**: 4H看趋势，15m找入场点
2. **仓位管理金字塔**: 初始10% → 盈利加仓至30% → 最大50%
3. **止损纪律**: 硬止损（技术位）+ 移动止损（盈利后移到成本价）
4. **风险回报比**: 至少1:2

---

### 3.2 多时间框架分析

**文件**: `src/ai_trader/data/multi_timeframe.py`

```python
"""多时间框架数据分析"""

from typing import List, Optional, Dict
from enum import Enum
from pydantic import BaseModel

from ..models.market import MarketData, Kline, Indicators
from ..exchange.base import BaseExchange
from .indicators import calculate_indicators


class Trend(str, Enum):
    """趋势方向"""
    UP = "up"
    DOWN = "down"
    SIDEWAYS = "sideways"


class TimeframeAnalysis(BaseModel):
    """单时间框架分析结果"""
    interval: str
    trend: Trend
    trend_strength: float  # 0-100
    support: float
    resistance: float
    ma_position: str  # above_ma / below_ma / crossing


class MultiTimeframeData(BaseModel):
    """多时间框架聚合数据"""
    symbol: str
    current_price: float

    # 各时间框架数据
    tf_15m: MarketData
    tf_1h: MarketData
    tf_4h: MarketData
    tf_1d: MarketData

    # 各时间框架分析结果
    analysis_15m: Optional[TimeframeAnalysis] = None
    analysis_1h: Optional[TimeframeAnalysis] = None
    analysis_4h: Optional[TimeframeAnalysis] = None
    analysis_1d: Optional[TimeframeAnalysis] = None

    @property
    def trend_alignment(self) -> bool:
        """多周期趋势是否一致"""
        trends = [
            self.analysis_15m.trend if self.analysis_15m else None,
            self.analysis_1h.trend if self.analysis_1h else None,
            self.analysis_4h.trend if self.analysis_4h else None,
        ]
        valid_trends = [t for t in trends if t is not None]
        if len(valid_trends) < 2:
            return False
        return len(set(valid_trends)) == 1

    @property
    def dominant_trend(self) -> Trend:
        """获取主导趋势（以大周期为准）"""
        # 权重: 1D > 4H > 1H > 15m
        if self.analysis_1d and self.analysis_1d.trend != Trend.SIDEWAYS:
            return self.analysis_1d.trend
        if self.analysis_4h and self.analysis_4h.trend != Trend.SIDEWAYS:
            return self.analysis_4h.trend
        if self.analysis_1h:
            return self.analysis_1h.trend
        return Trend.SIDEWAYS

    @property
    def trend_score(self) -> float:
        """趋势一致性评分 (0-100)"""
        weights = {"1d": 0.4, "4h": 0.3, "1h": 0.2, "15m": 0.1}
        analyses = {
            "1d": self.analysis_1d,
            "4h": self.analysis_4h,
            "1h": self.analysis_1h,
            "15m": self.analysis_15m,
        }

        score = 0.0
        dominant = self.dominant_trend

        for tf, analysis in analyses.items():
            if analysis and analysis.trend == dominant:
                score += weights[tf] * analysis.trend_strength

        return min(100, score)


class MultiTimeframeManager:
    """多时间框架数据管理器"""

    INTERVALS = ["15m", "1h", "4h", "1d"]

    def __init__(self, exchange: BaseExchange):
        self._exchange = exchange

    async def fetch_all(self, symbol: str, limit: int = 100) -> MultiTimeframeData:
        """获取所有时间框架数据"""
        import asyncio

        # 并行获取所有周期K线
        tasks = [
            self._fetch_market_data(symbol, interval, limit)
            for interval in self.INTERVALS
        ]
        results = await asyncio.gather(*tasks)

        tf_15m, tf_1h, tf_4h, tf_1d = results

        # 获取当前价格
        ticker = await self._exchange.get_ticker(symbol)

        mtf = MultiTimeframeData(
            symbol=symbol,
            current_price=ticker.last_price,
            tf_15m=tf_15m,
            tf_1h=tf_1h,
            tf_4h=tf_4h,
            tf_1d=tf_1d,
        )

        # 分析各时间框架
        mtf.analysis_15m = self._analyze_timeframe(tf_15m)
        mtf.analysis_1h = self._analyze_timeframe(tf_1h)
        mtf.analysis_4h = self._analyze_timeframe(tf_4h)
        mtf.analysis_1d = self._analyze_timeframe(tf_1d)

        return mtf

    async def _fetch_market_data(
        self, symbol: str, interval: str, limit: int
    ) -> MarketData:
        """获取单个时间框架的市场数据"""
        klines = await self._exchange.get_klines(symbol, interval, limit)
        ticker = await self._exchange.get_ticker(symbol)
        indicators = calculate_indicators(klines)

        return MarketData(
            symbol=symbol,
            current_price=ticker.last_price,
            klines=klines,
            interval=interval,
            indicators=indicators,
            high_24h=ticker.high_24h,
            low_24h=ticker.low_24h,
            change_24h=ticker.change_24h,
            volume_24h=ticker.volume_24h,
        )

    def _analyze_timeframe(self, market_data: MarketData) -> TimeframeAnalysis:
        """分析单个时间框架"""
        klines = market_data.klines
        indicators = market_data.indicators

        # 判断趋势
        trend = self._determine_trend(klines, indicators)

        # 计算趋势强度 (基于ADX，需要在indicators中添加)
        trend_strength = min(100, abs(indicators.macd_histogram) * 10)

        # 计算支撑阻力
        recent_lows = [k.low for k in klines[-20:]]
        recent_highs = [k.high for k in klines[-20:]]
        support = min(recent_lows)
        resistance = max(recent_highs)

        # 判断价格与MA关系
        current_price = klines[-1].close
        if current_price > indicators.ma25:
            ma_position = "above_ma"
        elif current_price < indicators.ma25:
            ma_position = "below_ma"
        else:
            ma_position = "crossing"

        return TimeframeAnalysis(
            interval=market_data.interval,
            trend=trend,
            trend_strength=trend_strength,
            support=support,
            resistance=resistance,
            ma_position=ma_position,
        )

    def _determine_trend(self, klines: List[Kline], indicators: Indicators) -> Trend:
        """判断趋势方向"""
        # MA排列判断
        ma_bullish = indicators.ma7 > indicators.ma25 > indicators.ma99
        ma_bearish = indicators.ma7 < indicators.ma25 < indicators.ma99

        # MACD判断
        macd_bullish = indicators.macd > indicators.macd_signal
        macd_bearish = indicators.macd < indicators.macd_signal

        # 综合判断
        if ma_bullish and macd_bullish:
            return Trend.UP
        elif ma_bearish and macd_bearish:
            return Trend.DOWN
        else:
            return Trend.SIDEWAYS
```

---

### 3.3 仓位管理模块

**文件**: `src/ai_trader/risk/position_manager.py`

功能：
- `calculate_initial_position()` - 初始建仓量
- `should_add_position()` - 加仓判断
- `calculate_trailing_stop()` - 移动止损

```python
"""仓位管理模块"""

from typing import Optional, Tuple
from enum import Enum
from pydantic import BaseModel
from decimal import Decimal, ROUND_DOWN

from ..exchange.base import Position, AccountInfo
from ..config import config
from ..utils.logger import logger


class PositionAction(str, Enum):
    """仓位操作"""
    HOLD = "hold"
    ADD = "add"
    REDUCE = "reduce"
    CLOSE = "close"


class StopLossType(str, Enum):
    """止损类型"""
    HARD = "hard"          # 固定止损
    TRAILING = "trailing"  # 移动止损
    BREAKEVEN = "breakeven"  # 保本止损


class PositionSizing(BaseModel):
    """仓位计算结果"""
    size: float
    leverage: int
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_amount: float  # 风险金额
    risk_percent: float  # 风险比例


class PositionManager:
    """仓位管理器

    实现专业交易员的仓位管理策略:
    1. 固定比例风控: 单笔风险不超过账户的1-2%
    2. 金字塔加仓: 盈利后逐步加仓
    3. 移动止损: 盈利后移动止损保护利润
    """

    # 仓位配置
    INITIAL_RISK_PERCENT = 0.01  # 初始风险1%
    MAX_RISK_PERCENT = 0.02      # 最大风险2%
    MAX_POSITION_PERCENT = 0.50  # 最大仓位50%

    # 金字塔加仓配置
    PYRAMID_LEVELS = [
        {"profit_r": 1.0, "add_percent": 0.10},  # 盈利1R后加仓10%
        {"profit_r": 2.0, "add_percent": 0.10},  # 盈利2R后再加10%
        {"profit_r": 3.0, "add_percent": 0.10},  # 盈利3R后再加10%
    ]

    # 移动止损配置
    TRAILING_STOP_LEVELS = [
        {"profit_r": 1.0, "stop_at_r": 0.0},   # 盈利1R，止损移到成本价
        {"profit_r": 2.0, "stop_at_r": 1.0},   # 盈利2R，止损移到+1R
        {"profit_r": 3.0, "stop_at_r": 2.0},   # 盈利3R，止损移到+2R
    ]

    def __init__(self):
        self.current_risk_percent = self.INITIAL_RISK_PERCENT

    def calculate_initial_position(
        self,
        account: AccountInfo,
        entry_price: float,
        stop_loss_price: float,
        leverage: int = 5,
    ) -> PositionSizing:
        """计算初始建仓量

        公式: 仓位 = (账户余额 × 风险比例) / (入场价 - 止损价)

        Args:
            account: 账户信息
            entry_price: 计划入场价
            stop_loss_price: 止损价
            leverage: 杠杆倍数

        Returns:
            PositionSizing: 仓位计算结果
        """
        # 计算风险金额
        risk_amount = account.available_balance * self.current_risk_percent

        # 计算每单位风险
        price_risk = abs(entry_price - stop_loss_price)
        if price_risk == 0:
            logger.warning("止损价等于入场价，无法计算仓位")
            return self._empty_sizing(entry_price)

        # 计算仓位大小
        position_size = risk_amount / price_risk

        # 检查是否超过最大仓位限制
        max_size = (account.available_balance * self.MAX_POSITION_PERCENT * leverage) / entry_price
        position_size = min(position_size, max_size)

        # 计算止盈价 (默认2R)
        risk_r = price_risk
        if entry_price > stop_loss_price:  # 做多
            take_profit = entry_price + (risk_r * 2)
        else:  # 做空
            take_profit = entry_price - (risk_r * 2)

        # 精度处理
        position_size = float(Decimal(str(position_size)).quantize(
            Decimal("0.001"), rounding=ROUND_DOWN
        ))

        return PositionSizing(
            size=position_size,
            leverage=leverage,
            entry_price=entry_price,
            stop_loss=stop_loss_price,
            take_profit=take_profit,
            risk_amount=risk_amount,
            risk_percent=self.current_risk_percent * 100,
        )

    def should_add_position(
        self,
        position: Position,
        current_price: float,
        original_stop_loss: float,
    ) -> Tuple[bool, float]:
        """判断是否应该加仓

        Args:
            position: 当前持仓
            current_price: 当前价格
            original_stop_loss: 原始止损价（用于计算初始风险R）

        Returns:
            (是否加仓, 加仓比例)
        """
        if position.size == 0:
            return False, 0.0

        entry_price = position.entry_price

        # 使用与calculate_initial_position一致的风险定义
        # 初始风险R = |入场价 - 止损价|
        initial_risk = abs(entry_price - original_stop_loss)
        if initial_risk == 0:
            logger.warning("初始风险为0，无法判断加仓条件")
            return False, 0.0

        # 计算当前盈利R值
        if position.side == "long":
            price_diff = current_price - entry_price
        else:
            price_diff = entry_price - current_price

        profit_r = price_diff / initial_risk

        # 检查是否达到加仓条件
        for level in self.PYRAMID_LEVELS:
            if profit_r >= level["profit_r"]:
                # 检查是否已经在该级别加过仓 (需要外部记录)
                return True, level["add_percent"]

        return False, 0.0

    def calculate_trailing_stop(
        self,
        position: Position,
        current_price: float,
        original_stop: float,
    ) -> float:
        """计算移动止损价

        Args:
            position: 当前持仓
            current_price: 当前价格
            original_stop: 原始止损价

        Returns:
            新的止损价
        """
        entry_price = position.entry_price
        is_long = position.side == "long"

        # 计算初始风险
        initial_risk = abs(entry_price - original_stop)
        if initial_risk == 0:
            return original_stop

        # 计算当前盈利R值
        if is_long:
            profit_r = (current_price - entry_price) / initial_risk
        else:
            profit_r = (entry_price - current_price) / initial_risk

        # 根据盈利情况移动止损
        new_stop = original_stop
        for level in self.TRAILING_STOP_LEVELS:
            if profit_r >= level["profit_r"]:
                if is_long:
                    new_stop = entry_price + (initial_risk * level["stop_at_r"])
                else:
                    new_stop = entry_price - (initial_risk * level["stop_at_r"])

        # 止损只能往有利方向移动
        if is_long:
            return max(new_stop, original_stop)
        else:
            return min(new_stop, original_stop) if new_stop > 0 else original_stop

    def check_daily_loss_limit(
        self,
        account: AccountInfo,
        daily_pnl: float,
        max_daily_loss_percent: float = 0.03,
    ) -> bool:
        """检查是否超过每日最大亏损限制

        Args:
            account: 账户信息
            daily_pnl: 当日盈亏
            max_daily_loss_percent: 最大每日亏损比例 (默认3%)

        Returns:
            True=已超限，应停止交易
        """
        max_loss = account.total_equity * max_daily_loss_percent
        if daily_pnl < -max_loss:
            logger.warning(f"触发每日最大亏损限制: {daily_pnl:.2f} < -{max_loss:.2f}")
            return True
        return False

    def calculate_risk_reward_ratio(
        self,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
    ) -> float:
        """计算风险回报比

        Args:
            entry_price: 入场价
            stop_loss: 止损价
            take_profit: 止盈价

        Returns:
            风险回报比 (如 2.0 表示 1:2)
        """
        risk = abs(entry_price - stop_loss)
        reward = abs(take_profit - entry_price)
        if risk == 0:
            return 0.0
        return reward / risk

    def _empty_sizing(self, price: float) -> PositionSizing:
        """返回空仓位"""
        return PositionSizing(
            size=0.0,
            leverage=1,
            entry_price=price,
            stop_loss=price,
            take_profit=price,
            risk_amount=0.0,
            risk_percent=0.0,
        )
```

---

### 3.4 规则引擎（可选）

**文件**: `src/ai_trader/rules/rule_engine.py`

```python
class TradingRule(ABC):
    @abstractmethod
    def evaluate(self, context: TradingContext) -> RuleResult:
        pass

class MaxDailyLossRule(TradingRule):
    """每日最大亏损规则"""
    ...
```

---

### 3.5 交易日志系统

**文件**: `src/ai_trader/analytics/trade_journal.py`

记录每笔交易的完整上下文：
- 市场状态
- 决策理由
- 执行结果
- PnL

---

### 3.6 AI Prompt增强

**文件**: `src/ai_trader/prompts/technical.py`, `trading.py`

在提示词中加入：
- 多时间框架分析要求
- 仓位管理规则
- 交易纪律约束

---

## 验证方法

1. 历史回测验证新架构性能
2. Testnet运行2周观察效果

---

## 风险控制

- 过度优化 → 使用out-of-sample数据验证
- 复杂度增加 → 模块化设计，逐步迭代

---

## 相关文档

- [主文档](./ai_quant_system_plan.md)
- [Phase 2: 模拟交易环境](./ai_quant_plan_phase2_testnet.md)
- [Phase 4: 量化策略模型集成](./ai_quant_plan_phase4_quant.md)
