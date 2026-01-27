# AI量化交易系统 - Phase 1: CCXT集成

> 本文档是 [AI量化交易系统升级规划](./ai_quant_system_plan.md) 的子文档

**预计时间**: 7天

---

## 目标

引入CCXT统一交易所接口，替换自定义WEEX实现，为多交易所支持打基础。

---

## 关键任务

### 1.1 设计交易所抽象层

**文件**: `src/ai_trader/exchange/base.py`

定义`BaseExchange`抽象基类，规范接口：
- `get_account()` - 账户信息
- `get_klines()` - K线数据
- `get_ticker()` - 实时价格
- `get_positions()` - 持仓查询
- `set_leverage()` - 杠杆设置
- `create_order()` - 下单

返回值统一为内部模型（`Kline`, `Position`, `Order`）。

```python
"""交易所抽象基类"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from enum import Enum
from pydantic import BaseModel

from ..models.market import Kline
from ..models.order import Order


class OrderSide(str, Enum):
    OPEN_LONG = "open_long"
    OPEN_SHORT = "open_short"
    CLOSE_LONG = "close_long"
    CLOSE_SHORT = "close_short"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class Position(BaseModel):
    """持仓模型"""
    symbol: str
    side: str  # long / short
    size: float
    entry_price: float
    mark_price: float
    unrealized_pnl: float
    leverage: int
    margin_mode: str  # cross / isolated
    liquidation_price: Optional[float] = None


class AccountInfo(BaseModel):
    """账户信息模型"""
    total_equity: float
    available_balance: float
    margin_used: float
    unrealized_pnl: float


class Ticker(BaseModel):
    """行情快照"""
    symbol: str
    last_price: float
    bid_price: float
    ask_price: float
    high_24h: float
    low_24h: float
    volume_24h: float
    change_24h: float


class BaseExchange(ABC):
    """交易所抽象基类，所有交易所实现必须继承此类"""

    @abstractmethod
    async def get_account(self) -> AccountInfo:
        """获取账户信息"""
        pass

    @abstractmethod
    async def get_klines(
        self,
        symbol: str,
        interval: str = "15m",
        limit: int = 100
    ) -> List[Kline]:
        """获取K线数据"""
        pass

    @abstractmethod
    async def get_ticker(self, symbol: str) -> Ticker:
        """获取实时行情"""
        pass

    @abstractmethod
    async def get_positions(self, symbol: str) -> List[Position]:
        """获取持仓信息"""
        pass

    @abstractmethod
    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        """设置杠杆倍数"""
        pass

    @abstractmethod
    async def create_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        size: float,
        price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> Order:
        """创建订单"""
        pass

    @abstractmethod
    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """取消订单"""
        pass

    @abstractmethod
    async def close(self):
        """关闭连接"""
        pass

    async def __aenter__(self) -> "BaseExchange":
        """异步上下文管理器入口"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.close()
```

---

### 1.2 实现CCXT适配器

**文件**: `src/ai_trader/exchange/ccxt_adapter.py`

核心逻辑：
- 包装`ccxt.Exchange`实例
- 转换CCXT数据格式到内部模型
- 统一异常处理

```python
"""CCXT统一适配器"""

import ccxt.async_support as ccxt
from typing import List, Optional, Dict, Any
from datetime import datetime

from .base import (
    BaseExchange, AccountInfo, Ticker, Position,
    OrderSide, OrderType
)
from ..models.market import Kline
from ..models.order import Order
from ..utils.logger import logger


class CCXTAdapter(BaseExchange):
    """CCXT统一交易所适配器"""

    # 时间周期映射: 内部格式 -> CCXT格式
    INTERVAL_MAP = {
        "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
        "1h": "1h", "4h": "4h", "1d": "1d", "1w": "1w",
    }

    def __init__(self, exchange: ccxt.Exchange):
        self._exchange = exchange
        self._exchange_id = exchange.id

    @classmethod
    def from_config(
        cls,
        exchange_id: str,
        api_key: str,
        api_secret: str,
        passphrase: Optional[str] = None,
        testnet: bool = False,
        proxy: Optional[str] = None,
    ) -> "CCXTAdapter":
        """从配置创建适配器"""
        exchange_class = getattr(ccxt, exchange_id, None)
        if exchange_class is None:
            raise ValueError(f"CCXT不支持交易所: {exchange_id}")

        config = {
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "options": {"defaultType": "swap"},  # 合约模式
        }

        if passphrase:
            config["password"] = passphrase

        if proxy:
            config["proxies"] = {"http": proxy, "https": proxy}

        exchange = exchange_class(config)

        # Testnet切换 - 严格模式，不支持则拒绝启动
        # 重要: 仅告警可能导致误连实盘，必须强制失败
        if testnet:
            if hasattr(exchange, 'set_sandbox_mode'):
                exchange.set_sandbox_mode(True)
                logger.info(f"{exchange_id} 已切换到Testnet模式")
            else:
                # 不支持sandbox的交易所，拒绝在testnet模式下使用通用适配器
                raise ValueError(
                    f"{exchange_id} 不支持set_sandbox_mode，无法安全切换到Testnet。"
                    f"请使用专用适配器(如BinanceAdapter)或检查交易所是否支持Testnet。"
                    f"支持Testnet的交易所: binance, bybit"
                )

        return cls(exchange)

    async def get_account(self) -> AccountInfo:
        """获取账户信息"""
        try:
            balance = await self._exchange.fetch_balance()
            usdt = balance.get("USDT", {})
            return AccountInfo(
                total_equity=float(usdt.get("total", 0)),
                available_balance=float(usdt.get("free", 0)),
                margin_used=float(usdt.get("used", 0)),
                unrealized_pnl=0.0,  # 需要从持仓汇总
            )
        except ccxt.BaseError as e:
            logger.error(f"CCXT获取账户失败: {e}")
            raise

    async def get_klines(
        self,
        symbol: str,
        interval: str = "15m",
        limit: int = 100
    ) -> List[Kline]:
        """获取K线数据"""
        try:
            ccxt_interval = self.INTERVAL_MAP.get(interval, interval)
            ohlcv = await self._exchange.fetch_ohlcv(
                symbol, timeframe=ccxt_interval, limit=limit
            )
            return [
                Kline(
                    timestamp=int(candle[0]),
                    open=float(candle[1]),
                    high=float(candle[2]),
                    low=float(candle[3]),
                    close=float(candle[4]),
                    volume=float(candle[5]),
                )
                for candle in ohlcv
            ]
        except ccxt.BaseError as e:
            logger.error(f"CCXT获取K线失败: {e}")
            raise

    async def get_ticker(self, symbol: str) -> Ticker:
        """获取实时行情"""
        try:
            ticker = await self._exchange.fetch_ticker(symbol)
            return Ticker(
                symbol=symbol,
                last_price=float(ticker.get("last", 0)),
                bid_price=float(ticker.get("bid", 0)),
                ask_price=float(ticker.get("ask", 0)),
                high_24h=float(ticker.get("high", 0)),
                low_24h=float(ticker.get("low", 0)),
                volume_24h=float(ticker.get("baseVolume", 0)),
                change_24h=float(ticker.get("percentage", 0)),
            )
        except ccxt.BaseError as e:
            logger.error(f"CCXT获取行情失败: {e}")
            raise

    async def get_positions(self, symbol: str) -> List[Position]:
        """获取持仓信息"""
        try:
            positions = await self._exchange.fetch_positions([symbol])
            return [
                Position(
                    symbol=pos["symbol"],
                    side="long" if pos["side"] == "long" else "short",
                    size=abs(float(pos.get("contracts", 0))),
                    entry_price=float(pos.get("entryPrice", 0)),
                    mark_price=float(pos.get("markPrice", 0)),
                    unrealized_pnl=float(pos.get("unrealizedPnl", 0)),
                    leverage=int(pos.get("leverage", 1)),
                    margin_mode=pos.get("marginMode", "cross"),
                    liquidation_price=pos.get("liquidationPrice"),
                )
                for pos in positions
                if float(pos.get("contracts", 0)) != 0
            ]
        except ccxt.BaseError as e:
            logger.error(f"CCXT获取持仓失败: {e}")
            raise

    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        """设置杠杆倍数"""
        try:
            await self._exchange.set_leverage(leverage, symbol)
            return True
        except ccxt.BaseError as e:
            logger.error(f"CCXT设置杠杆失败: {e}")
            return False

    async def create_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        size: float,
        price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> Order:
        """创建订单"""
        try:
            # 映射方向
            ccxt_side = "buy" if side in [OrderSide.OPEN_LONG, OrderSide.CLOSE_SHORT] else "sell"
            ccxt_type = order_type.value

            params = {}
            if side in [OrderSide.CLOSE_LONG, OrderSide.CLOSE_SHORT]:
                params["reduceOnly"] = True

            # 注意: stopLoss/takeProfit参数格式因交易所而异
            # Binance: 需要单独创建止损止盈订单
            # Bybit: 支持在下单时附带
            # 此处为简化版本，实际使用需按交易所适配
            # 推荐: 使用专用适配器(如BinanceAdapter)处理止损止盈
            if stop_loss and self._exchange_id in ["bybit", "okx"]:
                params["stopLoss"] = {"triggerPrice": stop_loss}
            if take_profit and self._exchange_id in ["bybit", "okx"]:
                params["takeProfit"] = {"triggerPrice": take_profit}

            result = await self._exchange.create_order(
                symbol=symbol,
                type=ccxt_type,
                side=ccxt_side,
                amount=size,
                price=price,
                params=params,
            )

            return Order(
                order_id=result["id"],
                symbol=symbol,
                side=side.value,
                order_type=order_type.value,
                size=size,
                price=price,
                status=result.get("status", "unknown"),
                filled_size=float(result.get("filled", 0)),
                avg_price=result.get("average"),
                created_at=datetime.now(),
            )
        except ccxt.BaseError as e:
            logger.error(f"CCXT创建订单失败: {e}")
            raise

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """取消订单"""
        try:
            await self._exchange.cancel_order(order_id, symbol)
            return True
        except ccxt.BaseError as e:
            logger.error(f"CCXT取消订单失败: {e}")
            return False

    async def close(self):
        """关闭连接"""
        await self._exchange.close()
```

---

### 1.3 重构WeexClient

**文件**: `src/ai_trader/exchange/weex_client.py`

改造方案：
```python
class WeexClient(BaseExchange):
    def __init__(self):
        self._ccxt_client = ccxt.weex({...})
        self._adapter = CCXTAdapter(self._ccxt_client)
```

**注意**: 如果CCXT对WEEX支持不完整，保留自定义实现作为fallback。

---

### 1.4 配置系统升级

**文件**: `src/ai_trader/config.py`

新增配置项：

```python
# 在 TradingConfig 类中新增以下字段

class TradingConfig(BaseSettings):
    # ... 现有字段 ...

    # ============= 交易所配置 =============
    exchange_type: Literal["weex", "binance", "bybit", "okx"] = Field(
        default="weex", validation_alias="EXCHANGE_TYPE"
    )
    use_ccxt: bool = Field(default=True, validation_alias="USE_CCXT")

    # ============= 运行模式 =============
    trading_mode: Literal["testnet", "live"] = Field(
        default="testnet", validation_alias="TRADING_MODE"
    )

    # ============= Testnet配置 =============
    testnet_exchange: str = Field(default="binance", validation_alias="TESTNET_EXCHANGE")
    testnet_api_key: str = Field(default="", validation_alias="TESTNET_API_KEY")
    testnet_api_secret: str = Field(default="", validation_alias="TESTNET_API_SECRET")

    # ============= Binance配置 =============
    binance_api_key: str = Field(default="", validation_alias="BINANCE_API_KEY")
    binance_api_secret: str = Field(default="", validation_alias="BINANCE_API_SECRET")

    # ============= Bybit配置 =============
    bybit_api_key: str = Field(default="", validation_alias="BYBIT_API_KEY")
    bybit_api_secret: str = Field(default="", validation_alias="BYBIT_API_SECRET")

    # ============= OKX配置 =============
    okx_api_key: str = Field(default="", validation_alias="OKX_API_KEY")
    okx_api_secret: str = Field(default="", validation_alias="OKX_API_SECRET")
    okx_passphrase: str = Field(default="", validation_alias="OKX_PASSPHRASE")

    def get_exchange_credentials(self, exchange_type: str) -> dict:
        """获取指定交易所的凭证"""
        credentials_map = {
            "weex": {
                "api_key": self.weex_api_key,
                "api_secret": self.weex_api_secret,
                "passphrase": self.weex_passphrase,
            },
            "binance": {
                "api_key": self.binance_api_key,
                "api_secret": self.binance_api_secret,
            },
            "bybit": {
                "api_key": self.bybit_api_key,
                "api_secret": self.bybit_api_secret,
            },
            "okx": {
                "api_key": self.okx_api_key,
                "api_secret": self.okx_api_secret,
                "passphrase": self.okx_passphrase,
            },
        }
        creds = credentials_map.get(exchange_type)
        if not creds or not creds.get("api_key"):
            raise ValueError(f"未配置{exchange_type}的API凭证")
        return creds

    # ============= 决策模式 =============
    decision_mode: Literal["quant_only", "llm_only", "hybrid"] = Field(
        default="hybrid", validation_alias="DECISION_MODE"
    )
    # 权重配置 (原始值，决策层会自动归一化)
    # 默认比例: 量化50% + LLM35% + 情绪15% = 100%
    quant_weight: float = Field(default=0.50, validation_alias="QUANT_WEIGHT")
    llm_weight: float = Field(default=0.35, validation_alias="LLM_WEIGHT")
    sentiment_weight: float = Field(default=0.15, validation_alias="SENTIMENT_WEIGHT")

    def get_normalized_weights(self) -> dict:
        """获取归一化后的权重，确保总和为1"""
        total = self.quant_weight + self.llm_weight
        if self.sentiment_enabled:
            total += self.sentiment_weight

        if total == 0:
            # 默认均分
            return {"quant": 0.5, "llm": 0.5, "sentiment": 0.0}

        return {
            "quant": self.quant_weight / total,
            "llm": self.llm_weight / total,
            "sentiment": (self.sentiment_weight / total) if self.sentiment_enabled else 0.0,
        }

    # ============= 情绪分析 =============
    sentiment_enabled: bool = Field(default=False, validation_alias="SENTIMENT_ENABLED")

    # ============= 策略选择 =============
    enabled_strategies: str = Field(
        default="trend_following,mean_reversion,breakout",
        validation_alias="ENABLED_STRATEGIES"
    )

    def get_enabled_strategies(self) -> List[str]:
        """获取启用的策略列表"""
        return [s.strip() for s in self.enabled_strategies.split(",")]

    @property
    def is_testnet(self) -> bool:
        return self.trading_mode == "testnet"
```

---

### 1.5 依赖注入改造

**文件**: `src/ai_trader/exchange/__init__.py`

引入工厂函数：

```python
"""交易所模块 - 工厂函数"""

from typing import Optional
from .base import BaseExchange
from .ccxt_adapter import CCXTAdapter
from .weex_client import WeexClient
from ..config import config
from ..utils.logger import logger


def create_exchange_client() -> BaseExchange:
    """创建交易所客户端实例

    根据配置自动选择合适的实现：
    - testnet模式: 使用专用适配器连接testnet交易所
    - live模式: 根据use_ccxt配置选择CCXT或原生实现
    """
    from .binance_adapter import BinanceAdapter

    # Testnet仅允许有专用适配器或明确支持的交易所
    SUPPORTED_TESTNET_EXCHANGES = ["binance", "bybit"]

    if config.trading_mode == "testnet":
        exchange = config.testnet_exchange.lower()
        logger.info(f"创建Testnet客户端: {exchange}")

        if exchange not in SUPPORTED_TESTNET_EXCHANGES:
            raise ValueError(
                f"Testnet模式不支持 {exchange}。"
                f"支持的交易所: {SUPPORTED_TESTNET_EXCHANGES}。"
                f"请使用实盘模式或切换到支持的交易所。"
            )

        # Binance使用专用适配器
        if exchange == "binance":
            return BinanceAdapter(
                api_key=config.testnet_api_key,
                api_secret=config.testnet_api_secret,
                testnet=True,
                proxy=config.proxy_url or None,
            )

        # Bybit等其他支持的交易所使用CCXT适配器
        # 注意: CCXTAdapter.from_config会校验set_sandbox_mode支持
        return CCXTAdapter.from_config(
            exchange_id=exchange,
            api_key=config.testnet_api_key,
            api_secret=config.testnet_api_secret,
            testnet=True,
            proxy=config.proxy_url or None,
        )

    # Live模式 - 使用各交易所独立的凭证
    exchange_type = config.exchange_type
    creds = config.get_exchange_credentials(exchange_type)

    if exchange_type == "weex":
        if config.use_ccxt:
            try:
                return CCXTAdapter.from_config(
                    exchange_id="weex",
                    api_key=creds["api_key"],
                    api_secret=creds["api_secret"],
                    passphrase=creds.get("passphrase"),
                    testnet=False,
                    proxy=config.proxy_url or None,
                )
            except ValueError:
                logger.warning("CCXT不支持WEEX，回退到原生实现")
                return WeexClient()
        else:
            return WeexClient()

    elif exchange_type == "binance":
        # Binance推荐使用专用适配器
        return BinanceAdapter(
            api_key=creds["api_key"],
            api_secret=creds["api_secret"],
            testnet=False,
            proxy=config.proxy_url or None,
        )

    else:
        # 其他交易所使用通用CCXT适配器 + 各自凭证
        return CCXTAdapter.from_config(
            exchange_id=exchange_type,
            api_key=creds["api_key"],
            api_secret=creds["api_secret"],
            passphrase=creds.get("passphrase"),
            testnet=False,
            proxy=config.proxy_url or None,
        )


# 导出
__all__ = [
    "BaseExchange",
    "CCXTAdapter",
    "WeexClient",
    "create_exchange_client",
]
```

---

### 1.6 测试

**文件**: `tests/exchange/test_ccxt_adapter.py`

验证：
- 数据格式转换正确性
- 与原WEEX实现行为一致
- 所有现有测试通过

---

## 依赖变更

```toml
[dependencies]
ccxt = ">=4.2.0"
```

---

## 验证方法

1. 回归测试通过
2. Testnet对比测试（CCXT vs 原生实现）

---

## 风险控制

- CCXT可能不支持WEEX → 保留原生实现
- 性能损耗 → 监控延迟指标

---

## 相关文档

- [主文档](./ai_quant_system_plan.md)
- [系统架构](./ai_quant_plan_architecture.md)
- [Phase 2: 模拟交易环境](./ai_quant_plan_phase2_testnet.md)
