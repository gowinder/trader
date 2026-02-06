# src/ai_trader/optimization/shadow_runner.py
"""影子运行器 - 参数验证"""

import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import uuid4
from dataclasses import dataclass

if TYPE_CHECKING:
    from ..persistence.database import DatabaseManager

logger = logging.getLogger(__name__)


@dataclass
class ShadowStats:
    """影子运行统计"""
    trades: int = 0
    wins: int = 0
    total_pnl: float = 0.0

    @property
    def win_rate(self) -> float:
        return self.wins / self.trades if self.trades > 0 else 0.0

    @property
    def avg_pnl(self) -> float:
        return self.total_pnl / self.trades if self.trades > 0 else 0.0


class ShadowRunner:
    """影子运行器"""

    MIN_TRADES = 10
    WIN_RATE_THRESHOLD = 0.03
    PNL_THRESHOLD = 0.005

    def __init__(self, db: "DatabaseManager"):
        self.db = db
        self._run_id: Optional[str] = None
        self._current_params: dict = {}
        self._candidate_params: dict = {}
        self._current_stats = ShadowStats()
        self._candidate_stats = ShadowStats()
        self._started_at: Optional[datetime] = None

    @property
    def is_running(self) -> bool:
        return self._run_id is not None

    async def start(self, current_params: dict, candidate_params: dict) -> str:
        """启动影子运行

        Args:
            current_params: 当前参数
            candidate_params: 候选参数

        Returns:
            运行 ID
        """
        self._run_id = f"shadow_{uuid4().hex[:8]}"
        self._current_params = current_params
        self._candidate_params = candidate_params
        self._current_stats = ShadowStats()
        self._candidate_stats = ShadowStats()
        self._started_at = datetime.now()

        await self.db.execute(
            """
            INSERT INTO shadow_runs (
                run_id, started_at, current_params, candidate_params, status
            ) VALUES ($1, $2, $3, $4, 'running')
            """,
            self._run_id,
            self._started_at,
            json.dumps(current_params),
            json.dumps(candidate_params),
        )

        logger.info(f"影子运行启动: {self._run_id}")
        return self._run_id

    def record_current_result(self, is_winner: bool, pnl: float) -> None:
        """记录实盘结果"""
        self._current_stats.trades += 1
        if is_winner:
            self._current_stats.wins += 1
        self._current_stats.total_pnl += pnl

    def record_candidate_result(self, is_winner: bool, pnl: float) -> None:
        """记录影子（候选参数）结果"""
        self._candidate_stats.trades += 1
        if is_winner:
            self._candidate_stats.wins += 1
        self._candidate_stats.total_pnl += pnl

    def get_stats(self) -> dict:
        """获取当前统计"""
        return {
            "current_trades": self._current_stats.trades,
            "current_win_rate": self._current_stats.win_rate,
            "current_avg_pnl": self._current_stats.avg_pnl,
            "candidate_trades": self._candidate_stats.trades,
            "candidate_win_rate": self._candidate_stats.win_rate,
            "candidate_avg_pnl": self._candidate_stats.avg_pnl,
        }

    def evaluate(self) -> dict:
        """评估是否应该切换参数"""
        if self._candidate_stats.trades < self.MIN_TRADES:
            return {
                "should_switch": False,
                "reason": f"样本不足: {self._candidate_stats.trades}/{self.MIN_TRADES}",
            }

        win_rate_improvement = (
            self._candidate_stats.win_rate - self._current_stats.win_rate
        )
        pnl_improvement = (
            self._candidate_stats.avg_pnl - self._current_stats.avg_pnl
        )

        should_switch = (
            win_rate_improvement >= self.WIN_RATE_THRESHOLD
            and pnl_improvement >= self.PNL_THRESHOLD
        )

        return {
            "should_switch": should_switch,
            "win_rate_improvement": win_rate_improvement,
            "pnl_improvement": pnl_improvement,
            "stats": self.get_stats(),
        }

    async def complete(self, switched: bool, conclusion: str = "") -> None:
        """完成影子运行"""
        if not self._run_id:
            return

        stats = self.get_stats()

        await self.db.execute(
            """
            UPDATE shadow_runs SET
                ended_at = $1,
                current_trades = $2,
                candidate_trades = $3,
                current_win_rate = $4,
                candidate_win_rate = $5,
                current_avg_pnl = $6,
                candidate_avg_pnl = $7,
                status = $8,
                conclusion = $9
            WHERE run_id = $10
            """,
            datetime.now(),
            stats["current_trades"],
            stats["candidate_trades"],
            stats["current_win_rate"],
            stats["candidate_win_rate"],
            stats["current_avg_pnl"],
            stats["candidate_avg_pnl"],
            "switched" if switched else "rejected",
            conclusion,
            self._run_id,
        )

        logger.info(f"影子运行完成: {self._run_id}, switched={switched}")
        self._run_id = None
