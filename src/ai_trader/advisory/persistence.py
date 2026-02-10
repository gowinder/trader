"""Advisory 持久化服务"""

import json
from typing import Optional, List, Dict, Any
from uuid import UUID

from ..persistence.database import DatabaseManager
from ..models.advisory import AdvisoryResult, TriggerType
from ..utils.logger import logger


class AdvisoryPersistenceService:
    """Advisory 数据持久化"""

    def __init__(self, db: DatabaseManager):
        self.db = db

    async def save_advisory(
        self,
        result: AdvisoryResult,
        trigger_type: TriggerType,
        trigger_detail: Dict[str, Any],
        llm_provider: str,
        llm_model: str,
        tokens_used: int,
    ) -> UUID:
        """保存 advisory 及其 suggestions"""
        async with self.db.transaction() as conn:
            advisory_id = await conn.fetchval(
                """
                INSERT INTO advisories (
                    trigger_type, trigger_detail, urgency, market_summary,
                    status, llm_provider, llm_model, tokens_used
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING id
                """,
                trigger_type.value,
                json.dumps(trigger_detail),
                result.urgency.value,
                result.market_summary,
                "resolved" if not result.suggestions else "pending",
                llm_provider,
                llm_model,
                tokens_used,
            )

            for s in result.suggestions:
                await conn.execute(
                    """
                    INSERT INTO advisory_suggestions (
                        advisory_id, type, target, action, detail,
                        reasoning, risk_note, status
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    """,
                    advisory_id,
                    s.type.value,
                    s.target,
                    s.action,
                    json.dumps(s.detail),
                    s.reasoning,
                    s.risk_note,
                    "pending",
                )

            return advisory_id

    async def update_suggestion_status(
        self,
        suggestion_id: UUID,
        status: str,
        execution_result: Optional[Dict] = None,
        rejection_reason: Optional[str] = None,
    ):
        """更新建议状态"""
        await self.db.pool.execute(
            """
            UPDATE advisory_suggestions
            SET status = $1, execution_result = $2, rejection_reason = $3,
                updated_at = NOW()
            WHERE id = $4
            """,
            status,
            json.dumps(execution_result) if execution_result else None,
            rejection_reason,
            suggestion_id,
        )

    async def get_pending_advisories(self, limit: int = 50) -> List[Dict]:
        """获取待处理的 advisories"""
        rows = await self.db.pool.fetch(
            """
            SELECT a.*, json_agg(
                json_build_object(
                    'id', s.id, 'type', s.type, 'target', s.target,
                    'action', s.action, 'detail', s.detail,
                    'reasoning', s.reasoning, 'risk_note', s.risk_note,
                    'status', s.status
                ) ORDER BY s.id
            ) as suggestions
            FROM advisories a
            LEFT JOIN advisory_suggestions s ON s.advisory_id = a.id
            WHERE a.status = 'pending'
            GROUP BY a.id
            ORDER BY a.created_at DESC
            LIMIT $1
            """,
            limit,
        )
        return [dict(r) for r in rows]

    async def resolve_advisory(self, advisory_id: UUID):
        """标记 advisory 为已处理"""
        await self.db.pool.execute(
            """
            UPDATE advisories SET status = 'resolved', resolved_at = NOW()
            WHERE id = $1
            """,
            advisory_id,
        )

    async def try_resolve_advisory_for_suggestion(self, suggestion_id: UUID):
        """检查建议所属 advisory 是否所有建议都已进入终态，如果是则自动 resolve"""
        row = await self.db.pool.fetchrow(
            "SELECT advisory_id FROM advisory_suggestions WHERE id = $1",
            suggestion_id,
        )
        if not row:
            return
        advisory_id = row["advisory_id"]
        active = await self.db.pool.fetchval(
            """
            SELECT COUNT(*) FROM advisory_suggestions
            WHERE advisory_id = $1 AND status NOT IN ('rejected', 'executed', 'failed')
            """,
            advisory_id,
        )
        if active == 0:
            await self.resolve_advisory(advisory_id)
