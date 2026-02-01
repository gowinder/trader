# src/ai_trader/optimization/rule_validator.py
"""规则统计验证器"""

import logging
from typing import Optional

from ..memory.models import TradeMemoryEntry, DistilledRule

logger = logging.getLogger(__name__)


class RuleValidator:
    """候选规则的统计验证器"""

    MIN_SAMPLE_SIZE = 20
    P_VALUE_THRESHOLD = 0.05
    MIN_WIN_RATE_IMPROVEMENT = 0.05

    def validate(
        self,
        rule: dict,
        history: list[TradeMemoryEntry],
    ) -> dict:
        """验证候选规则

        Args:
            rule: 候选规则（包含 condition 和 recommendation）
            history: 历史交易记录

        Returns:
            验证结果
        """
        condition = rule.get("condition", {})

        # 筛选符合条件的交易
        matched = [t for t in history if self._match_condition(t, condition)]

        if len(matched) < self.MIN_SAMPLE_SIZE:
            return {
                "is_valid": False,
                "reason": f"样本不足: {len(matched)}/{self.MIN_SAMPLE_SIZE}",
                "sample_size": len(matched),
            }

        # 计算胜率
        winners = [t for t in matched if t.is_winner]
        win_rate = len(winners) / len(matched)

        # 计算平均盈亏
        pnls = [t.pnl_percent for t in matched if t.pnl_percent is not None]
        avg_pnl = sum(pnls) / len(pnls) if pnls else 0

        # 基准对比（不符合条件的交易）
        baseline = [t for t in history if not self._match_condition(t, condition)]
        baseline_winners = [t for t in baseline if t.is_winner]
        baseline_win_rate = len(baseline_winners) / len(baseline) if baseline else 0

        # 简化的统计检验（使用胜率差异）
        p_value = self._simple_significance_test(matched, baseline)

        is_valid = (
            p_value < self.P_VALUE_THRESHOLD
            and win_rate - baseline_win_rate >= self.MIN_WIN_RATE_IMPROVEMENT
        )

        result = {
            "is_valid": is_valid,
            "sample_size": len(matched),
            "win_rate": win_rate,
            "baseline_win_rate": baseline_win_rate,
            "avg_pnl": avg_pnl,
            "p_value": p_value,
            "improvement": win_rate - baseline_win_rate,
        }

        if not is_valid:
            if p_value >= self.P_VALUE_THRESHOLD:
                result["reason"] = f"统计不显著: p={p_value:.3f}"
            else:
                result["reason"] = f"提升不足: {(win_rate - baseline_win_rate)*100:.1f}%"

        logger.info(f"规则验证: valid={is_valid}, p={p_value:.3f}, win_rate={win_rate:.2%}")
        return result

    def _match_condition(self, trade: TradeMemoryEntry, condition: dict) -> bool:
        """检查交易是否符合规则条件"""
        for key, value in condition.items():
            if key == "market_state":
                if trade.market_state != value:
                    return False
            elif key == "hour_range":
                if not (value[0] <= trade.hour_of_day <= value[1]):
                    return False
            elif key == "consecutive_losses_gt":
                if trade.consecutive_losses <= value:
                    return False
        return True

    def _simple_significance_test(
        self,
        matched: list[TradeMemoryEntry],
        baseline: list[TradeMemoryEntry],
    ) -> float:
        """简化的显著性检验（不依赖 scipy）"""
        if not baseline or len(baseline) < 5:
            return 1.0

        matched_wins = sum(1 for t in matched if t.is_winner)
        matched_total = len(matched)

        baseline_wins = sum(1 for t in baseline if t.is_winner)
        baseline_total = len(baseline)

        # 使用简化的 Z 检验近似 p 值
        p1 = matched_wins / matched_total
        p2 = baseline_wins / baseline_total

        # 合并比例
        p_combined = (matched_wins + baseline_wins) / (matched_total + baseline_total)

        # 标准误差
        se = (p_combined * (1 - p_combined) * (1/matched_total + 1/baseline_total)) ** 0.5

        if se == 0:
            return 1.0

        z = abs(p1 - p2) / se

        # 近似 p 值（使用正态分布）
        # 简化：z > 1.96 时 p < 0.05
        if z > 2.576:  # p < 0.01
            return 0.01
        elif z > 1.96:  # p < 0.05
            return 0.04
        elif z > 1.645:  # p < 0.10
            return 0.08
        else:
            return 0.5

    def create_distilled_rule(
        self, rule: dict, validation_result: dict
    ) -> Optional[DistilledRule]:
        """创建已验证的规则"""
        if not validation_result.get("is_valid"):
            return None

        from uuid import uuid4

        return DistilledRule(
            rule_id=f"rule_{uuid4().hex[:8]}",
            condition=rule["condition"],
            recommendation=rule["recommendation"],
            reasoning=rule.get("reasoning", ""),
            sample_size=validation_result["sample_size"],
            win_rate=validation_result["win_rate"],
            avg_pnl=validation_result["avg_pnl"],
            p_value=validation_result["p_value"],
        )
