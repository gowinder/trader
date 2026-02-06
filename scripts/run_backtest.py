#!/usr/bin/env python3
"""Backtest script for Phase 4 strategy validation

支持将回测结果保存到 Dashboard 数据库，启用方法:
  1. 配置 DASHBOARD_DATABASE_URL 和 ENABLE_DECISION_PERSISTENCE=true
  2. 添加 --save-to-db 参数
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID
import pandas as pd

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from ai_trader.backtest.engine import BacktestEngine, BacktestConfig
from ai_trader.strategies.pattern_recognition import PatternRecognizer
from ai_trader.strategies.market_classifier import MarketClassifier
from ai_trader.strategies.strategy_selector import StrategySelector
from ai_trader.strategies.signal_filter import SignalFilter
from ai_trader.persistence import DatabaseManager, DecisionPersistenceService
from ai_trader.config import config


async def fetch_historical_data(
    symbol: str,
    start_date: datetime,
    end_date: datetime,
    interval: str = "1h",
    use_real_data: bool = True,
) -> pd.DataFrame:
    """Fetch historical data from exchange

    Args:
        symbol: Trading symbol (e.g., "BTCUSDT")
        start_date: Start date
        end_date: End date
        interval: Candle interval
        use_real_data: Whether to use real data from Binance

    Returns:
        DataFrame with OHLCV data
    """
    if use_real_data:
        # Use real data from Binance
        print(f"Fetching real {symbol} data from Binance...")
        from ai_trader.data.fetcher import CachedDataFetcher

        # Convert symbol format: BTCUSDT -> BTC/USDT
        if "/" not in symbol:
            symbol = f"{symbol[:-4]}/{symbol[-4:]}"

        fetcher = CachedDataFetcher(cache_dir="data/cache")
        df = fetcher.get_data(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            timeframe=interval,
        )
        print(f"✓ Loaded {len(df)} real candles from Binance")
        return df
    else:
        # Generate dummy data (for testing)
        print(f"⚠️  Generating dummy data for {symbol} (use --real-data for actual data)...")
        date_range = pd.date_range(start=start_date, end=end_date, freq=interval)

        np = __import__("numpy")
        close_prices = np.cumsum(np.random.randn(len(date_range))) * 100 + 50000

        data = {
            "timestamp": date_range,
            "open": close_prices + np.random.randn(len(date_range)) * 50,
            "high": close_prices + np.abs(np.random.randn(len(date_range))) * 100,
            "low": close_prices - np.abs(np.random.randn(len(date_range))) * 100,
            "close": close_prices,
            "volume": np.abs(np.random.randn(len(date_range))) * 1000 + 500,
        }

        df = pd.DataFrame(data)
        print(f"Generated {len(df)} dummy candles")
        return df


def generate_signals(df: pd.DataFrame, enable_filters: bool = True) -> pd.DataFrame:
    """Generate trading signals from strategy

    Args:
        df: OHLCV data
        enable_filters: Whether to enable signal filters

    Returns:
        DataFrame with signals
    """
    print("Generating trading signals...")

    # Initialize strategy components
    market_classifier = MarketClassifier()
    strategy_selector = StrategySelector(config.enabled_strategies)
    signal_filter = SignalFilter(min_interval_hours=6) if enable_filters else None

    signals = []

    for i in range(len(df)):
        # Get data window (need at least 50 candles for reliable analysis)
        window_df = df.iloc[max(0, i - 100) : i + 1]

        # Need at least 50 candles for ADX (14*2+1=29) and other indicators
        if len(window_df) < 50:
            # Not enough data
            signals.append(
                {
                    "action": "hold",
                    "confidence": 0.0,
                    "entry_price": None,
                    "stop_loss": None,
                    "take_profit": None,
                }
            )
            continue

        # Classify market state
        market_class = market_classifier.classify(window_df)

        # Generate signal
        signal = strategy_selector.aggregate_signals(window_df, market_class)

        # Map signal action to backtest action format
        action_map = {
            "long": "open_long",
            "short": "open_short",
            "close_long": "close_long",
            "close_short": "close_short",
            "hold": "hold",
        }
        action = action_map.get(signal.action.value, "hold")

        # Apply filters if enabled
        if enable_filters and action != "hold":
            current_time = df.iloc[i]["timestamp"]

            # Filter 1: Confidence threshold (55%)
            if signal.confidence < 0.55:
                action = "hold"
            # Filter 2: Time-based filter (6h interval)
            elif signal_filter:
                allowed, reason = signal_filter.should_allow_signal(signal.action, current_time)
                if not allowed:
                    action = "hold"
                else:
                    signal_filter.record_trade(signal.action, current_time)

        signals.append(
            {
                "action": action,
                "confidence": signal.confidence,
                "entry_price": signal.entry_price,
                "stop_loss": signal.stop_loss,
                "take_profit": signal.take_profit,
            }
        )

    signals_df = pd.DataFrame(signals)
    print(f"Generated {len(signals)} signals")

    # Print signal statistics
    action_counts = signals_df["action"].value_counts()
    print("\nSignal breakdown:")
    for action, count in action_counts.items():
        print(f"  - {action}: {count} ({count/len(signals_df)*100:.1f}%)")

    non_hold = signals_df[signals_df["action"] != "hold"]
    print(f"\nTrading signals (non-hold): {len(non_hold)}")

    return signals_df


async def save_backtest_to_db(
    engine: BacktestEngine,
    result,
    df: pd.DataFrame,
    symbol: str,
    start_date: str,
    end_date: str,
    initial_capital: float,
    interval: str,
) -> Optional[UUID]:
    """保存回测结果到数据库

    Args:
        engine: 回测引擎实例
        result: 回测结果
        df: K线数据
        symbol: 交易对
        start_date: 开始日期
        end_date: 结束日期
        initial_capital: 初始资金
        interval: K线间隔

    Returns:
        回测 ID 或 None
    """
    if not config.dashboard_database_url:
        print("⚠️  未配置 DASHBOARD_DATABASE_URL，跳过数据库保存")
        return None

    print("\n保存回测结果到数据库...")
    db = DatabaseManager(config.dashboard_database_url)
    await db.connect()
    persistence = DecisionPersistenceService(db)

    try:
        # 创建回测记录
        backtest_id = await persistence.create_backtest(
            mode="single",
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            config_snapshot={
                "interval": interval,
                "strategies": config.enabled_strategies,
            },
        )

        # 保存交易记录
        for trade in engine.trades:
            await persistence.save_backtest_trade(
                backtest_id=backtest_id,
                symbol=symbol,
                side=trade.side,
                entry_time=trade.timestamp,
                entry_price=trade.entry_price,
                exit_time=trade.timestamp,
                exit_price=trade.exit_price,
                pnl=trade.pnl,
                pnl_percent=(trade.pnl / (trade.entry_price * trade.size) * 100)
                if trade.pnl and trade.entry_price and trade.size
                else None,
            )

        # 保存权益曲线 (每10个点保存一次，避免数据过多)
        step = max(1, len(engine.equity_curve) // 100)
        for i in range(0, len(engine.equity_curve), step):
            if i < len(df):
                ts = df.iloc[i]["timestamp"]
                if isinstance(ts, str):
                    ts = datetime.fromisoformat(ts)
                await persistence.save_backtest_equity(
                    backtest_id=backtest_id,
                    timestamp=ts,
                    total_equity=engine.equity_curve[i],
                )

        # 完成回测
        await persistence.complete_backtest(
            backtest_id=backtest_id,
            final_capital=result.final_capital,
            total_pnl=result.total_pnl,
            total_trades=result.total_trades,
            winning_trades=result.winning_trades,
            max_drawdown=result.max_drawdown,
            sharpe_ratio=result.sharpe_ratio,
        )

        print(f"✓ 回测结果已保存，ID: {backtest_id}")
        return backtest_id

    except Exception as e:
        print(f"✗ 保存失败: {e}")
        return None
    finally:
        await db.close()


async def run_backtest(
    symbol: str = "BTCUSDT",
    start_date: str = "2024-01-01",
    end_date: str = "2025-01-01",
    interval: str = "1h",
    initial_capital: float = 10000.0,
    use_real_data: bool = True,
    enable_filters: bool = False,
    save_to_db: bool = False,
):
    """Run backtest

    Args:
        symbol: Trading symbol
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        interval: Candle interval
        initial_capital: Initial capital in USDT
        save_to_db: Whether to save results to database
    """
    print("=" * 60)
    print("PHASE 4 BACKTEST - QUANTITATIVE STRATEGY VALIDATION")
    print("=" * 60)
    print()

    # Parse dates
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    # Fetch data
    df = await fetch_historical_data(symbol, start, end, interval, use_real_data=use_real_data)

    # Generate signals
    print("\nGenerating signals...")
    signals = generate_signals(df, enable_filters=enable_filters)

    # Configure backtest
    bt_config = BacktestConfig(
        initial_capital=initial_capital,
        commission_rate=0.0002,  # 0.02%
        slippage_rate=0.001,  # 0.1%
        max_position_size=0.5,  # 50% of capital
        enable_stop_loss=True,
        enable_take_profit=True,
    )

    # Run backtest
    print("\nRunning backtest...")
    engine = BacktestEngine(bt_config)
    result = engine.run(df, signals)

    # Generate report
    report = engine.generate_report(result)
    print(report)

    # Save to database if requested
    if save_to_db:
        await save_backtest_to_db(
            engine=engine,
            result=result,
            df=df,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            interval=interval,
        )

    # Validation checks
    print("\nVALIDATION CHECKS")
    print("-" * 60)

    checks = [
        ("Win Rate > 55%", result.win_rate > 0.55),
        ("Win/Loss Ratio > 1.5", result.avg_win_loss_ratio > 1.5),
        ("Max Drawdown < 20%", result.max_drawdown_pct < 20.0),
        ("Sharpe Ratio > 1.0", result.sharpe_ratio > 1.0),
        ("Positive Return", result.return_pct > 0),
    ]

    passed = 0
    for check_name, check_result in checks:
        status = "✓ PASS" if check_result else "✗ FAIL"
        print(f"{status:>10} - {check_name}")
        if check_result:
            passed += 1

    print()
    print(f"Passed: {passed}/{len(checks)} checks")

    if passed == len(checks):
        print("\n🎉 All validation checks passed!")
    else:
        print("\n⚠️  Some validation checks failed. Review strategy parameters.")


async def compare_modes():
    """Compare pure quant, pure AI, and hybrid modes"""
    print("=" * 60)
    print("MODE COMPARISON: Quant vs AI vs Hybrid")
    print("=" * 60)
    print()

    modes = [
        ("Pure Quantitative", {"quant_weight": 1.0, "ai_weight": 0.0}),
        ("Pure AI", {"quant_weight": 0.0, "ai_weight": 1.0}),
        ("Hybrid (50/50)", {"quant_weight": 0.5, "ai_weight": 0.5}),
    ]

    # TODO: Implement mode comparison
    # This would require:
    # 1. Modify config for each mode
    # 2. Run backtest for each
    # 3. Compare results

    print("Mode comparison not yet implemented.")
    print("Run individual backtests with different config.quant_weight settings.")


async def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Run Phase 4 backtest")
    parser.add_argument(
        "--symbol",
        type=str,
        default="BTCUSDT",
        help="Trading symbol (default: BTCUSDT)",
    )
    parser.add_argument(
        "--start",
        type=str,
        default="2024-01-01",
        help="Start date YYYY-MM-DD (default: 2024-01-01)",
    )
    parser.add_argument(
        "--end",
        type=str,
        default="2025-01-01",
        help="End date YYYY-MM-DD (default: 2025-01-01)",
    )
    parser.add_argument(
        "--interval",
        type=str,
        default="1h",
        help="Candle interval (default: 1h)",
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=10000.0,
        help="Initial capital in USDT (default: 10000)",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Run mode comparison",
    )
    parser.add_argument(
        "--dummy-data",
        action="store_true",
        help="Use dummy data instead of real Binance data",
    )
    parser.add_argument(
        "--save-to-db",
        action="store_true",
        help="Save backtest results to Dashboard database",
    )

    args = parser.parse_args()

    if args.compare:
        await compare_modes()
    else:
        await run_backtest(
            symbol=args.symbol,
            start_date=args.start,
            end_date=args.end,
            interval=args.interval,
            initial_capital=args.capital,
            use_real_data=not args.dummy_data,  # Use real data by default
            save_to_db=args.save_to_db,
        )


if __name__ == "__main__":
    asyncio.run(main())
