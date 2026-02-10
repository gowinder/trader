import type { ActionFunctionArgs } from "react-router";
import postgres from "postgres";
import { createClient } from "redis";

export async function action({ request }: ActionFunctionArgs) {
  if (request.method !== "POST") {
    return Response.json({ error: "Method not allowed" }, { status: 405 });
  }

  const body = await request.json();
  const { suggestionId, action: userAction, rejectionReason } = body;

  if (!suggestionId || !userAction) {
    return Response.json({ error: "Missing suggestionId or action" }, { status: 400 });
  }

  const sql = postgres(process.env.DATABASE_URL!);

  try {
    if (userAction === "accept") {
      await sql`
        UPDATE advisory_suggestions
        SET status = 'accepted', updated_at = NOW()
        WHERE id = ${suggestionId}
      `;
    } else if (userAction === "reject") {
      await sql`
        UPDATE advisory_suggestions
        SET status = 'rejected', rejection_reason = ${rejectionReason || null}, updated_at = NOW()
        WHERE id = ${suggestionId}
      `;
    } else if (userAction === "confirm") {
      // 原子更新状态：仅 accepted → confirmed，防止重复执行
      const updated = await sql`
        UPDATE advisory_suggestions
        SET status = 'confirmed', updated_at = NOW()
        WHERE id = ${suggestionId} AND status = 'accepted'
        RETURNING id, type, target, action, detail
      `;

      if (updated.length > 0) {
        const suggestion = updated[0];
        const redisUrl = process.env.REDIS_URL || "redis://localhost:6379";
        const redis = createClient({ url: redisUrl });
        await redis.connect();
        await redis.lPush(
          "advisory:execute_tasks",
          JSON.stringify({
            suggestion_id: suggestionId,
            type: suggestion.type,
            target: suggestion.target,
            action: suggestion.action,
            detail: suggestion.detail,
          })
        );
        await redis.disconnect();
      }
    }

    // Check if all suggestions in terminal state -> resolve advisory
    // Terminal states: rejected, executed, failed
    // Non-terminal: pending, accepted, confirmed
    const [{ advisory_id: advisoryId }] = await sql`
      SELECT advisory_id FROM advisory_suggestions WHERE id = ${suggestionId}
    `;
    const [{ activeCount }] = await sql`
      SELECT COUNT(*)::int as "activeCount"
      FROM advisory_suggestions
      WHERE advisory_id = ${advisoryId} AND status NOT IN ('rejected', 'executed', 'failed')
    `;
    if (activeCount === 0) {
      await sql`
        UPDATE advisories SET status = 'resolved', resolved_at = NOW()
        WHERE id = ${advisoryId}
      `;
    }

    await sql.end();
    return Response.json({ success: true });
  } catch (error) {
    await sql.end();
    const message = error instanceof Error ? error.message : "Unknown error";
    return Response.json({ error: message }, { status: 500 });
  }
}
