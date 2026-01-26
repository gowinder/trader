"""Trading journal system for tracking, analyzing, and improving trading performance"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
import json
from pathlib import Path
from ..utils.logger import logger


class TradeDirection(str, Enum):
    """Trade direction"""

    LONG = "long"
    SHORT = "short"


class TradeOutcome(str, Enum):
    """Trade outcome classification"""

    WIN = "win"
    LOSS = "loss"
    BREAKEVEN = "breakeven"


class EmotionalState(str, Enum):
    """Trader's emotional state during trade"""

    CALM = "calm"
    CONFIDENT = "confident"
    ANXIOUS = "anxious"
    GREEDY = "greedy"
    FEARFUL = "fearful"
    FOMO = "fomo"  # Fear of missing out
    REVENGE = "revenge"  # Revenge trading after loss


@dataclass
class TradeEntry:
    """Single trade journal entry"""

    # Basic Information
    trade_id: str
    timestamp: str  # ISO format
    symbol: str
    direction: TradeDirection

    # Entry/Exit Prices
    entry_price: float
    exit_price: Optional[float] = None
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None

    # Position Information
    position_size: float  # In base currency (e.g., BTC)
    position_value: float  # In quote currency (e.g., USDT)
    leverage: int = 1

    # Performance Metrics
    pnl: Optional[float] = None  # Profit/Loss in USDT
    pnl_percentage: Optional[float] = None  # P&L as percentage of position value
    outcome: Optional[TradeOutcome] = None
    hold_duration: Optional[int] = None  # In seconds

    # Technical Analysis
    entry_reason: str = ""  # Why entered (indicators, patterns, multi-timeframe signals)
    timeframe_analysis: Dict[str, Any] = None  # Multi-timeframe data at entry
    ma_alignment: Optional[bool] = None
    macd_signal: Optional[str] = None
    rsi_value: Optional[float] = None
    confluence_score: Optional[float] = None  # Multi-timeframe alignment score

    # Risk Management
    risk_reward_ratio: Optional[float] = None  # Expected R:R at entry
    actual_reward_risk: Optional[float] = None  # Actual R:R at exit
    max_adverse_excursion: Optional[float] = None  # Worst price during trade
    max_favorable_excursion: Optional[float] = None  # Best price during trade

    # Psychology
    emotional_state: EmotionalState = EmotionalState.CALM
    notes: str = ""  # Free-form notes

    # Exit Information
    exit_reason: str = ""  # Why exited (target hit, stop hit, manual, signal reversal)
    exit_timestamp: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization"""
        data = asdict(self)
        # Convert enums to strings
        data["direction"] = self.direction.value
        data["emotional_state"] = self.emotional_state.value
        if self.outcome:
            data["outcome"] = self.outcome.value
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "TradeEntry":
        """Create TradeEntry from dictionary"""
        # Convert string enums back
        if "direction" in data:
            data["direction"] = TradeDirection(data["direction"])
        if "emotional_state" in data:
            data["emotional_state"] = EmotionalState(data["emotional_state"])
        if "outcome" in data and data["outcome"]:
            data["outcome"] = TradeOutcome(data["outcome"])

        return cls(**data)


@dataclass
class PerformanceMetrics:
    """Trading performance metrics"""

    # Overall Statistics
    total_trades: int
    winning_trades: int
    losing_trades: int
    breakeven_trades: int
    win_rate: float  # Percentage of winning trades

    # Profit/Loss
    total_pnl: float
    average_win: float
    average_loss: float
    largest_win: float
    largest_loss: float
    profit_factor: float  # Gross profit / Gross loss

    # Risk Metrics
    average_rr_ratio: float  # Average reward/risk ratio
    max_drawdown: float  # Maximum peak-to-trough decline
    sharpe_ratio: Optional[float] = None  # Risk-adjusted return

    # Trade Quality
    average_hold_duration: float  # In hours
    average_confluence_score: float  # Multi-timeframe alignment quality

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return asdict(self)


class TradeJournal:
    """Trading journal for systematic trade tracking and performance analysis"""

    def __init__(self, journal_file: Optional[str] = None):
        """Initialize trade journal

        Args:
            journal_file: Path to JSON file for persisting trades (default: trades/journal.json)
        """
        if journal_file is None:
            journal_file = "trades/journal.json"

        self.journal_file = Path(journal_file)
        self.journal_file.parent.mkdir(parents=True, exist_ok=True)

        self.trades: List[TradeEntry] = []
        self._load_journal()

    def _load_journal(self):
        """Load existing trades from journal file"""
        if self.journal_file.exists():
            try:
                with open(self.journal_file, "r") as f:
                    data = json.load(f)
                    self.trades = [TradeEntry.from_dict(t) for t in data]
                logger.info(f"Loaded {len(self.trades)} trades from journal")
            except Exception as e:
                logger.error(f"Failed to load journal: {e}")
                self.trades = []
        else:
            logger.info("No existing journal found, starting fresh")

    def _save_journal(self):
        """Persist trades to journal file"""
        try:
            with open(self.journal_file, "w") as f:
                data = [t.to_dict() for t in self.trades]
                json.dump(data, f, indent=2, default=str)
            logger.info(f"Saved {len(self.trades)} trades to journal")
        except Exception as e:
            logger.error(f"Failed to save journal: {e}")

    def add_trade(self, trade: TradeEntry):
        """Add new trade entry to journal

        Args:
            trade: TradeEntry object
        """
        self.trades.append(trade)
        self._save_journal()
        logger.info(f"Added trade {trade.trade_id} to journal")

    def update_trade(self, trade_id: str, **kwargs):
        """Update existing trade entry

        Args:
            trade_id: ID of trade to update
            **kwargs: Fields to update (e.g., exit_price=65000, pnl=500)
        """
        for trade in self.trades:
            if trade.trade_id == trade_id:
                for key, value in kwargs.items():
                    if hasattr(trade, key):
                        setattr(trade, key, value)
                    else:
                        logger.warning(f"Unknown field: {key}")

                # Recalculate outcome if exit_price provided
                if "exit_price" in kwargs and trade.exit_price:
                    self._calculate_outcome(trade)

                self._save_journal()
                logger.info(f"Updated trade {trade_id}")
                return

        logger.warning(f"Trade {trade_id} not found in journal")

    def _calculate_outcome(self, trade: TradeEntry):
        """Calculate trade outcome (win/loss/breakeven) based on P&L"""
        if trade.pnl is None or trade.pnl == 0:
            trade.outcome = TradeOutcome.BREAKEVEN
        elif trade.pnl > 0:
            trade.outcome = TradeOutcome.WIN
        else:
            trade.outcome = TradeOutcome.LOSS

    def close_trade(
        self,
        trade_id: str,
        exit_price: float,
        exit_reason: str,
        exit_timestamp: Optional[str] = None,
    ):
        """Close a trade and calculate final metrics

        Args:
            trade_id: ID of trade to close
            exit_price: Exit price
            exit_reason: Reason for exit (e.g., "Take profit hit", "Stop loss hit")
            exit_timestamp: Exit timestamp (default: now)
        """
        for trade in self.trades:
            if trade.trade_id == trade_id:
                if exit_timestamp is None:
                    exit_timestamp = datetime.now().isoformat()

                trade.exit_price = exit_price
                trade.exit_reason = exit_reason
                trade.exit_timestamp = exit_timestamp

                # Calculate P&L
                if trade.direction == TradeDirection.LONG:
                    pnl = (exit_price - trade.entry_price) * trade.position_size
                else:  # SHORT
                    pnl = (trade.entry_price - exit_price) * trade.position_size

                trade.pnl = pnl
                trade.pnl_percentage = (pnl / trade.position_value) * 100

                # Calculate actual reward/risk ratio
                if trade.stop_loss_price:
                    risk = abs(trade.entry_price - trade.stop_loss_price) * trade.position_size
                    if risk > 0:
                        trade.actual_reward_risk = abs(pnl / risk)

                # Calculate hold duration
                entry_dt = datetime.fromisoformat(trade.timestamp)
                exit_dt = datetime.fromisoformat(exit_timestamp)
                trade.hold_duration = int((exit_dt - entry_dt).total_seconds())

                # Determine outcome
                self._calculate_outcome(trade)

                self._save_journal()
                logger.info(
                    f"Closed trade {trade_id}: {trade.outcome.value}, "
                    f"P&L: {pnl:.2f} USDT ({trade.pnl_percentage:.2f}%)"
                )
                return

        logger.warning(f"Trade {trade_id} not found in journal")

    def get_performance_metrics(
        self, start_date: Optional[str] = None, end_date: Optional[str] = None
    ) -> PerformanceMetrics:
        """Calculate performance metrics for a date range

        Args:
            start_date: Start date (ISO format, default: all time)
            end_date: End date (ISO format, default: now)

        Returns:
            PerformanceMetrics object
        """
        # Filter trades by date range
        filtered_trades = self.trades

        if start_date:
            filtered_trades = [
                t for t in filtered_trades if t.timestamp >= start_date
            ]
        if end_date:
            filtered_trades = [t for t in filtered_trades if t.timestamp <= end_date]

        # Filter only closed trades
        closed_trades = [t for t in filtered_trades if t.exit_price is not None]

        if not closed_trades:
            logger.warning("No closed trades found for performance calculation")
            return self._empty_metrics()

        # Basic counts
        total_trades = len(closed_trades)
        winning_trades = sum(1 for t in closed_trades if t.outcome == TradeOutcome.WIN)
        losing_trades = sum(1 for t in closed_trades if t.outcome == TradeOutcome.LOSS)
        breakeven_trades = sum(
            1 for t in closed_trades if t.outcome == TradeOutcome.BREAKEVEN
        )

        # Win rate
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

        # P&L statistics
        pnls = [t.pnl for t in closed_trades if t.pnl is not None]
        total_pnl = sum(pnls)

        wins = [pnl for pnl in pnls if pnl > 0]
        losses = [pnl for pnl in pnls if pnl < 0]

        average_win = sum(wins) / len(wins) if wins else 0
        average_loss = sum(losses) / len(losses) if losses else 0
        largest_win = max(wins) if wins else 0
        largest_loss = min(losses) if losses else 0

        # Profit factor
        gross_profit = sum(wins) if wins else 0
        gross_loss = abs(sum(losses)) if losses else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

        # Risk/Reward ratios
        rr_ratios = [
            t.actual_reward_risk
            for t in closed_trades
            if t.actual_reward_risk is not None
        ]
        average_rr_ratio = sum(rr_ratios) / len(rr_ratios) if rr_ratios else 0

        # Max drawdown (simplified: cumulative P&L peak-to-trough)
        max_drawdown = self._calculate_max_drawdown(closed_trades)

        # Average hold duration
        durations = [
            t.hold_duration for t in closed_trades if t.hold_duration is not None
        ]
        average_hold_duration = (
            (sum(durations) / len(durations) / 3600) if durations else 0
        )  # Convert to hours

        # Average confluence score
        confluence_scores = [
            t.confluence_score
            for t in closed_trades
            if t.confluence_score is not None
        ]
        average_confluence = (
            sum(confluence_scores) / len(confluence_scores) if confluence_scores else 0
        )

        return PerformanceMetrics(
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            breakeven_trades=breakeven_trades,
            win_rate=win_rate,
            total_pnl=total_pnl,
            average_win=average_win,
            average_loss=average_loss,
            largest_win=largest_win,
            largest_loss=largest_loss,
            profit_factor=profit_factor,
            average_rr_ratio=average_rr_ratio,
            max_drawdown=max_drawdown,
            average_hold_duration=average_hold_duration,
            average_confluence_score=average_confluence,
        )

    def _calculate_max_drawdown(self, trades: List[TradeEntry]) -> float:
        """Calculate maximum drawdown from peak

        Drawdown = (Trough - Peak) / Peak
        """
        if not trades:
            return 0

        cumulative_pnl = []
        running_total = 0
        for trade in sorted(trades, key=lambda t: t.timestamp):
            if trade.pnl is not None:
                running_total += trade.pnl
                cumulative_pnl.append(running_total)

        if not cumulative_pnl:
            return 0

        max_drawdown = 0
        peak = cumulative_pnl[0]

        for value in cumulative_pnl:
            if value > peak:
                peak = value

            drawdown = peak - value
            if drawdown > max_drawdown:
                max_drawdown = drawdown

        return max_drawdown

    def _empty_metrics(self) -> PerformanceMetrics:
        """Return empty metrics when no trades available"""
        return PerformanceMetrics(
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            breakeven_trades=0,
            win_rate=0,
            total_pnl=0,
            average_win=0,
            average_loss=0,
            largest_win=0,
            largest_loss=0,
            profit_factor=0,
            average_rr_ratio=0,
            max_drawdown=0,
            average_hold_duration=0,
            average_confluence_score=0,
        )

    def get_recent_trades(self, count: int = 10) -> List[TradeEntry]:
        """Get most recent N trades

        Args:
            count: Number of recent trades to return

        Returns:
            List of recent TradeEntry objects
        """
        sorted_trades = sorted(self.trades, key=lambda t: t.timestamp, reverse=True)
        return sorted_trades[:count]

    def get_trade_by_id(self, trade_id: str) -> Optional[TradeEntry]:
        """Get trade by ID

        Args:
            trade_id: Trade ID to search for

        Returns:
            TradeEntry or None if not found
        """
        for trade in self.trades:
            if trade.trade_id == trade_id:
                return trade
        return None

    def generate_report(self, output_file: Optional[str] = None) -> str:
        """Generate human-readable performance report

        Args:
            output_file: Path to save report (default: trades/report.txt)

        Returns:
            Report text
        """
        metrics = self.get_performance_metrics()

        report_lines = [
            "=" * 60,
            "TRADING PERFORMANCE REPORT",
            "=" * 60,
            "",
            "📊 Overall Statistics",
            f"  Total Trades: {metrics.total_trades}",
            f"  Winning Trades: {metrics.winning_trades}",
            f"  Losing Trades: {metrics.losing_trades}",
            f"  Breakeven Trades: {metrics.breakeven_trades}",
            f"  Win Rate: {metrics.win_rate:.2f}%",
            "",
            "💰 Profit/Loss",
            f"  Total P&L: {metrics.total_pnl:+.2f} USDT",
            f"  Average Win: {metrics.average_win:.2f} USDT",
            f"  Average Loss: {metrics.average_loss:.2f} USDT",
            f"  Largest Win: {metrics.largest_win:.2f} USDT",
            f"  Largest Loss: {metrics.largest_loss:.2f} USDT",
            f"  Profit Factor: {metrics.profit_factor:.2f}",
            "",
            "⚖️ Risk Metrics",
            f"  Average R:R Ratio: {metrics.average_rr_ratio:.2f}",
            f"  Max Drawdown: {metrics.max_drawdown:.2f} USDT",
            "",
            "🎯 Trade Quality",
            f"  Average Hold Duration: {metrics.average_hold_duration:.2f} hours",
            f"  Average Confluence Score: {metrics.average_confluence_score:.2f}",
            "",
            "=" * 60,
        ]

        report = "\n".join(report_lines)

        # Save to file if requested
        if output_file:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w") as f:
                f.write(report)
            logger.info(f"Report saved to {output_file}")

        return report
