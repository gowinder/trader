"""Test Trade Journal with simulated trades"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ai_trader.analytics.trade_journal import (
    TradeJournal,
    TradeEntry,
    TradeDirection,
    EmotionalState,
)
from datetime import datetime, timedelta
import uuid


def create_sample_trades():
    """Create sample trades for testing"""
    trades = []

    # Trade 1: Winning long trade
    trade1 = TradeEntry(
        trade_id=str(uuid.uuid4())[:8],
        timestamp=(datetime.now() - timedelta(days=7)).isoformat(),
        symbol="BTCUSDT",
        direction=TradeDirection.LONG,
        entry_price=60000.0,
        exit_price=62400.0,
        stop_loss_price=59000.0,
        take_profit_price=63000.0,
        position_size=0.1,
        position_value=6000.0,
        leverage=5,
        pnl=240.0,
        pnl_percentage=4.0,
        entry_reason="MA alignment + MACD golden cross + 4H uptrend confirmed",
        ma_alignment=True,
        macd_signal="bullish",
        rsi_value=65.0,
        confluence_score=0.85,
        risk_reward_ratio=2.0,
        actual_reward_risk=2.4,
        emotional_state=EmotionalState.CONFIDENT,
        notes="Perfect setup, entered at support bounce",
        exit_reason="Take profit hit",
        exit_timestamp=(datetime.now() - timedelta(days=6, hours=12)).isoformat(),
        hold_duration=43200,  # 12 hours
    )
    trades.append(trade1)

    # Trade 2: Losing short trade
    trade2 = TradeEntry(
        trade_id=str(uuid.uuid4())[:8],
        timestamp=(datetime.now() - timedelta(days=6)).isoformat(),
        symbol="ETHUSDT",
        direction=TradeDirection.SHORT,
        entry_price=3000.0,
        exit_price=3060.0,
        stop_loss_price=3060.0,
        position_size=2.0,
        position_value=6000.0,
        leverage=3,
        pnl=-120.0,
        pnl_percentage=-2.0,
        entry_reason="Resistance rejection + bearish divergence",
        ma_alignment=False,
        macd_signal="neutral",
        rsi_value=72.0,
        confluence_score=0.45,
        risk_reward_ratio=2.0,
        actual_reward_risk=-1.0,
        emotional_state=EmotionalState.ANXIOUS,
        notes="Entered too early, market broke resistance",
        exit_reason="Stop loss hit",
        exit_timestamp=(datetime.now() - timedelta(days=5, hours=20)).isoformat(),
        hold_duration=14400,  # 4 hours
    )
    trades.append(trade2)

    # Trade 3: Big winning long trade
    trade3 = TradeEntry(
        trade_id=str(uuid.uuid4())[:8],
        timestamp=(datetime.now() - timedelta(days=5)).isoformat(),
        symbol="BTCUSDT",
        direction=TradeDirection.LONG,
        entry_price=61000.0,
        exit_price=66100.0,
        stop_loss_price=60000.0,
        take_profit_price=67000.0,
        position_size=0.15,
        position_value=9150.0,
        leverage=5,
        pnl=765.0,
        pnl_percentage=8.36,
        entry_reason="Breakout + volume surge + all timeframes aligned",
        ma_alignment=True,
        macd_signal="bullish",
        rsi_value=68.0,
        confluence_score=0.92,
        risk_reward_ratio=3.0,
        actual_reward_risk=5.1,
        emotional_state=EmotionalState.CALM,
        notes="High confluence setup, perfect execution",
        exit_reason="Manual exit - trailing stop tightened",
        exit_timestamp=(datetime.now() - timedelta(days=3, hours=8)).isoformat(),
        hold_duration=122400,  # 34 hours
    )
    trades.append(trade3)

    # Trade 4: Break-even trade
    trade4 = TradeEntry(
        trade_id=str(uuid.uuid4())[:8],
        timestamp=(datetime.now() - timedelta(days=3)).isoformat(),
        symbol="BNBUSDT",
        direction=TradeDirection.LONG,
        entry_price=400.0,
        exit_price=400.5,
        stop_loss_price=395.0,
        position_size=15.0,
        position_value=6000.0,
        leverage=3,
        pnl=7.5,
        pnl_percentage=0.125,
        entry_reason="Range support test",
        ma_alignment=False,
        macd_signal="neutral",
        rsi_value=50.0,
        confluence_score=0.35,
        risk_reward_ratio=2.0,
        actual_reward_risk=0.1,
        emotional_state=EmotionalState.CALM,
        notes="Low confidence, moved to break-even quickly",
        exit_reason="Break-even stop hit",
        exit_timestamp=(datetime.now() - timedelta(days=2, hours=18)).isoformat(),
        hold_duration=21600,  # 6 hours
    )
    trades.append(trade4)

    # Trade 5: Another winning trade
    trade5 = TradeEntry(
        trade_id=str(uuid.uuid4())[:8],
        timestamp=(datetime.now() - timedelta(days=2)).isoformat(),
        symbol="SOLUSDT",
        direction=TradeDirection.LONG,
        entry_price=100.0,
        exit_price=105.0,
        stop_loss_price=98.0,
        take_profit_price=106.0,
        position_size=60.0,
        position_value=6000.0,
        leverage=5,
        pnl=300.0,
        pnl_percentage=5.0,
        entry_reason="Cup and handle breakout + bullish engulfing",
        ma_alignment=True,
        macd_signal="bullish",
        rsi_value=62.0,
        confluence_score=0.78,
        risk_reward_ratio=2.5,
        actual_reward_risk=2.5,
        emotional_state=EmotionalState.CONFIDENT,
        notes="Classic pattern, good entry timing",
        exit_reason="Take profit hit",
        exit_timestamp=(datetime.now() - timedelta(days=1, hours=6)).isoformat(),
        hold_duration=64800,  # 18 hours
    )
    trades.append(trade5)

    return trades


def test_trade_journal():
    """Test trade journal functionality"""
    print("=" * 60)
    print("📓 Testing Trade Journal System")
    print("=" * 60)

    # Create journal
    journal_file = "trades/test_journal.json"
    journal = TradeJournal(journal_file=journal_file)

    # Add sample trades
    print("\n📝 Adding Sample Trades...")
    trades = create_sample_trades()
    for i, trade in enumerate(trades, 1):
        journal.add_trade(trade)
        print(f"  ✅ Trade {i} added: {trade.symbol} {trade.direction.value.upper()} "
              f"{trade.pnl:+.2f} USDT")

    # Get performance metrics
    print("\n📊 Calculating Performance Metrics...")
    metrics = journal.get_performance_metrics()

    print("\n" + "=" * 60)
    print("📈 TRADING PERFORMANCE REPORT")
    print("=" * 60)

    print(f"\n🎯 Overall Statistics:")
    print(f"  Total Trades: {metrics.total_trades}")
    print(f"  Winning Trades: {metrics.winning_trades} ({metrics.winning_trades/metrics.total_trades*100:.1f}%)")
    print(f"  Losing Trades: {metrics.losing_trades} ({metrics.losing_trades/metrics.total_trades*100:.1f}%)")
    print(f"  Break-even Trades: {metrics.breakeven_trades}")
    print(f"  Win Rate: {metrics.win_rate:.2f}%")

    print(f"\n💰 Profit/Loss:")
    print(f"  Total P&L: {metrics.total_pnl:+.2f} USDT")
    print(f"  Average Win: {metrics.average_win:.2f} USDT")
    print(f"  Average Loss: {metrics.average_loss:.2f} USDT")
    print(f"  Largest Win: {metrics.largest_win:.2f} USDT")
    print(f"  Largest Loss: {metrics.largest_loss:.2f} USDT")
    print(f"  Profit Factor: {metrics.profit_factor:.2f}")

    print(f"\n⚖️ Risk Metrics:")
    print(f"  Average R:R Ratio: {metrics.average_rr_ratio:.2f}")
    print(f"  Max Drawdown: {metrics.max_drawdown:.2f} USDT")

    print(f"\n🎯 Trade Quality:")
    print(f"  Average Hold Duration: {metrics.average_hold_duration:.1f} hours")
    print(f"  Average Confluence Score: {metrics.average_confluence_score:.2%}")

    # Generate report
    print("\n\n" + "=" * 60)
    print("📄 Generating Full Report...")
    print("=" * 60)

    report = journal.generate_report(output_file="trades/test_report.txt")
    print(report)

    # Show recent trades
    print("\n\n" + "=" * 60)
    print("📋 Recent Trades (Last 3)")
    print("=" * 60)

    recent = journal.get_recent_trades(count=3)
    for trade in recent:
        print(f"\n🔖 {trade.trade_id} - {trade.symbol} {trade.direction.value.upper()}")
        print(f"  Entry: {trade.entry_price:.2f} → Exit: {trade.exit_price:.2f}")
        print(f"  P&L: {trade.pnl:+.2f} USDT ({trade.pnl_percentage:+.2f}%)")
        print(f"  Confluence: {trade.confluence_score:.0%}")
        print(f"  Emotional State: {trade.emotional_state.value}")
        print(f"  Exit Reason: {trade.exit_reason}")

    print("\n\n" + "=" * 60)
    print("✅ Trade Journal Test Completed")
    print(f"📁 Journal saved to: {journal_file}")
    print(f"📄 Report saved to: trades/test_report.txt")
    print("=" * 60)


if __name__ == "__main__":
    test_trade_journal()
