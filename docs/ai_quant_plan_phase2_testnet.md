# AI量化交易系统 - Phase 2: 模拟交易环境

> 本文档是 [AI量化交易系统升级规划](./ai_quant_system_plan.md) 的子文档

**预计时间**: 8天

---

## 目标

接入Binance/Bybit Testnet，搭建无风险验证环境。

---

## 关键任务

### 2.1 调研交易所Testnet

**输出**: `docs/testnet_research.md`

评估维度：
- API接口完整度
- 数据真实性
- 文档质量

**推荐选择**: Binance Testnet（优先）+ Bybit Testnet（备选）

---

### 2.2 环境切换配置

**文件**: `src/ai_trader/config.py`

```python
trading_mode: Literal["testnet", "live"] = "testnet"
testnet_exchange: str = "binance"
testnet_api_key: str
testnet_api_secret: str
```

---

### 2.3 实现Binance适配器

**文件**: `src/ai_trader/exchange/binance_adapter.py`

```python
"""Binance交易所适配器 - 支持Testnet"""

import ccxt.async_support as ccxt
from typing import Optional

from .ccxt_adapter import CCXTAdapter
from ..utils.logger import logger


class BinanceAdapter(CCXTAdapter):
    """Binance交易所适配器，继承CCXT适配器并添加Binance特定配置"""

    # Binance Testnet URLs
    TESTNET_URLS = {
        "fapiPublic": "https://testnet.binancefuture.com/fapi/v1",
        "fapiPrivate": "https://testnet.binancefuture.com/fapi/v1",
        "fapiPrivateV2": "https://testnet.binancefuture.com/fapi/v2",
    }

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        testnet: bool = False,
        proxy: Optional[str] = None,
    ):
        config = {
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "options": {
                "defaultType": "future",  # 使用U本位合约
                "adjustForTimeDifference": True,  # 自动校准时间戳
            },
        }

        if testnet:
            config["sandbox"] = True
            # Binance Testnet需要特殊URL配置
            config["urls"] = {"api": self.TESTNET_URLS}
            logger.info("使用Binance Testnet环境")

        if proxy:
            config["proxies"] = {"http": proxy, "https": proxy}

        exchange = ccxt.binance(config)
        super().__init__(exchange)

    @classmethod
    def create(
        cls,
        api_key: str,
        api_secret: str,
        testnet: bool = False,
        proxy: Optional[str] = None,
    ) -> "BinanceAdapter":
        """工厂方法创建适配器"""
        return cls(api_key, api_secret, testnet, proxy)

    async def set_position_mode(self, hedge_mode: bool = True) -> bool:
        """设置持仓模式

        Args:
            hedge_mode: True=双向持仓, False=单向持仓
        """
        try:
            await self._exchange.fapiPrivatePostPositionSideDual({
                "dualSidePosition": "true" if hedge_mode else "false"
            })
            logger.info(f"设置持仓模式: {'双向' if hedge_mode else '单向'}")
            return True
        except ccxt.BaseError as e:
            # 如果已经是目标模式，会报错但不影响
            if "No need to change" in str(e):
                return True
            logger.error(f"设置持仓模式失败: {e}")
            return False

    async def set_margin_type(self, symbol: str, margin_type: str = "CROSSED") -> bool:
        """设置保证金模式

        Args:
            symbol: 交易对
            margin_type: CROSSED(全仓) / ISOLATED(逐仓)
        """
        try:
            await self._exchange.fapiPrivatePostMarginType({
                "symbol": symbol.replace("/", "").replace(":USDT", ""),
                "marginType": margin_type,
            })
            logger.info(f"设置保证金模式: {margin_type}")
            return True
        except ccxt.BaseError as e:
            if "No need to change" in str(e):
                return True
            logger.error(f"设置保证金模式失败: {e}")
            return False

    async def get_funding_rate(self, symbol: str) -> float:
        """获取资金费率"""
        try:
            result = await self._exchange.fapiPublicGetPremiumIndex({
                "symbol": symbol.replace("/", "").replace(":USDT", "")
            })
            return float(result.get("lastFundingRate", 0))
        except ccxt.BaseError as e:
            logger.error(f"获取资金费率失败: {e}")
            return 0.0
```

---

### 2.4 工厂函数增强

**文件**: `src/ai_trader/exchange/__init__.py`

```python
def create_exchange_client() -> BaseExchange:
    if config.trading_mode == "testnet":
        if config.testnet_exchange == "binance":
            # 使用专用适配器，传入testnet凭证
            return BinanceAdapter(
                api_key=config.testnet_api_key,
                api_secret=config.testnet_api_secret,
                testnet=True,
                proxy=config.proxy_url or None,
            )
    elif config.trading_mode == "live":
        creds = config.get_exchange_credentials(config.exchange_type)
        return WeexClient()  # 或其他实现
```
> 完整实现见 [Phase 1: 依赖注入改造](./ai_quant_plan_phase1_ccxt.md#15-依赖注入改造)

---

### 2.5 测试验证

**文件**: `tests/exchange/test_testnet_live_parity.py`

对比testnet和live的：
- K线数据一致性
- 订单流程完整性

---

## 验证方法

在Binance Testnet运行完整交易周期（数据获取 → 决策 → 下单）。

---

## 风险控制

- Testnet数据滞后 → 选择大厂交易所
- API限制更严格 → 调整请求频率

---

## 相关文档

- [主文档](./ai_quant_system_plan.md)
- [Phase 1: CCXT集成](./ai_quant_plan_phase1_ccxt.md)
- [Phase 3: 专业交易员流程](./ai_quant_plan_phase3_trading.md)
