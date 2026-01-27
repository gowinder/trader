# 快速修复建议

## 现状
1年回测：胜率37.45%，收益-24.89%，最大回撤26.66%

## 3个立即可执行的修复

### 修复1：提高信号置信度门槛 (预期改进: +5%胜率)

```python
# src/ai_trader/strategies/strategy_selector.py
# 在 aggregate_signals() 方法最后添加：

def aggregate_signals(self, df, market_class):
    # ... 现有代码 ...

    # 🔧 修复：过滤低置信度信号
    if final_confidence < 0.70:  # 原来没有这个检查
        return AggregatedSignal(
            action=SignalAction.HOLD,
            confidence=0.5,
            contributing_strategies=[],
            reason="Signal confidence too low (< 0.70)"
        )

    return final_signal
```

### 修复2：收紧止损参数 (预期改进: -4%回撤)

```python
# src/ai_trader/strategies/strategy_base.py
# TrendFollowingStrategy.generate_signal() 方法中：

# 原来：
stop_loss = current_price - atr * 2  # 🔧 修改这里
take_profit = current_price + atr * 4

# 修改为：
stop_loss = current_price - atr * 1.5  # 更保守
take_profit = current_price + atr * 3   # 对应调整
```

同样修改所有策略的止损/止盈。

### 修复3：添加波动率过滤 (预期改进: -20%交易次数)

```python
# src/ai_trader/strategies/strategy_selector.py
# 在 aggregate_signals() 开头添加：

def aggregate_signals(self, df, market_class):
    # 🔧 修复：高波动期避免交易
    if market_class.volatility > 2.5:  # ATR > 2.5%
        return AggregatedSignal(
            action=SignalAction.HOLD,
            confidence=0.3,
            contributing_strategies=[],
            reason="Market volatility too high"
        )

    # ... 继续现有代码 ...
```

## 预期效果

| 指标 | 当前 | 修复后预期 | 改进 |
|------|------|-----------|------|
| 胜率 | 37.45% | ~42% | +5% |
| 交易次数 | 275 | ~150 | -45% |
| 最大回撤 | 26.66% | ~22% | -4% |
| 收益率 | -24.89% | -15~-10% | +10-15% |

⚠️ **注意**：这些是基于经验的估计，实际效果需要重新回测验证。

## 执行步骤

1. 应用上述3个修复
2. 重新运行回测：
   ```bash
   export UV_NO_CACHE=1
   uv run python scripts/run_backtest.py --symbol BTCUSDT --start 2024-01-01
   ```
3. 对比结果

## 根本解决方案

快速修复只是临时缓解，根本解决需要：
1. **真实数据** - 当前使用模拟数据
2. **参数优化** - 当前参数未经优化
3. **Walk-forward验证** - 避免过拟合

详见 `STRATEGY_OPTIMIZATION_PLAN.md`
