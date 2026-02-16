"""优化编排器 — 复盘 → 影子验证 → 参数应用 的完整闭环"""

import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from .parameter_registry import ParameterRegistry
from .shadow_runner import ShadowRunner
from ..config import config

if TYPE_CHECKING:
    from ..persistence.database import DatabaseManager
    import redis.asyncio as redis

logger = logging.getLogger(__name__)


class OptimizationOrchestrator:
    """编排 复盘 → 影子验证 → 参数应用 的完整闭环"""

    def __init__(
        self,
        db: "DatabaseManager",
        shadow_runner: ShadowRunner,
        parameter_registry: ParameterRegistry,
        redis_client: Optional["redis.Redis"] = None,
    ):
        self.db = db
        self.shadow_runner = shadow_runner
        self.registry = parameter_registry
        self._redis = redis_client

    async def handle_reflection_result(self, reflection_result: dict) -> bool:
        """处理复盘结果，决定是否启动影子验证

        Returns:
            True if shadow run was started
        """
        suggestions = reflection_result.get("parameter_suggestions", {})
        if not suggestions:
            logger.info("复盘结果无参数建议，跳过")
            return False

        # 过滤只保留在 ParameterRegistry 中注册且在合法范围内的参数
        valid_suggestions = {}
        for param_name, detail in suggestions.items():
            param = self.registry.get(param_name)
            new_val = detail.get("new_value") if isinstance(detail, dict) else detail
            if param and new_val is not None and param.is_within_bounds(float(new_val)):
                valid_suggestions[param_name] = detail

        if not valid_suggestions:
            logger.info("复盘参数建议均不在合法范围内，跳过")
            return False

        # 已有影子运行进行中，跳过
        if self.shadow_runner.is_running:
            logger.info("影子运行已在进行中，跳过新建议")
            return False

        # 构建候选参数
        current_params = self.registry.to_dict()
        candidate_params = current_params.copy()
        for name, detail in valid_suggestions.items():
            new_val = detail.get("new_value") if isinstance(detail, dict) else detail
            candidate_params[name] = float(new_val)

        run_id = await self.shadow_runner.start(current_params, candidate_params)
        logger.info(
            f"从复盘结果启动影子运行: {run_id}, "
            f"候选参数变更: {list(valid_suggestions.keys())}"
        )
        return True

    async def evaluate_and_apply(self) -> Optional[dict]:
        """评估影子运行结果，通过则自动应用

        Returns:
            评估结果 dict if switched, else None
        """
        if not self.shadow_runner.is_running:
            return None

        result = self.shadow_runner.evaluate()

        if result.get("should_switch"):
            candidate = self.shadow_runner._candidate_params
            changes = {}
            for name, value in candidate.items():
                param = self.registry.get(name)
                if param:
                    old_val = param.current_value
                    self.registry.update(name, value, reason="shadow_run_validated")
                    # 同步到 runtime config
                    if hasattr(config, name):
                        setattr(config, name, value)
                    if old_val != value:
                        changes[name] = {"old": old_val, "new": value}

            await self._save_parameter_changes(changes, result)
            await self.shadow_runner.complete(switched=True, conclusion="验证通过，自动切换")

            if self._redis:
                await self._publish_config_update(changes)

            logger.info(f"影子运行验证通过，参数已自动切换: {list(changes.keys())}")
            return result

        # 检查是否样本足够但不达标
        stats = result.get("stats", {})
        if stats.get("candidate_trades", 0) >= self.shadow_runner.MIN_TRADES:
            await self.shadow_runner.complete(switched=False, conclusion="验证不通过")
            logger.info("影子运行验证不通过，保持原参数")

        return None

    async def _save_parameter_changes(self, changes: dict, eval_result: dict) -> None:
        """记录参数变更到数据库"""
        if not self.db or not changes:
            return
        try:
            await self.db.execute(
                """
                INSERT INTO parameter_changes (
                    changed_at, changes, eval_result, source
                ) VALUES ($1, $2, $3, $4)
                """,
                datetime.now(),
                json.dumps(changes),
                json.dumps(eval_result.get("stats", {})),
                "shadow_run",
            )
        except Exception as e:
            logger.error(f"Failed to save parameter changes: {e}")

    async def _publish_config_update(self, changes: dict) -> None:
        """发布配置更新事件到 Redis"""
        if not self._redis:
            return
        try:
            await self._redis.publish(
                "trading:config:updated",
                json.dumps({
                    "source": "optimization",
                    "changes": changes,
                }),
            )
        except Exception as e:
            logger.error(f"Failed to publish config update: {e}")
