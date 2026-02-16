"""性能基线追踪 — 周期性评估系统表现并检测退化"""

import json
import logging
import math
from datetime import datetime
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..persistence.database import DatabaseManager

logger = logging.getLogger(__name__)


class PerformanceTracker:
    """周期性计算系统表现基线"""

    def __init__(self, db: "DatabaseManager"):
        self.db = db

    async def compute_weekly_report(self) -> dict:
        """计算本周表现

        Returns:
            周报字典，包含 win_rate, avg_pnl, sharpe_ratio, max_drawdown 等
        """
        try:
            rows = await self.db.fetch(
                """
                SELECT realized_pnl, pnl_percent
                FROM position_history
                WHERE status = 'closed'
                  AND realized_pnl IS NOT NULL
                  AND exit_time > NOW() - INTERVAL '7 days'
                ORDER BY exit_time ASC
                """
            )
        except Exception as e:
            logger.error(f"Failed to query weekly trades: {e}")
            return self._empty_report()

        if not rows:
            return self._empty_report()

        pnl_list = [float(r.get("pnl_percent") or 0) for r in rows]
        wins = sum(1 for p in pnl_list if p > 0)
        total = len(pnl_list)
        win_rate = wins / total if total > 0 else 0
        avg_pnl = sum(pnl_list) / total if total > 0 else 0

        # 夏普比率 (简化版: avg / std，假设无风险利率为 0)
        if total >= 2:
            mean = avg_pnl
            variance = sum((p - mean) ** 2 for p in pnl_list) / (total - 1)
            std = math.sqrt(variance) if variance > 0 else 0
            sharpe = mean / std if std > 0 else 0
        else:
            sharpe = 0

        # 最大回撤
        peak = 0.0
        equity = 0.0
        max_dd = 0.0
        for p in pnl_list:
            equity += p
            peak = max(peak, equity)
            dd = peak - equity
            max_dd = max(max_dd, dd)

        return {
            "period": "weekly",
            "computed_at": datetime.now().isoformat(),
            "total_trades": total,
            "win_rate": round(win_rate, 4),
            "avg_pnl": round(avg_pnl, 4),
            "total_pnl": round(sum(pnl_list), 4),
            "sharpe_ratio": round(sharpe, 4),
            "max_drawdown_pct": round(max_dd, 4),
        }

    async def detect_degradation(self) -> Optional[str]:
        """检测表现退化

        与上一份周报对比。

        Returns:
            退化描述字符串，无退化返回 None
        """
        current = await self.compute_weekly_report()
        previous = await self._get_previous_report()

        if not previous or current["total_trades"] < 5:
            return None

        prev_wr = previous.get("win_rate", 0)
        prev_pnl = previous.get("avg_pnl", 0)

        if current["win_rate"] < prev_wr - 0.1:
            return (
                f"胜率下降: {prev_wr:.0%} → {current['win_rate']:.0%}"
            )
        if current["avg_pnl"] < prev_pnl - 1.0:
            return (
                f"平均盈亏下降: {prev_pnl:+.2f}% → {current['avg_pnl']:+.2f}%"
            )
        return None

    async def save_report(self, report: dict) -> None:
        """保存周报到数据库"""
        try:
            await self.db.execute(
                """
                INSERT INTO performance_reports (
                    period, computed_at, total_trades, win_rate,
                    avg_pnl, total_pnl, sharpe_ratio, max_drawdown_pct, raw_data
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                report.get("period", "weekly"),
                datetime.now(),
                report.get("total_trades", 0),
                report.get("win_rate", 0),
                report.get("avg_pnl", 0),
                report.get("total_pnl", 0),
                report.get("sharpe_ratio", 0),
                report.get("max_drawdown_pct", 0),
                json.dumps(report, ensure_ascii=False),
            )
        except Exception as e:
            logger.error(f"Failed to save performance report: {e}")

    async def _get_previous_report(self) -> Optional[dict]:
        """获取上一份周报"""
        try:
            row = await self.db.fetchrow(
                """
                SELECT raw_data
                FROM performance_reports
                WHERE period = 'weekly'
                ORDER BY computed_at DESC
                LIMIT 1
                """
            )
            if row and row.get("raw_data"):
                data = row["raw_data"]
                if isinstance(data, str):
                    return json.loads(data)
                return dict(data)
        except Exception:
            pass
        return None

    @staticmethod
    def _empty_report() -> dict:
        return {
            "period": "weekly",
            "computed_at": datetime.now().isoformat(),
            "total_trades": 0,
            "win_rate": 0,
            "avg_pnl": 0,
            "total_pnl": 0,
            "sharpe_ratio": 0,
            "max_drawdown_pct": 0,
        }
