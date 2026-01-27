#!/usr/bin/env python3
"""Optimize Trend Following Strategy parameters"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime
import pandas as pd
from itertools import product

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from ai_trader.backtest.engine import BacktestEngine, BacktestConfig
from ai_trader.strategies.strategy_base import TrendFollowingStrategy, SignalAction
from ai_trader.data.fetcher import CachedDataFetcher


class OptimizableTrendStrategy(TrendFollowingStrategy):
    """Trend strategy with configurable parameters"""

    def __init__(self, fast_ma: int = 10, slow_ma: int = 30, stop_loss_atr: float = 2.0, take_profit_atr: float = 4.0):
        super().__init__()
        self.fast_ma_period = fast_ma
        self.slow_ma_period = slow_ma
        self.stop_loss_atr = stop_loss_atr
        self.take_profit_atr = take_profit_atr

    def generate_signal(self, df: pd.DataFrame):
        """Override to use custom parameters"""
        if len(df) < self.slow_ma_period:
            from ai_trader.strategies.strategy_base import Signal, SignalAction
            return Signal(
                action=SignalAction.HOLD,
                confidence=0.0,
                reason="Insufficient data for trend following",
            )

        close = df["close"]
        current_price = float(close.iloc[-1])

        # Calculate indicators
        fast_ma = self.calculate_ma(close, self.fast_ma_period)
        slow_ma = self.calculate_ma(close, self.slow_ma_period)
        macd, signal_line, histogram = self.calculate_macd(close)
        atr = self.calculate_atr(df)

        # Check for golden cross (bullish)
        if fast_ma > slow_ma and macd > signal_line and histogram > 0:
            from ai_trader.strategies.strategy_base import Signal, SignalAction
            confidence = min(0.85, 0.6 + abs(histogram) * 0.01)
            stop_loss = current_price - atr * self.stop_loss_atr
            take_profit = current_price + atr * self.take_profit_atr

            return Signal(
                action=SignalAction.LONG,
                confidence=confidence,
                entry_price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                reason=f"Golden cross: MA{self.fast_ma_period} > MA{self.slow_ma_period}, MACD bullish",
            )

        # Check for death cross (bearish)
        elif fast_ma < slow_ma and macd < signal_line and histogram < 0:
            from ai_trader.strategies.strategy_base import Signal, SignalAction
            confidence = min(0.85, 0.6 + abs(histogram) * 0.01)
            stop_loss = current_price + atr * self.stop_loss_atr
            take_profit = current_price - atr * self.take_profit_atr

            return Signal(
                action=SignalAction.SHORT,
                confidence=confidence,
                entry_price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                reason=f"Death cross: MA{self.fast_ma_period} < MA{self.slow_ma_period}, MACD bearish",
            )

        else:
            from ai_trader.strategies.strategy_base import Signal, SignalAction
            return Signal(
                action=SignalAction.HOLD,
                confidence=0.5,
                reason="No clear trend signal",
            )


async def test_parameters(df: pd.DataFrame, fast_ma: int, slow_ma: int, sl_atr: float, tp_atr: float) -> dict:
    """Test a parameter combination"""
    strategy = OptimizableTrendStrategy(fast_ma, slow_ma, sl_atr, tp_atr)

    signals = []
    for i in range(len(df)):
        window_df = df.iloc[max(0, i - 100) : i + 1]

        if len(window_df) < 50:
            signals.append({
                "action": "hold",
                "confidence": 0.0,
                "entry_price": None,
                "stop_loss": None,
                "take_profit": None,
            })
            continue

        signal = strategy.generate_signal(window_df)

        action_map = {
            "long": "open_long",
            "short": "open_short",
            "close_long": "close_long",
            "close_short": "close_short",
            "hold": "hold",
        }
        action = action_map.get(signal.action.value, "hold")

        signals.append({
            "action": action,
            "confidence": signal.confidence,
            "entry_price": signal.entry_price,
            "stop_loss": signal.stop_loss,
            "take_profit": signal.take_profit,
        })

    signals_df = pd.DataFrame(signals)

    # Run backtest
    bt_config = BacktestConfig(
        initial_capital=10000.0,
        commission_rate=0.0002,
        slippage_rate=0.001,
        max_position_size=0.5,
        enable_stop_loss=True,
        enable_take_profit=True,
    )
    engine = BacktestEngine(bt_config)
    result = engine.run(df, signals_df)

    return {
        "fast_ma": fast_ma,
        "slow_ma": slow_ma,
        "sl_atr": sl_atr,
        "tp_atr": tp_atr,
        "total_trades": result.total_trades,
        "win_rate": result.win_rate,
        "return_pct": result.return_pct,
        "max_drawdown": result.max_drawdown_pct,
        "sharpe_ratio": result.sharpe_ratio,
        "win_loss_ratio": result.avg_win_loss_ratio,
        "profit_factor": result.profit_factor,
    }


async def main():
    """Main entry point"""
    print("="*60)
    print("TREND FOLLOWING STRATEGY PARAMETER OPTIMIZATION")
    print("="*60)

    # Fetch data
    start = datetime.strptime("2024-01-01", "%Y-%m-%d")
    end = datetime.strptime("2025-01-01", "%Y-%m-%d")

    print("\nFetching data...")
    fetcher = CachedDataFetcher(cache_dir="data/cache")
    df = fetcher.get_data(
        symbol="BTC/USDT",
        start_date=start,
        end_date=end,
        timeframe="1h",
    )
    print(f"✓ Loaded {len(df)} candles")

    # Parameter grid
    fast_ma_values = [5, 8, 10, 12, 15]
    slow_ma_values = [20, 25, 30, 40, 50]
    sl_atr_values = [1.5, 2.0, 2.5, 3.0]
    tp_atr_values = [3.0, 4.0, 5.0, 6.0]

    print(f"\nTesting parameter combinations...")
    print(f"Fast MA: {fast_ma_values}")
    print(f"Slow MA: {slow_ma_values}")
    print(f"Stop Loss ATR: {sl_atr_values}")
    print(f"Take Profit ATR: {tp_atr_values}")
    print(f"Total combinations: {len(fast_ma_values) * len(slow_ma_values) * len(sl_atr_values) * len(tp_atr_values)}")

    results = []
    total = len(fast_ma_values) * len(slow_ma_values) * len(sl_atr_values) * len(tp_atr_values)
    count = 0

    for fast_ma, slow_ma, sl_atr, tp_atr in product(fast_ma_values, slow_ma_values, sl_atr_values, tp_atr_values):
        if fast_ma >= slow_ma:
            continue

        count += 1
        if count % 20 == 0:
            print(f"Progress: {count}/{total} ({count/total*100:.1f}%)")

        result = await test_parameters(df, fast_ma, slow_ma, sl_atr, tp_atr)
        results.append(result)

    # Sort results
    print(f"\n{'='*60}")
    print("OPTIMIZATION RESULTS")
    print(f"{'='*60}")

    # Top 10 by win rate
    print("\nTop 10 by Win Rate:")
    print(f"{'Fast MA':>8} {'Slow MA':>8} {'SL ATR':>8} {'TP ATR':>8} {'Trades':>8} {'WR':>8} {'Return':>10} {'Sharpe':>8}")
    print("-"*80)
    by_win_rate = sorted(results, key=lambda x: x['win_rate'], reverse=True)[:10]
    for r in by_win_rate:
        print(f"{r['fast_ma']:>8} {r['slow_ma']:>8} {r['sl_atr']:>8.1f} {r['tp_atr']:>8.1f} {r['total_trades']:>8} {r['win_rate']:>7.1%} {r['return_pct']:>9.1%} {r['sharpe_ratio']:>8.2f}")

    # Top 10 by return
    print("\nTop 10 by Return:")
    print(f"{'Fast MA':>8} {'Slow MA':>8} {'SL ATR':>8} {'TP ATR':>8} {'Trades':>8} {'WR':>8} {'Return':>10} {'Sharpe':>8}")
    print("-"*80)
    by_return = sorted(results, key=lambda x: x['return_pct'], reverse=True)[:10]
    for r in by_return:
        print(f"{r['fast_ma']:>8} {r['slow_ma']:>8} {r['sl_atr']:>8.1f} {r['tp_atr']:>8.1f} {r['total_trades']:>8} {r['win_rate']:>7.1%} {r['return_pct']:>9.1%} {r['sharpe_ratio']:>8.2f}")

    # Top 10 by Sharpe ratio
    print("\nTop 10 by Sharpe Ratio:")
    print(f"{'Fast MA':>8} {'Slow MA':>8} {'SL ATR':>8} {'TP ATR':>8} {'Trades':>8} {'WR':>8} {'Return':>10} {'Sharpe':>8}")
    print("-"*80)
    by_sharpe = sorted(results, key=lambda x: x['sharpe_ratio'], reverse=True)[:10]
    for r in by_sharpe:
        print(f"{r['fast_ma']:>8} {r['slow_ma']:>8} {r['sl_atr']:>8.1f} {r['tp_atr']:>8.1f} {r['total_trades']:>8} {r['win_rate']:>7.1%} {r['return_pct']:>9.1%} {r['sharpe_ratio']:>8.2f}")

    # Best overall (balanced score)
    print("\n" + "="*60)
    print("BEST OVERALL (Balanced Score)")
    print("="*60)

    # Score = win_rate * 0.4 + (return_pct/100) * 0.3 + sharpe_ratio * 0.3
    for r in results:
        r['score'] = r['win_rate'] * 0.4 + (r['return_pct']/100) * 0.3 + max(r['sharpe_ratio'], -1) * 0.3

    best = max(results, key=lambda x: x['score'])
    print(f"\nBest Parameters:")
    print(f"  Fast MA:         {best['fast_ma']}")
    print(f"  Slow MA:         {best['slow_ma']}")
    print(f"  Stop Loss ATR:   {best['sl_atr']}")
    print(f"  Take Profit ATR: {best['tp_atr']}")
    print(f"\nPerformance:")
    print(f"  Total Trades:    {best['total_trades']}")
    print(f"  Win Rate:        {best['win_rate']:.2%}")
    print(f"  Return:          {best['return_pct']:.2%}")
    print(f"  Max Drawdown:    {best['max_drawdown']:.2%}")
    print(f"  Sharpe Ratio:    {best['sharpe_ratio']:.2f}")
    print(f"  Win/Loss Ratio:  {best['win_loss_ratio']:.2f}")
    print(f"  Balanced Score:  {best['score']:.3f}")


if __name__ == "__main__":
    asyncio.run(main())
