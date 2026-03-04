"""Prompt 上下文增强器 — 动态注入历史表现和已验证规则"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..persistence.database import DatabaseManager

logger = logging.getLogger(__name__)


class PromptContextEnricher:
    """动态丰富 AI 决策 prompt 上下文"""

    def __init__(self, db: "DatabaseManager"):
        self.db = db

    async def get_performance_summary(self, symbol: str, limit: int = 20) -> str:
        """获取近期表现摘要"""
        try:
            rows = await self.db.fetch(
                """
                SELECT side, realized_pnl, pnl_percent
                FROM position_history
                WHERE symbol = $1
                  AND status = 'closed'
                  AND realized_pnl IS NOT NULL
                ORDER BY exit_time DESC
                LIMIT $2
                """,
                symbol,
                limit,
            )
        except Exception as e:
            logger.error(f"Failed to fetch performance data: {e}")
            return "Performance data unavailable"

        if not rows:
            return "No recent closed trades"

        total = len(rows)
        wins = sum(1 for r in rows if (r["realized_pnl"] or 0) > 0)
        losses = total - wins
        win_rate = wins / total if total > 0 else 0
        avg_pnl_pct = sum((r["pnl_percent"] or 0) for r in rows) / total

        # 按方向统计
        long_trades = [r for r in rows if r["side"] == "long"]
        short_trades = [r for r in rows if r["side"] == "short"]
        long_wr = (
            sum(1 for r in long_trades if (r["realized_pnl"] or 0) > 0) / len(long_trades)
            if long_trades
            else 0
        )
        short_wr = (
            sum(1 for r in short_trades if (r["realized_pnl"] or 0) > 0) / len(short_trades)
            if short_trades
            else 0
        )

        # 连续亏损检测
        consecutive_losses = 0
        for r in rows:
            if (r["realized_pnl"] or 0) < 0:
                consecutive_losses += 1
            else:
                break

        loss_pattern = ""
        if consecutive_losses >= 3:
            loss_pattern = (
                f"\n⚠️ WARNING: {consecutive_losses} consecutive losses detected. "
                "Consider reducing position size or waiting for better setups."
            )

        return (
            f"Last {total} trades: {wins}W/{losses}L (win rate: {win_rate:.0%})\n"
            f"Average PnL per trade: {avg_pnl_pct:+.2f}%\n"
            f"Long win rate: {long_wr:.0%} ({len(long_trades)} trades), "
            f"Short win rate: {short_wr:.0%} ({len(short_trades)} trades)"
            f"{loss_pattern}"
        )

    async def get_recent_stats(self, symbol: str, hours: int = 24) -> dict:
        """Get recent trading stats for risk assessment and decision context."""
        try:
            rows = await self.db.fetch(
                """
                SELECT realized_pnl
                FROM position_history
                WHERE symbol = $1
                  AND status = 'closed'
                  AND exit_time >= NOW() - INTERVAL '1 hour' * $2
                ORDER BY exit_time DESC
                """,
                symbol,
                hours,
            )
        except Exception as e:
            logger.warning(f"Failed to fetch recent stats: {e}")
            return {"trade_count": 0, "total_pnl": 0.0, "win_rate": 0.0}

        if not rows:
            return {"trade_count": 0, "total_pnl": 0.0, "win_rate": 0.0}

        trade_count = len(rows)
        total_pnl = sum(float(r["realized_pnl"] or 0) for r in rows)
        wins = sum(1 for r in rows if (r["realized_pnl"] or 0) > 0)
        win_rate = wins / trade_count if trade_count > 0 else 0.0

        return {"trade_count": trade_count, "total_pnl": total_pnl, "win_rate": win_rate}

    async def get_enhanced_performance_summary(
        self,
        symbol: str,
        limit: int = 20,
        current_position: dict | None = None,
        daily_pnl: float = 0.0,
    ) -> str:
        """Get enhanced performance summary with current position and daily PnL context."""
        base = await self.get_performance_summary(symbol, limit)

        extra_lines = []
        if daily_pnl != 0.0:
            extra_lines.append(f"Today's PnL: {daily_pnl:+.2f} USDT")
        if current_position:
            side = current_position.get("side", "unknown")
            upnl = current_position.get("unrealized_pnl", 0)
            extra_lines.append(f"Current position: {side}, unrealized PnL: {upnl:+.2f} USDT")

        if extra_lines:
            return base + "\n" + "\n".join(extra_lines)
        return base

    async def get_active_rules(self) -> str:
        """获取已验证生效的规则"""
        try:
            rows = await self.db.fetch(
                """
                SELECT condition, recommendation, win_rate, sample_size
                FROM distilled_rules
                WHERE status = 'active'
                ORDER BY win_rate DESC
                LIMIT 5
                """,
            )
        except Exception as e:
            logger.debug(f"distilled_rules table not available: {e}")
            return "No validated rules yet"

        if not rows:
            return "No validated rules yet"

        lines = []
        for r in rows:
            lines.append(
                f"- When {r['condition']}: {r['recommendation']} "
                f"(win rate: {r['win_rate']:.0%}, samples: {r['sample_size']})"
            )
        return "\n".join(lines)
