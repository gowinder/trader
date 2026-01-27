# 策略优化计划

## 当前问题

1年回测结果（2024-01-01 ~ 2025-01-01）：
- ❌ 胜率：37.45% (目标: >55%)
- ❌ 收益率：-24.89% (目标: >0%)
- ❌ 最大回撤：26.66% (目标: <20%)
- ⚠️ 盈亏比：1.10 (目标: >1.5, 接近)

## 问题根因

### 1. 数据质量问题
```python
# 当前：使用模拟数据
close_prices = np.cumsum(np.random.randn(n)) * 100 + 50000
```
- **问题**：随机游走数据不反映真实市场规律
- **影响**：策略无法捕捉真实趋势和形态
- **优先级**：🔴 高

### 2. 策略参数未优化
当前策略使用硬编码参数：
- 趋势跟随：MA(10, 30)
- 均值回归：RSI(14), BB(20, 2.0)
- 突破：Lookback(20), Volume(1.5x)

这些参数未经过任何优化或验证。

### 3. 入场过于频繁
- 交易次数：275笔/年 (平均1.3天1笔)
- 信号比例：19.4% (1704/8785)
- **问题**：手续费累积 $466.97 (4.67%)

## 优化方案

### Phase 1: 真实数据获取 (优先级: 🔴 高)

#### 1.1 对接 Binance API
```python
# scripts/fetch_binance_data.py
import ccxt
import pandas as pd

def fetch_historical_klines(
    symbol: str,
    start_date: str,
    end_date: str,
    interval: str = "1h"
) -> pd.DataFrame:
    """Fetch real historical data from Binance"""
    exchange = ccxt.binance()

    # Convert to timestamp
    since = exchange.parse8601(f"{start_date}T00:00:00Z")
    end = exchange.parse8601(f"{end_date}T23:59:59Z")

    all_ohlcv = []
    while since < end:
        ohlcv = exchange.fetch_ohlcv(
            symbol=symbol,
            timeframe=interval,
            since=since,
            limit=1000
        )
        if not ohlcv:
            break
        all_ohlcv.extend(ohlcv)
        since = ohlcv[-1][0] + 1

    # Convert to DataFrame
    df = pd.DataFrame(
        all_ohlcv,
        columns=["timestamp", "open", "high", "low", "close", "volume"]
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df
```

#### 1.2 数据缓存
```python
# 避免重复请求
cache_file = f"data/cache/{symbol}_{start}_{end}_{interval}.pkl"
if os.path.exists(cache_file):
    return pd.read_pickle(cache_file)
else:
    df = fetch_historical_klines(...)
    df.to_pickle(cache_file)
    return df
```

### Phase 2: 策略参数优化 (优先级: 🟡 中)

#### 2.1 参数网格搜索
```python
# 趋势跟随策略参数空间
param_grid = {
    "fast_ma": [5, 10, 15, 20],
    "slow_ma": [20, 30, 40, 50],
    "atr_stop_loss": [1.5, 2.0, 2.5],
    "atr_take_profit": [3.0, 4.0, 5.0],
}

best_params = None
best_sharpe = -float("inf")

for params in ParameterGrid(param_grid):
    result = run_backtest_with_params(df, params)
    if result.sharpe_ratio > best_sharpe:
        best_sharpe = result.sharpe_ratio
        best_params = params
```

#### 2.2 Walk-Forward 验证
```python
# 避免过拟合
train_period = 9  # months
test_period = 3   # months

for i in range(0, len(df), test_period * 30 * 24):
    train_df = df[i : i + train_period * 30 * 24]
    test_df = df[i + train_period * 30 * 24 : i + (train_period + test_period) * 30 * 24]

    # 在训练集上优化参数
    best_params = optimize_params(train_df)

    # 在测试集上验证
    result = run_backtest(test_df, best_params)
    print(f"Test Period {i}: Sharpe={result.sharpe_ratio}")
```

### Phase 3: 入场过滤优化 (优先级: 🟡 中)

#### 3.1 提高信号质量门槛
```python
# strategy_selector.py
def aggregate_signals(self, df, market_class):
    signal = super().aggregate_signals(df, market_class)

    # 过滤低置信度信号
    if signal.confidence < 0.7:
        return Signal(action=SignalAction.HOLD, confidence=0.5, reason="Low confidence")

    # 过滤高波动期（避免假信号）
    if market_class.volatility > 3.0:  # ATR > 3%
        return Signal(action=SignalAction.HOLD, confidence=0.5, reason="High volatility")

    return signal
```

#### 3.2 多时间框架确认
```python
# 要求多个时间框架对齐
if not mtf_data or mtf_data.confluence_score < 0.6:
    return Signal(action=SignalAction.HOLD, confidence=0.5, reason="Weak MTF alignment")
```

### Phase 4: 风险管理增强 (优先级: 🟢 低)

#### 4.1 仓位大小动态调整
```python
# 根据胜率调整仓位
if recent_win_rate < 0.4:
    position_size *= 0.5  # 连续亏损时减半仓位
elif recent_win_rate > 0.6:
    position_size *= 1.2  # 连续盈利时增加仓位（上限50%）
```

#### 4.2 时间止损
```python
# 持仓超过N根K线自动平仓
if current_bar - entry_bar > 48:  # 持仓超过48小时
    close_position(reason="time_stop")
```

## 实施计划

### Week 1: 真实数据 + 基础优化
- [ ] Day 1-2: 实现 Binance 数据获取
- [ ] Day 3-4: 参数网格搜索框架
- [ ] Day 5-6: 运行优化，找到最佳参数
- [ ] Day 7: 验证优化结果

### Week 2: 进阶优化 + 验证
- [ ] Day 1-2: Walk-forward 验证
- [ ] Day 3-4: 信号过滤优化
- [ ] Day 5-6: 多币种验证（BTC/ETH/SOL）
- [ ] Day 7: 生成最终报告

## 预期改进

保守估计（基于真实数据 + 参数优化）：
- 胜率：37% → **48-52%** (+11-15%)
- 盈亏比：1.10 → **1.3-1.5** (+0.2-0.4)
- 最大回撤：26.66% → **15-18%** (-8-11%)
- 收益率：-24.89% → **5-15%** (+30-40%)
- 夏普比率：-0.58 → **0.8-1.2** (+1.4-1.8)

## 快速修复（临时方案）

如果需要立即改善结果，可以先尝试：

### 1. 提高信号置信度门槛
```bash
# 修改 config.py
# 在策略选择器中过滤低置信度信号
```

### 2. 减少交易频率
```python
# strategy_selector.py - aggregate_signals()
# 添加：if signal.confidence < 0.75: return HOLD
```

### 3. 收紧止损
```python
# strategy_base.py - TrendFollowingStrategy
# 修改：stop_loss = price ± ATR × 1.5  # 原来是2.0
```

预期改进（未经验证）：
- 交易次数：275 → ~150 (-45%)
- 胜率：37% → ~42% (+5%)
- 最大回撤：26.66% → ~22% (-4%)

## 总结

**核心问题**：模拟数据 + 未优化参数

**解决方案**：
1. 🔴 **立即执行**：真实数据获取
2. 🟡 **本周完成**：参数优化
3. 🟢 **后续改进**：风险管理增强

**现实预期**：
- 第一次回测很少能达标（这是正常的）
- 优化是迭代过程（需要2-3轮）
- 目标是稳定盈利，不是暴利

**下一步**：
```bash
# 1. 实现真实数据获取
python scripts/fetch_binance_data.py --symbol BTCUSDT --start 2024-01-01 --end 2025-01-01

# 2. 重新运行回测
export UV_NO_CACHE=1
uv run python scripts/run_backtest.py --symbol BTCUSDT --start 2024-01-01 --real-data

# 3. 参数优化
python scripts/optimize_params.py --symbol BTCUSDT --method grid_search
```
