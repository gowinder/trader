import type { ActionFunctionArgs } from "react-router";
import postgres from "postgres";
import { createClient } from "redis";

export async function action({ request }: ActionFunctionArgs) {
  if (request.method !== "POST") {
    return Response.json({ error: "Method not allowed" }, { status: 405 });
  }

  const body = await request.json();
  const { suggestionId, advisoryId, action: userAction, rejectionReason } = body;

  // 批量操作只需要 advisoryId，单条操作需要 suggestionId
  if (!userAction) {
    return Response.json({ error: "Missing action" }, { status: 400 });
  }
  if (!advisoryId && !suggestionId) {
    return Response.json({ error: "Missing suggestionId or advisoryId" }, { status: 400 });
  }

  const sql = postgres(process.env.DATABASE_URL!);

  try {
    // ====== 批量操作：全部采纳 ======
    if (userAction === "accept_all" && advisoryId) {
      const updated = await sql`
        UPDATE advisory_suggestions
        SET status = 'accepted', updated_at = NOW()
        WHERE advisory_id = ${advisoryId} AND status = 'pending'
        RETURNING id
      `;
      return Response.json({ success: true, count: updated.length });
    }

    // ====== 批量操作：全部确认执行 ======
    if (userAction === "confirm_all" && advisoryId) {
      const updated = await sql`
        UPDATE advisory_suggestions
        SET status = 'confirmed', updated_at = NOW()
        WHERE advisory_id = ${advisoryId} AND status = 'accepted'
        RETURNING id, type, target, action, detail
      `;

      if (updated.length > 0) {
        const redisUrl = process.env.REDIS_URL || "redis://localhost:6379";
        const redis = createClient({ url: redisUrl });
        try {
          await redis.connect();
          for (const suggestion of updated) {
            await redis.lPush(
              "advisory:execute_tasks",
              JSON.stringify({
                suggestion_id: suggestion.id,
                type: suggestion.type,
                target: suggestion.target,
                action: suggestion.action,
                detail: suggestion.detail,
              })
            );
          }
        } catch (redisError) {
          // Redis 入队失败时回滚 DB 状态
          const ids = updated.map((s) => s.id);
          await sql`
            UPDATE advisory_suggestions
            SET status = 'accepted', updated_at = NOW()
            WHERE id = ANY(${ids}) AND status = 'confirmed'
          `;
          throw redisError;
        } finally {
          try { await redis.disconnect(); } catch { /* ignore */ }
        }
      }

      // 检查是否全部终态 → resolve
      const [{ activeCount }] = await sql`
        SELECT COUNT(*)::int as "activeCount"
        FROM advisory_suggestions
        WHERE advisory_id = ${advisoryId} AND status NOT IN ('rejected', 'executed', 'failed', 'expired')
      `;
      if (activeCount === 0) {
        await sql`
          UPDATE advisories SET status = 'resolved', resolved_at = NOW()
          WHERE id = ${advisoryId}
        `;
      }

      return Response.json({ success: true, count: updated.length });
    }

    // ====== 单条操作 ======
    if (!suggestionId) {
      return Response.json({ error: "Missing suggestionId for single action" }, { status: 400 });
    }

    if (userAction === "accept") {
      const acceptResult = await sql`
        UPDATE advisory_suggestions
        SET status = 'accepted', updated_at = NOW()
        WHERE id = ${suggestionId} AND status = 'pending'
        RETURNING id
      `;
      if (acceptResult.length === 0) {
        return Response.json({ error: "Suggestion not found or not in pending state" }, { status: 409 });
      }
    } else if (userAction === "reject") {
      const rejectResult = await sql`
        UPDATE advisory_suggestions
        SET status = 'rejected', rejection_reason = ${rejectionReason || null}, updated_at = NOW()
        WHERE id = ${suggestionId} AND status IN ('pending', 'accepted')
        RETURNING id
      `;
      if (rejectResult.length === 0) {
        return Response.json({ error: "Suggestion not found or not in valid state" }, { status: 409 });
      }
    } else if (userAction === "cancel") {
      // 从 accepted 回退到 pending
      const cancelResult = await sql`
        UPDATE advisory_suggestions
        SET status = 'pending', updated_at = NOW()
        WHERE id = ${suggestionId} AND status = 'accepted'
        RETURNING id
      `;
      if (cancelResult.length === 0) {
        return Response.json({ error: "Suggestion not found or not in accepted state" }, { status: 409 });
      }
    } else if (userAction !== "confirm") {
      return Response.json({ error: `Unsupported action: ${userAction}` }, { status: 400 });
    } else {
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
        try {
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
        } catch (redisError) {
          // Redis 入队失败时回滚 DB 状态
          await sql`
            UPDATE advisory_suggestions
            SET status = 'accepted', updated_at = NOW()
            WHERE id = ${suggestionId} AND status = 'confirmed'
          `;
          throw redisError;
        } finally {
          try { await redis.disconnect(); } catch { /* ignore disconnect errors */ }
        }
      }
    }

    // Check if all suggestions in terminal state -> resolve advisory
    const suggestionRow = await sql`
      SELECT advisory_id FROM advisory_suggestions WHERE id = ${suggestionId}
    `;
    if (suggestionRow.length === 0) {
      return Response.json({ error: "Suggestion not found" }, { status: 404 });
    }
    const resolveAdvisoryId = suggestionRow[0].advisory_id;

    const [{ activeCount }] = await sql`
      SELECT COUNT(*)::int as "activeCount"
      FROM advisory_suggestions
      WHERE advisory_id = ${resolveAdvisoryId} AND status NOT IN ('rejected', 'executed', 'failed', 'expired')
    `;
    if (activeCount === 0) {
      await sql`
        UPDATE advisories SET status = 'resolved', resolved_at = NOW()
        WHERE id = ${resolveAdvisoryId}
      `;
    }

    return Response.json({ success: true });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return Response.json({ error: message }, { status: 500 });
  } finally {
    await sql.end();
  }
}
