"""Tests for notification formatter."""

from ai_trader.notification.formatter import (
    format_trade_message,
    format_stop_loss_take_profit_message,
    format_decision_message,
    format_backtest_message,
)


class TestFormatTradeMessage:

    def test_format_trade_message_basic(self):
        msg = format_trade_message("BTC/USDT", "open_long", 50000.0, 0.1)
        assert "BTC/USDT" in msg
        assert "50000" in msg
        assert "0.1" in msg
        assert "开多" in msg

    def test_format_trade_message_with_sl_tp(self):
        msg = format_trade_message(
            "ETH/USDT", "open_short", 3000.0, 1.0,
            stop_loss=3100.0, take_profit=2800.0,
        )
        assert "止损: 3100" in msg
        assert "止盈: 2800" in msg

    def test_format_trade_message_unknown_action(self):
        msg = format_trade_message("BTC/USDT", "mystery_action", 100.0, 1.0)
        assert "mystery_action" in msg


class TestFormatStopLossTakeProfit:

    def test_format_stop_loss_message(self):
        msg = format_stop_loss_take_profit_message(
            "BTC/USDT", "long", "stop_loss", 50000.0, 48000.0, -4.0,
        )
        assert "止损" in msg
        assert "BTC/USDT" in msg

    def test_format_take_profit_message(self):
        msg = format_stop_loss_take_profit_message(
            "BTC/USDT", "long", "take_profit", 50000.0, 55000.0, 10.0,
        )
        assert "止盈" in msg

    def test_format_stop_loss_positive_pnl(self):
        msg = format_stop_loss_take_profit_message(
            "BTC/USDT", "short", "stop_loss", 50000.0, 49000.0, 2.0,
        )
        assert "\U0001f7e2" in msg  # green circle

    def test_format_stop_loss_negative_pnl(self):
        msg = format_stop_loss_take_profit_message(
            "BTC/USDT", "long", "stop_loss", 50000.0, 48000.0, -4.0,
        )
        assert "\U0001f534" in msg  # red circle


class TestFormatDecisionMessage:

    def test_format_decision_hold(self):
        msg = format_decision_message("BTC/USDT", "hold", confidence=60.0)
        assert "持仓不动" in msg
        assert "BTC/USDT" in msg
        # hold is a single line
        assert "\n" not in msg.strip() or msg.count("\n") == 0

    def test_format_decision_with_reasoning(self):
        msg = format_decision_message(
            "ETH/USDT", "open_long", confidence=85.0,
            reasoning="Strong uptrend", risk_note="High volatility",
        )
        assert "Strong uptrend" in msg
        assert "High volatility" in msg
        assert "开多" in msg


class TestFormatBacktestMessage:

    def test_format_backtest_positive_return(self):
        msg = format_backtest_message(
            "BTC/USDT", "2024-01-01", "2024-06-01",
            return_pct=15.5, win_rate=55.0, max_drawdown_pct=8.0,
            sharpe_ratio=1.5, total_trades=100,
        )
        assert "\U0001f7e2" in msg
        assert "+15.50%" in msg

    def test_format_backtest_negative_return(self):
        msg = format_backtest_message(
            "BTC/USDT", "2024-01-01", "2024-06-01",
            return_pct=-5.0, win_rate=40.0, max_drawdown_pct=12.0,
            sharpe_ratio=-0.3, total_trades=50,
        )
        assert "\U0001f534" in msg
        assert "-5.00%" in msg
