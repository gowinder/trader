"""策略权重优化器 — 基于历史数据动态调整策略权重"""

import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..persistence.database import DatabaseManager

logger = logging.getLogger(__name__)


class StrategyWeightOptimizer:
    """基于历史回测和实盘数据优化策略权重"""

    MIN_SAMPLES = 20

    def __init__(self, db: "DatabaseManager"):
        self.db = db

    async def compute_optimal_weights(self, market_state: str) -> dict[str, float]:
        """根据特定市场状态下的历史表现计算最优权重

        从 position_history + decisions 联合查询各策略在该市场状态下的表现，
        按胜率和平均盈亏加权计算最优权重。

        Returns:
            策略名 -> 权重 的映射，样本不足时返回空 dict（使用默认权重）
        """
        try:
            rows = await self.db.fetch(
                """
                SELECT
                    d.strategy_signals,
                    ph.realized_pnl,
                    ph.pnl_percent
                FROM position_history ph
                JOIN decisions d ON d.symbol = ph.symbol
                    AND d.created_at BETWEEN ph.entry_time - INTERVAL '5 minutes'
                    AND ph.entry_time + INTERVAL '5 minutes'
                WHERE d.market_state = $1
                  AND ph.status = 'closed'
                  AND ph.realized_pnl IS NOT NULL
                ORDER BY ph.exit_time DESC
                LIMIT 100
                """,
                market_state,
            )
        except Exception as e:
            logger.error(f"Failed to query strategy performance: {e}")
            return {}

        if len(rows) < self.MIN_SAMPLES:
            return {}

        # 统计每个策略的贡献
        strategy_stats: dict[str, dict] = {}  # name -> {wins, total, pnl_sum}
        for row in rows:
            signals = row.get("strategy_signals")
            if not signals:
                continue
            # strategy_signals 格式: JSON dict {strategy_name: {action, confidence}}
            if isinstance(signals, str):
                try:
                    signals = json.loads(signals)
                except (json.JSONDecodeError, TypeError):
                    continue

            pnl = row.get("pnl_percent") or 0
            is_win = (row.get("realized_pnl") or 0) > 0

            for strategy_name in signals:
                if strategy_name not in strategy_stats:
                    strategy_stats[strategy_name] = {"wins": 0, "total": 0, "pnl_sum": 0.0}
                stats = strategy_stats[strategy_name]
                stats["total"] += 1
                if is_win:
                    stats["wins"] += 1
                stats["pnl_sum"] += pnl

        if not strategy_stats:
            return {}

        # 计算每个策略的得分 = 0.6 * win_rate + 0.4 * normalized_avg_pnl
        scores: dict[str, float] = {}
        for name, stats in strategy_stats.items():
            if stats["total"] < 5:
                continue
            win_rate = stats["wins"] / stats["total"]
            avg_pnl = stats["pnl_sum"] / stats["total"]
            # 归一化 avg_pnl 到 [0, 1] 范围（假设 -5% ~ +5%）
            norm_pnl = max(0, min(1, (avg_pnl + 5) / 10))
            scores[name] = 0.6 * win_rate + 0.4 * norm_pnl

        if not scores:
            return {}

        # 归一化为权重
        total_score = sum(scores.values())
        if total_score <= 0:
            return {}

        weights = {name: score / total_score for name, score in scores.items()}
        logger.info(f"Computed optimal weights for {market_state}: {weights}")
        return weights

    async def update_strategy_selector(self, selector) -> int:
        """更新策略选择器的权重映射

        Returns:
            更新的市场状态数量
        """
        updated = 0
        for state in ["strong_trend", "weak_trend", "range_bound", "sideways", "breakout"]:
            weights = await self.compute_optimal_weights(state)
            if weights:
                selector.update_weights(state, weights)
                updated += 1
        return updated
