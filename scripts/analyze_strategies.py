#!/usr/bin/env python3
"""Analyze individual strategy performance"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime
import pandas as pd

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from ai_trader.backtest.engine import BacktestEngine, BacktestConfig
from ai_trader.strategies.pattern_recognition import PatternRecognizer
from ai_trader.strategies.market_classifier import MarketClassifier, MarketState
from ai_trader.strategies.strategy_base import (
    TrendFollowingStrategy,
    MeanReversionStrategy,
    BreakoutStrategy,
    SignalAction,
)
from ai_trader.data.fetcher import CachedDataFetcher


async def analyze_single_strategy(
    strategy,
    strategy_name: str,
    df: pd.DataFrame,
) -> dict:
    """Analyze performance of a single strategy"""
    print(f"\n{'='*60}")
    print(f"Analyzing: {strategy_name}")
    print(f"{'='*60}")

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

        # Map action
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

    # Print signal statistics
    action_counts = signals_df["action"].value_counts()
    print("\nSignal breakdown:")
    for action, count in action_counts.items():
        print(f"  - {action}: {count} ({count/len(signals_df)*100:.1f}%)")

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

    print(f"\nPerformance:")
    print(f"  Total Trades:    {result.total_trades}")
    print(f"  Win Rate:        {result.win_rate:.2%}")
    print(f"  Return:          {result.return_pct:.2%}")
    print(f"  Max Drawdown:    {result.max_drawdown_pct:.2%}")
    print(f"  Sharpe Ratio:    {result.sharpe_ratio:.2f}")
    print(f"  Win/Loss Ratio:  {result.avg_win_loss_ratio:.2f}")
    print(f"  Profit Factor:   {result.profit_factor:.2f}")

    return {
        "strategy": strategy_name,
        "total_trades": result.total_trades,
        "win_rate": result.win_rate,
        "return_pct": result.return_pct,
        "max_drawdown_pct": result.max_drawdown_pct,
        "sharpe_ratio": result.sharpe_ratio,
        "win_loss_ratio": result.avg_win_loss_ratio,
        "profit_factor": result.profit_factor,
    }


async def main():
    """Main entry point"""
    print("="*60)
    print("STRATEGY PERFORMANCE ANALYSIS")
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

    # Test each strategy
    strategies = [
        (TrendFollowingStrategy(), "Trend Following"),
        (MeanReversionStrategy(), "Mean Reversion"),
        (BreakoutStrategy(), "Breakout"),
    ]

    results = []
    for strategy, name in strategies:
        result = await analyze_single_strategy(strategy, name, df)
        results.append(result)

    # Summary comparison
    print("\n" + "="*60)
    print("STRATEGY COMPARISON")
    print("="*60)
    print(f"{'Strategy':<20} {'Trades':>8} {'Win Rate':>10} {'Return':>10} {'Sharpe':>8} {'W/L':>8}")
    print("-"*72)
    for r in results:
        print(f"{r['strategy']:<20} {r['total_trades']:>8} {r['win_rate']:>9.1%} {r['return_pct']:>9.1%} {r['sharpe_ratio']:>8.2f} {r['win_loss_ratio']:>8.2f}")

    # Recommendations
    print("\n" + "="*60)
    print("RECOMMENDATIONS")
    print("="*60)

    best_wr = max(results, key=lambda x: x['win_rate'])
    best_return = max(results, key=lambda x: x['return_pct'])
    best_sharpe = max(results, key=lambda x: x['sharpe_ratio'])

    print(f"Best Win Rate:   {best_wr['strategy']} ({best_wr['win_rate']:.1%})")
    print(f"Best Return:     {best_return['strategy']} ({best_return['return_pct']:.1%})")
    print(f"Best Sharpe:     {best_sharpe['strategy']} ({best_sharpe['sharpe_ratio']:.2f})")


if __name__ == "__main__":
    asyncio.run(main())
