# Kraken XStock 美股现货交易接入设计

## 1. 概述

接入 Kraken XStock（代币化美股）现货交易，支持全自动 AI 决策的美股买卖。与现有合约交易管线并行，通过适配器层封装差异。

### 关键约束
- **仅做多**：现货不支持做空，无杠杆
- **无 sandbox**：XStock 无公开测试环境，使用 `validate=true` 参数验证订单
- **地域限制**：110+ 国家可用，不含 US/CA/UK/AU
- **资产代码**：股票代码加 `x` 后缀，如 `AAPLx`、`TSLAx`、`SPYx`

## 2. 配置层

### 2.1 config.py 改动

```python
# exchange_type 增加 kraken
exchange_type: Literal["weex", "binance", "bybit", "okx", "kraken"]

# Kraken 凭证
kraken_api_key: str = Field(default="", validation_alias="KRAKEN_API_KEY")
kraken_api_secret: str = Field(default="", validation_alias="KRAKEN_API_SECRET")

# 美股交易对
stock_trading_symbols: str = Field(default="", validation_alias="STOCK_TRADING_SYMBOLS")
# 格式: "AAPLx/USD,TSLAx/USD,SPYx/USD"
```

### 2.2 credentials_map 增加

```python
"kraken": {
    "api_key": self.kraken_api_key,
    "api_secret": self.kraken_api_secret,
}
```

### 2.3 .env.example 新增

```
EXCHANGE_TYPE=kraken
KRAKEN_API_KEY=
KRAKEN_API_SECRET=
STOCK_TRADING_SYMBOLS=
```

## 3. KrakenXStockAdapter

### 3.1 文件
`src/ai_trader/exchange/kraken_xstock_adapter.py`

### 3.2 继承 BaseExchange

内部使用 `ccxt.kraken()`，配置 `options={"defaultType": "spot"}`。

### 3.3 方法实现

| 方法 | 行为 |
|------|------|
| `get_account()` | 调 CCXT `fetch_balance()`，AccountInfo: margin_used=0, unrealized_pnl 从持仓计算 |
| `get_klines()` | CCXT `fetch_ohlcv()`，标准 OHLCV 格式 |
| `get_ticker()` | CCXT `fetch_ticker()` |
| `get_positions()` | 从 balance 中取非零持仓，组装 Position 列表。side="long", leverage=1, margin_mode="spot", liquidation_price=0 |
| `set_leverage()` | **no-op，直接返回 True** |
| `create_order()` | CCXT `create_order(symbol, type, side, amount, price, params={"asset_class": "tokenized_asset"})` |
| `cancel_order()` | CCXT `cancel_order(id, symbol)` |
| `get_available_symbols()` | CCXT `fetch_markets()`，过滤 `spot=True & active=True & quote="USD"`，或直接调 REST `GET /0/public/AssetPairs?aclass_base=tokenized_asset` |

### 3.4 数据映射

```
OrderSide: buy → OPEN_LONG, sell → CLOSE_LONG (禁止 SHORT)

Position 字段:
  side = "long" (spot 无 short)
  leverage = 1
  margin_mode = "spot"
  liquidation_price = 0
  margin = size * mark_price
```

### 3.5 工厂函数

`exchange/__init__.py` 中 `create_exchange_client()` 增加 kraken 分支：

```python
elif config.exchange_type == "kraken":
    return KrakenXStockAdapter(
        api_key=config.kraken_api_key,
        api_secret=config.kraken_api_secret,
    )
```

## 4. 美股决策引擎

### 4.1 提示词

`src/ai_trader/prompts/stock_trading.py`

| 维度 | 合约 prompt | 美股 prompt |
|------|-------------|-------------|
| 角色 | 加密货币期货交易员 | 美股量化交易员 |
| 动作 | open_long/open_short/close/... | buy/sell/hold/add/reduce |
| 杠杆 | 1-10 范围 | 无 |
| 分析维度 | 筹码分布、资金费率 | 成交量、市值、板块轮动 |
| 止损止盈 | ATR + 百分比 | 百分比 |

### 4.2 HybridDecisionEngine 适配

在 `ai/hybrid_decision.py` 中，根据 symbol 所在集合切换：
- 使用 `stock_trading.py` prompt 模板（非 `trading.py`）
- 动作白名单过滤：只保留 buy/sell/hold/add/reduce
- 决策结果中 leverage 固定为 1

## 5. 美股量化策略

### 5.1 目录
`src/ai_trader/strategies/stock/`

### 5.2 模型

```python
class StockSignalAction(Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"

class StockSignal(BaseModel):
    action: StockSignalAction
    confidence: float  # 0.0 ~ 1.0
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    reason: str = ""
```

### 5.3 策略

| 策略 | 逻辑 |
|------|------|
| StockTrendFollowing | MA7 上穿 MA25 且 MACD > 0 → BUY；下穿且 MACD < 0 → SELL |
| StockMeanReversion | RSI(14) < 30 + 价格接近 Bollinger 下轨 → BUY；RSI > 70 + 接近上轨 → SELL |

策略层面**不生成做空信号**。

## 6. Scheduler 调度改动

### 6.1 Symbol 来源

```
all_symbols = config.trading_symbols.split(",")  # 合约
+ config.stock_trading_symbols.split(",")         # 美股现货
```

### 6.2 每 symbol 循环差异化

`run_cycle_for_symbol()` 中通过 `is_stock_symbol(symbol)` 判断。

| 环节 | 合约 | 美股现货 |
|------|------|---------|
| 止损止盈 | 双向（long/short） | 仅单向（long） |
| quantity | `balance * pos% * leverage / price` | `balance * pos% / price` |
| 动作过滤 | 全部 8 种 | 过滤 short/close_short/reduce_short → hold |
| 风控 cooldown | reverse_cooldown 适用 | reverse_cooldown 不适用 |
| 杠杆设定 | `set_leverage()` | 跳过 |
| 持久化 | leverage/margin 如实 | leverage=1, margin=持仓市值 |

### 6.3 is_stock_symbol()

检查 symbol 是否在 `stock_trading_symbols` 配置中，或通过 adapter 的 `market_type` 属性判断。

## 7. 数据模型

### 7.1 position_history 表兼容

现货持仓写入时：
- `leverage` = 1
- `margin` = 持仓市值（size * entry_price）
- `liquidation_price` = None 或 0
- `side` = "long"

无需新增表字段，现有字段足以承载。

### 7.2 订单持久化

`decision` 表中：
- `action` 用 buy/sell/add/reduce/hold
- `leverage` = 1
- `position_size_percent` 照常

## 8. 测试

### 8.1 测试方法

Kraken XStock **无公开 sandbox**。测试方式：
1. 使用 `validate=true` 参数验证订单参数正确性
2. 单元测试 mock Kraken API 响应
3. 小资金实盘验证（推荐先 1 只股票、小仓位）

### 8.2 测试清单

- [ ] `KrakenXStockAdapter` 各方法 API 调用正确
- [ ] `asset_class=tokenized_asset` 参数正确传递
- [ ] 现货 quantity 计算正确（无杠杆）
- [ ] 美股 prompt 模板生成正确的 LLM 请求
- [ ] 动作白名单过滤 short 信号
- [ ] 止损止盈仅检查 long 方向
- [ ] 持仓持久化字段兼容

## 9. 文件变更清单

### 新建
- `src/ai_trader/exchange/kraken_xstock_adapter.py`
- `src/ai_trader/prompts/stock_trading.py`
- `src/ai_trader/strategies/stock/__init__.py`
- `src/ai_trader/strategies/stock/stock_strategy_base.py`
- `src/ai_trader/strategies/stock/stock_trend_following.py`
- `src/ai_trader/strategies/stock/stock_mean_reversion.py`

### 修改
- `src/ai_trader/config.py`
- `src/ai_trader/exchange/__init__.py`
- `src/ai_trader/exchange/base.py`（Position 模型增加 margin_mode 可选字段）
- `src/ai_trader/scheduler.py`（symbol 合并 + 现货差异化分支）
- `src/ai_trader/ai/hybrid_decision.py`（prompt 切换 + 动作过滤）
- `.env.example`

## 10. 风险与限制

- **无 testnet**：只能小资金实盘验证，需谨慎
- **交易时间**：非核心 10 只 xStock 仅 24/5 可交易
- **流动性**：xStock 是较新产品，大额订单可能滑点较大
- **地域**：确认服务地区可用性
