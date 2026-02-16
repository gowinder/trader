# src/ai_trader/reflection/engine.py
"""复盘引擎"""

import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import uuid4

from .prompts import REFLECTION_PROMPT
from ..memory.models import TradeMemoryEntry
from ..optimization.parameter_registry import ParameterRegistry

if TYPE_CHECKING:
    from ..persistence.database import DatabaseManager
    from ..ai.client import LLMClient

logger = logging.getLogger(__name__)


class ReflectionEngine:
    """复盘引擎 - LLM 驱动的交易分析"""

    def __init__(
        self,
        llm_client: "LLMClient",
        db: "DatabaseManager",
        parameter_registry: Optional[ParameterRegistry] = None,
        redis_client=None,
    ):
        """初始化复盘引擎

        Args:
            llm_client: LLM 客户端
            db: 数据库管理器
            parameter_registry: 参数注册表（可选）
            redis_client: Redis 客户端（可选，推送复盘结果供 orchestrator 消费）
        """
        self.llm = llm_client
        self.db = db
        self.registry = parameter_registry or ParameterRegistry()
        self.redis = redis_client

    async def run_reflection(self, memories: list[TradeMemoryEntry]) -> dict:
        """运行复盘分析

        Args:
            memories: 待分析的交易记忆列表

        Returns:
            复盘结果
        """
        reflection_id = f"ref_{uuid4().hex[:8]}"
        logger.info(f"开始复盘: {reflection_id}, 分析 {len(memories)} 笔交易")

        # 构建 prompt
        prompt = self._build_prompt(memories)

        # 调用 LLM
        response = await self.llm.generate(prompt)

        # 解析结果
        result = self._parse_response(response)
        result["reflection_id"] = reflection_id
        result["trades_analyzed"] = len(memories)

        # 保存复盘记录
        await self._save_reflection(reflection_id, len(memories), result)

        # 推送复盘结果到 Redis 队列，供 OptimizationOrchestrator 消费
        if self.redis:
            try:
                await self.redis.lpush(
                    "reflection:results", json.dumps(result, ensure_ascii=False)
                )
                logger.info(f"复盘结果已推送到 Redis 队列: {reflection_id}")
            except Exception as e:
                logger.error(f"推送复盘结果到 Redis 失败: {e}")

        logger.info(f"复盘完成: {reflection_id}")
        return result

    def _build_prompt(self, memories: list[TradeMemoryEntry]) -> str:
        """构建复盘 prompt"""
        trade_data = [m.to_dict() for m in memories]

        return REFLECTION_PROMPT.format(
            n=len(memories),
            trade_data_json=json.dumps(trade_data, indent=2, ensure_ascii=False),
            current_parameters=json.dumps(self.registry.to_dict(), indent=2),
        )

    def _parse_response(self, response: str) -> dict:
        """解析 LLM 响应"""
        try:
            # 尝试提取 JSON
            response = response.strip()
            if response.startswith("```"):
                lines = response.split("\n")
                response = "\n".join(lines[1:-1])

            return json.loads(response)
        except json.JSONDecodeError as e:
            logger.error(f"复盘响应解析失败: {e}")
            return {
                "summary": "解析失败",
                "insights": [],
                "candidate_rules": [],
                "parameter_suggestions": {},
            }

    async def _save_reflection(
        self, reflection_id: str, trades_analyzed: int, result: dict
    ) -> None:
        """保存复盘记录"""
        await self.db.execute(
            """
            INSERT INTO reflection_logs (
                reflection_id, triggered_at, trades_analyzed,
                summary, insights, candidate_rules, parameter_suggestions
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            reflection_id,
            datetime.now(),
            trades_analyzed,
            result.get("summary"),
            json.dumps(result.get("insights", [])),
            json.dumps(result.get("candidate_rules", [])),
            json.dumps(result.get("parameter_suggestions", {})),
        )
