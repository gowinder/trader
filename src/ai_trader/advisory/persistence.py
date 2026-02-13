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

    async def create_running_advisory(
        self,
        trigger_type: TriggerType,
        trigger_detail: Dict[str, Any],
        llm_provider: str,
        llm_model: str,
    ) -> UUID:
        """创建一条 running 状态的 advisory 记录（LLM 调用前）"""
        advisory_id = await self.db.pool.fetchval(
            """
            INSERT INTO advisories (
                trigger_type, trigger_detail, urgency, market_summary,
                status, llm_provider, llm_model, tokens_used
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id
            """,
            trigger_type.value,
            json.dumps(trigger_detail),
            "low",
            "",
            "running",
            llm_provider,
            llm_model,
            0,
        )
        return advisory_id

    async def fail_advisory(self, advisory_id: UUID, error_message: str):
        """将 advisory 标记为 failed"""
        await self.db.pool.execute(
            """
            UPDATE advisories
            SET status = 'failed', market_summary = $1, resolved_at = NOW()
            WHERE id = $2
            """,
            error_message,
            advisory_id,
        )

    async def complete_advisory(
        self,
        advisory_id: UUID,
        result: AdvisoryResult,
    ):
        """LLM 成功后，更新 advisory 并写入 suggestions"""
        async with self.db.transaction() as conn:
            await conn.execute(
                """
                UPDATE advisories
                SET urgency = $1, market_summary = $2,
                    status = $3
                WHERE id = $4
                """,
                result.urgency.value,
                result.market_summary,
                "resolved" if not result.suggestions else "pending",
                advisory_id,
            )
            for idx, s in enumerate(result.suggestions):
                await conn.execute(
                    """
                    INSERT INTO advisory_suggestions (
                        advisory_id, sort_order, type, target, action, detail,
                        reasoning, risk_note, status
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    """,
                    advisory_id,
                    idx,
                    s.type.value,
                    s.target,
                    s.action,
                    json.dumps(s.detail),
                    s.reasoning,
                    s.risk_note,
                    "pending",
                )

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

            for idx, s in enumerate(result.suggestions):
                await conn.execute(
                    """
                    INSERT INTO advisory_suggestions (
                        advisory_id, sort_order, type, target, action, detail,
                        reasoning, risk_note, status
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    """,
                    advisory_id,
                    idx,
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

    async def update_suggestion_status_if(
        self,
        suggestion_id: UUID,
        new_status: str,
        expected_status: str,
    ) -> bool:
        """原子条件更新: 仅当当前状态为 expected_status 时才更新，返回是否成功"""
        result = await self.db.pool.fetchval(
            """
            UPDATE advisory_suggestions
            SET status = $1, updated_at = NOW()
            WHERE id = $2 AND status = $3
            RETURNING id
            """,
            new_status,
            suggestion_id,
            expected_status,
        )
        return result is not None

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
                ) ORDER BY s.sort_order
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

    async def get_suggestion_by_advisory_and_index(
        self, advisory_id: UUID, sort_order: int
    ) -> Optional[Dict]:
        """按 advisory_id + sort_order 定向查询单条建议"""
        row = await self.db.pool.fetchrow(
            """
            SELECT id, type, target, action, detail, status
            FROM advisory_suggestions
            WHERE advisory_id = $1 AND sort_order = $2
            """,
            advisory_id,
            sort_order,
        )
        if not row:
            return None
        d = dict(row)
        # asyncpg 可能将 jsonb 以字符串返回，确保 detail 为 dict
        if isinstance(d.get("detail"), str):
            import json as _json
            d["detail"] = _json.loads(d["detail"])
        return d

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
            WHERE advisory_id = $1 AND status NOT IN ('rejected', 'executed', 'failed', 'expired')
            """,
            advisory_id,
        )
        if active == 0:
            await self.resolve_advisory(advisory_id)
