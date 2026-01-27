"""Backtesting engine for strategy validation"""

from typing import Optional
from datetime import datetime
import pandas as pd
import numpy as np
from pydantic import BaseModel, Field


class BacktestConfig(BaseModel):
    """Backtest configuration"""

    initial_capital: float = Field(default=10000.0, description="Initial capital in USDT")
    commission_rate: float = Field(default=0.0002, description="Commission rate (0.02%)")
    slippage_rate: float = Field(default=0.001, description="Slippage rate (0.1%)")
    max_position_size: float = Field(
        default=1.0, description="Maximum position size (1.0 = 100%)"
    )
    enable_stop_loss: bool = Field(default=True, description="Enable stop loss")
    enable_take_profit: bool = Field(default=True, description="Enable take profit")


class BacktestTrade(BaseModel):
    """Backtest trade record"""

    trade_id: int = Field(..., description="Trade ID")
    timestamp: datetime = Field(..., description="Trade timestamp")
    action: str = Field(..., description="Trade action (open/close)")
    side: str = Field(..., description="Position side (long/short)")
    entry_price: float = Field(..., description="Entry price")
    exit_price: Optional[float] = Field(None, description="Exit price")
    size: float = Field(..., description="Position size")
    stop_loss: Optional[float] = Field(None, description="Stop loss price")
    take_profit: Optional[float] = Field(None, description="Take profit price")
    pnl: Optional[float] = Field(None, description="Realized P&L")
    commission: float = Field(..., description="Commission paid")
    exit_reason: Optional[str] = Field(None, description="Exit reason")


class BacktestResult(BaseModel):
    """Backtest result summary"""

    # Performance metrics
    total_trades: int = Field(..., description="Total number of trades")
    winning_trades: int = Field(..., description="Number of winning trades")
    losing_trades: int = Field(..., description="Number of losing trades")
    win_rate: float = Field(..., description="Win rate (0-1)")

    # P&L metrics
    total_pnl: float = Field(..., description="Total P&L")
    total_commission: float = Field(..., description="Total commission paid")
    net_pnl: float = Field(..., description="Net P&L")
    final_capital: float = Field(..., description="Final capital")
    return_pct: float = Field(..., description="Return percentage")

    # Risk metrics
    max_drawdown: float = Field(..., description="Maximum drawdown")
    max_drawdown_pct: float = Field(..., description="Maximum drawdown percentage")
    sharpe_ratio: float = Field(..., description="Sharpe ratio")
    profit_factor: float = Field(..., description="Profit factor")

    # Trade metrics
    avg_win: float = Field(..., description="Average winning trade")
    avg_loss: float = Field(..., description="Average losing trade")
    avg_win_loss_ratio: float = Field(..., description="Average win/loss ratio")
    largest_win: float = Field(..., description="Largest winning trade")
    largest_loss: float = Field(..., description="Largest losing trade")

    # Execution metrics
    avg_trade_duration: float = Field(..., description="Average trade duration (bars)")
    max_consecutive_wins: int = Field(..., description="Max consecutive wins")
    max_consecutive_losses: int = Field(..., description="Max consecutive losses")


class BacktestEngine:
    """Backtesting engine for strategy validation"""

    def __init__(self, config: BacktestConfig):
        """Initialize backtest engine

        Args:
            config: Backtest configuration
        """
        self.config = config
        self.trades: list[BacktestTrade] = []
        self.equity_curve: list[float] = []
        self.current_position: Optional[dict] = None
        self.capital = config.initial_capital
        self.trade_id_counter = 0

    def run(
        self,
        df: pd.DataFrame,
        signals: pd.DataFrame,
    ) -> BacktestResult:
        """Run backtest on historical data

        Args:
            df: OHLCV data (columns: open, high, low, close, volume, timestamp)
            signals: Trading signals (columns: action, confidence, entry_price, stop_loss, take_profit)

        Returns:
            Backtest result summary
        """
        # Reset state
        self.trades = []
        self.equity_curve = [self.config.initial_capital]
        self.current_position = None
        self.capital = self.config.initial_capital
        self.trade_id_counter = 0

        # Simulate trading
        for i in range(len(df)):
            row = df.iloc[i]
            signal = signals.iloc[i] if i < len(signals) else None

            # Check stop loss / take profit if position open
            if self.current_position:
                exit_result = self._check_exit_triggers(row, self.current_position)
                if exit_result:
                    self._close_position(row, exit_result["reason"])

            # Process signal
            if signal is not None and signal["action"] != "hold":
                if signal["action"] in ["open_long", "open_short"]:
                    if not self.current_position:
                        self._open_position(row, signal)
                elif signal["action"] in ["close_long", "close_short"]:
                    if self.current_position:
                        self._close_position(row, "signal_close")

            # Record equity
            equity = self._calculate_equity(row)
            self.equity_curve.append(equity)

        # Close any remaining position
        if self.current_position:
            final_row = df.iloc[-1]
            self._close_position(final_row, "backtest_end")

        # Calculate metrics
        result = self._calculate_metrics()
        return result

    def _open_position(self, row: pd.Series, signal: pd.Series):
        """Open a new position

        Args:
            row: Current candle data
            signal: Trading signal
        """
        side = "long" if signal["action"] == "open_long" else "short"
        entry_price = row["close"] * (
            1 + self.config.slippage_rate
            if side == "long"
            else 1 - self.config.slippage_rate
        )

        # Calculate position size
        position_value = self.capital * self.config.max_position_size
        size = position_value / entry_price

        # Calculate commission
        commission = position_value * self.config.commission_rate

        # Create trade record
        trade = BacktestTrade(
            trade_id=self.trade_id_counter,
            timestamp=row["timestamp"] if "timestamp" in row else datetime.now(),
            action="open",
            side=side,
            entry_price=entry_price,
            size=size,
            stop_loss=signal.get("stop_loss") if self.config.enable_stop_loss else None,
            take_profit=signal.get("take_profit") if self.config.enable_take_profit else None,
            commission=commission,
        )

        self.current_position = {
            "trade": trade,
            "entry_bar": len(self.equity_curve),
        }
        self.capital -= commission
        self.trade_id_counter += 1

    def _close_position(self, row: pd.Series, reason: str):
        """Close current position

        Args:
            row: Current candle data
            reason: Exit reason
        """
        if not self.current_position:
            return

        trade = self.current_position["trade"]
        side = trade.side

        # Calculate exit price with slippage
        exit_price = row["close"] * (
            1 - self.config.slippage_rate
            if side == "long"
            else 1 + self.config.slippage_rate
        )

        # Calculate P&L
        if side == "long":
            pnl = (exit_price - trade.entry_price) * trade.size
        else:
            pnl = (trade.entry_price - exit_price) * trade.size

        # Calculate commission
        position_value = exit_price * trade.size
        commission = position_value * self.config.commission_rate

        # Update trade record
        trade.exit_price = exit_price
        trade.pnl = pnl
        trade.commission += commission
        trade.exit_reason = reason

        # Update capital
        self.capital += pnl - commission

        # Store trade
        self.trades.append(trade)
        self.current_position = None

    def _check_exit_triggers(
        self, row: pd.Series, position: dict
    ) -> Optional[dict]:
        """Check if stop loss or take profit is triggered

        Args:
            row: Current candle data
            position: Current position info

        Returns:
            Exit info if triggered, None otherwise
        """
        trade = position["trade"]
        side = trade.side
        high = row["high"]
        low = row["low"]

        # Check stop loss
        if trade.stop_loss:
            if side == "long" and low <= trade.stop_loss:
                return {"reason": "stop_loss"}
            elif side == "short" and high >= trade.stop_loss:
                return {"reason": "stop_loss"}

        # Check take profit
        if trade.take_profit:
            if side == "long" and high >= trade.take_profit:
                return {"reason": "take_profit"}
            elif side == "short" and low <= trade.take_profit:
                return {"reason": "take_profit"}

        return None

    def _calculate_equity(self, row: pd.Series) -> float:
        """Calculate current equity

        Args:
            row: Current candle data

        Returns:
            Current equity value
        """
        equity = self.capital

        if self.current_position:
            trade = self.current_position["trade"]
            current_price = row["close"]

            # Calculate unrealized P&L
            if trade.side == "long":
                unrealized_pnl = (current_price - trade.entry_price) * trade.size
            else:
                unrealized_pnl = (trade.entry_price - current_price) * trade.size

            equity += unrealized_pnl

        return equity

    def _calculate_metrics(self) -> BacktestResult:
        """Calculate backtest performance metrics

        Returns:
            Backtest result summary
        """
        if not self.trades:
            return BacktestResult(
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=0.0,
                total_pnl=0.0,
                total_commission=0.0,
                net_pnl=0.0,
                final_capital=self.config.initial_capital,
                return_pct=0.0,
                max_drawdown=0.0,
                max_drawdown_pct=0.0,
                sharpe_ratio=0.0,
                profit_factor=0.0,
                avg_win=0.0,
                avg_loss=0.0,
                avg_win_loss_ratio=0.0,
                largest_win=0.0,
                largest_loss=0.0,
                avg_trade_duration=0.0,
                max_consecutive_wins=0,
                max_consecutive_losses=0,
            )

        # Basic metrics
        total_trades = len(self.trades)
        winning_trades = sum(1 for t in self.trades if t.pnl > 0)
        losing_trades = sum(1 for t in self.trades if t.pnl <= 0)
        win_rate = winning_trades / total_trades if total_trades > 0 else 0.0

        # P&L metrics
        total_pnl = sum(t.pnl for t in self.trades)
        total_commission = sum(t.commission for t in self.trades)
        net_pnl = total_pnl - total_commission
        final_capital = self.capital
        return_pct = (
            (final_capital - self.config.initial_capital) / self.config.initial_capital * 100
        )

        # Win/loss metrics
        wins = [t.pnl for t in self.trades if t.pnl > 0]
        losses = [t.pnl for t in self.trades if t.pnl <= 0]

        avg_win = sum(wins) / len(wins) if wins else 0.0
        avg_loss = sum(losses) / len(losses) if losses else 0.0
        avg_win_loss_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 0.0

        largest_win = max(wins) if wins else 0.0
        largest_loss = min(losses) if losses else 0.0

        # Profit factor
        total_wins = sum(wins) if wins else 0.0
        total_losses = abs(sum(losses)) if losses else 0.0
        profit_factor = total_wins / total_losses if total_losses > 0 else 0.0

        # Drawdown metrics
        equity_curve = np.array(self.equity_curve)
        running_max = np.maximum.accumulate(equity_curve)
        drawdown = running_max - equity_curve
        max_drawdown = float(drawdown.max())
        max_drawdown_pct = (
            (max_drawdown / running_max[drawdown.argmax()] * 100)
            if running_max[drawdown.argmax()] > 0
            else 0.0
        )

        # Sharpe ratio (simplified: using daily returns)
        if len(equity_curve) > 1:
            returns = np.diff(equity_curve) / equity_curve[:-1]
            sharpe_ratio = (
                (returns.mean() / returns.std() * np.sqrt(252))
                if returns.std() > 0
                else 0.0
            )
        else:
            sharpe_ratio = 0.0

        # Consecutive wins/losses
        max_consecutive_wins = 0
        max_consecutive_losses = 0
        current_wins = 0
        current_losses = 0

        for trade in self.trades:
            if trade.pnl > 0:
                current_wins += 1
                current_losses = 0
                max_consecutive_wins = max(max_consecutive_wins, current_wins)
            else:
                current_losses += 1
                current_wins = 0
                max_consecutive_losses = max(max_consecutive_losses, current_losses)

        # Average trade duration (placeholder - needs entry/exit bar tracking)
        avg_trade_duration = 0.0

        return BacktestResult(
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            total_pnl=total_pnl,
            total_commission=total_commission,
            net_pnl=net_pnl,
            final_capital=final_capital,
            return_pct=return_pct,
            max_drawdown=max_drawdown,
            max_drawdown_pct=max_drawdown_pct,
            sharpe_ratio=sharpe_ratio,
            profit_factor=profit_factor,
            avg_win=avg_win,
            avg_loss=avg_loss,
            avg_win_loss_ratio=avg_win_loss_ratio,
            largest_win=largest_win,
            largest_loss=largest_loss,
            avg_trade_duration=avg_trade_duration,
            max_consecutive_wins=max_consecutive_wins,
            max_consecutive_losses=max_consecutive_losses,
        )

    def generate_report(self, result: BacktestResult) -> str:
        """Generate backtest report

        Args:
            result: Backtest result

        Returns:
            Formatted report string
        """
        report = f"""
========================================
           BACKTEST REPORT
========================================

PERFORMANCE SUMMARY
-------------------
Total Trades:         {result.total_trades}
Winning Trades:       {result.winning_trades}
Losing Trades:        {result.losing_trades}
Win Rate:             {result.win_rate:.2%}

P&L METRICS
-----------
Initial Capital:      ${self.config.initial_capital:,.2f}
Final Capital:        ${result.final_capital:,.2f}
Total P&L:            ${result.total_pnl:,.2f}
Total Commission:     ${result.total_commission:,.2f}
Net P&L:              ${result.net_pnl:,.2f}
Return:               {result.return_pct:+.2f}%

RISK METRICS
------------
Max Drawdown:         ${result.max_drawdown:,.2f} ({result.max_drawdown_pct:.2f}%)
Sharpe Ratio:         {result.sharpe_ratio:.2f}
Profit Factor:        {result.profit_factor:.2f}

TRADE METRICS
-------------
Average Win:          ${result.avg_win:,.2f}
Average Loss:         ${result.avg_loss:,.2f}
Win/Loss Ratio:       {result.avg_win_loss_ratio:.2f}
Largest Win:          ${result.largest_win:,.2f}
Largest Loss:         ${result.largest_loss:,.2f}

STREAK METRICS
--------------
Max Consecutive Wins:   {result.max_consecutive_wins}
Max Consecutive Losses: {result.max_consecutive_losses}

========================================
"""
        return report
