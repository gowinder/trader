import type { LoaderFunctionArgs } from "react-router";
import postgres from "postgres";

export async function loader({ request }: LoaderFunctionArgs) {
  const url = new URL(request.url);
  const status = url.searchParams.get("status") || "pending";
  const limit = parseInt(url.searchParams.get("limit") || "50");

  const sql = postgres(process.env.DATABASE_URL!);

  try {
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
          WHERE a.status = ${status}
          GROUP BY a.id
          ORDER BY a.created_at DESC
          LIMIT ${limit}
        `;

    const [{ count }] = await sql`
      SELECT COUNT(*)::int as count FROM advisories WHERE status = 'pending'
    `;

    await sql.end();
    return Response.json({ advisories, pendingCount: count });
  } catch (error) {
    await sql.end();
    const message = error instanceof Error ? error.message : "Unknown error";
    return Response.json({ error: message }, { status: 500 });
  }
}
