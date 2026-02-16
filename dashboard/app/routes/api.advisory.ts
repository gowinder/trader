import type { LoaderFunctionArgs } from "react-router";
import postgres from "postgres";

export async function loader({ request }: LoaderFunctionArgs) {
  const url = new URL(request.url);
  const status = url.searchParams.get("status") || "pending";
  const limit = parseInt(url.searchParams.get("limit") || "50");

  const sql = postgres(process.env.DATABASE_URL!);

  try {
    // 自动过期：超过 24 小时未处理的 pending/accepted 建议标记为 expired
    await sql`
      UPDATE advisory_suggestions
      SET status = 'expired', updated_at = NOW()
      WHERE status IN ('pending', 'accepted')
        AND (updated_at < NOW() - INTERVAL '24 hours'
             OR (updated_at IS NULL AND EXISTS (
               SELECT 1 FROM advisories WHERE id = advisory_id AND created_at < NOW() - INTERVAL '24 hours'
             )))
    `;
    // 将所有建议都已终态的 advisory 标记为 resolved
    await sql`
      UPDATE advisories SET status = 'resolved', resolved_at = NOW()
      WHERE status = 'pending'
        AND NOT EXISTS (
          SELECT 1 FROM advisory_suggestions
          WHERE advisory_id = advisories.id
            AND status NOT IN ('rejected', 'executed', 'failed', 'expired')
        )
    `;

    const advisories = status === "all"
      ? await sql`
          SELECT a.*,
            COALESCE(
              json_agg(
                json_build_object(
                  'id', s.id, 'type', s.type, 'target', s.target,
                  'action', s.action, 'detail', s.detail,
                  'reasoning', s.reasoning, 'risk_note', s.risk_note,
                  'status', s.status, 'execution_result', s.execution_result,
                  'rejection_reason', s.rejection_reason
                ) ORDER BY s.sort_order
              ) FILTER (WHERE s.id IS NOT NULL), '[]'
            ) as suggestions
          FROM advisories a
          LEFT JOIN advisory_suggestions s ON s.advisory_id = a.id
          GROUP BY a.id
          ORDER BY a.created_at DESC
          LIMIT ${limit}
        `
      : await sql`
          SELECT a.*,
            COALESCE(
              json_agg(
                json_build_object(
                  'id', s.id, 'type', s.type, 'target', s.target,
                  'action', s.action, 'detail', s.detail,
                  'reasoning', s.reasoning, 'risk_note', s.risk_note,
                  'status', s.status, 'execution_result', s.execution_result,
                  'rejection_reason', s.rejection_reason
                ) ORDER BY s.sort_order
              ) FILTER (WHERE s.id IS NOT NULL), '[]'
            ) as suggestions
          FROM advisories a
          LEFT JOIN advisory_suggestions s ON s.advisory_id = a.id
          WHERE a.status = ANY(${status === "pending" ? ["pending", "running", "failed"] : [status]}::text[])
          GROUP BY a.id
          ORDER BY a.created_at DESC
          LIMIT ${limit}
        `;

    const [{ count }] = await sql`
      SELECT COUNT(*)::int as count FROM advisories WHERE status IN ('pending', 'running', 'failed')
    `;

    await sql.end();
    return Response.json({ advisories, pendingCount: count });
  } catch (error) {
    await sql.end();
    const message = error instanceof Error ? error.message : "Unknown error";
    return Response.json({ error: message }, { status: 500 });
  }
}
