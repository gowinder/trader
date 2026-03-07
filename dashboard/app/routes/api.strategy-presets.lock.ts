import postgres from "postgres";
import { createClient } from "redis";

function getDb() {
  const dbUrl = process.env.DATABASE_URL;
  if (!dbUrl) return null;
  return postgres(dbUrl);
}

async function getRedisClient() {
  const redisUrl = process.env.REDIS_URL || "redis://localhost:6379";
  const client = createClient({ url: redisUrl });
  await client.connect();
  return client;
}

export async function action({ request }: { request: Request }) {
  if (request.method !== "POST") {
    return Response.json({ error: "Method not allowed" }, { status: 405 });
  }

  const sql = getDb();
  if (!sql) {
    return Response.json({ error: "Database not configured" }, { status: 500 });
  }

  try {
    const body = await request.json();
    const isLocked = body.isLocked === true;

    // Update the active strategy's lock state
    const result = await sql`
      UPDATE active_strategy SET is_locked = ${isLocked}
      WHERE deactivated_at IS NULL
      RETURNING preset_id
    `;

    if (result.length === 0) {
      return Response.json({ error: "No active strategy found" }, { status: 404 });
    }

    // Update Redis cache
    try {
      const redisClient = await getRedisClient();
      const existing = await redisClient.get("strategy:active_preset");
      if (existing) {
        const data = JSON.parse(existing);
        data.is_locked = isLocked;
        await redisClient.set("strategy:active_preset", JSON.stringify(data));
        await redisClient.publish("strategy:preset:updated", JSON.stringify(data));
      }
      await redisClient.disconnect();
    } catch (redisErr) {
      console.error("Redis update failed (non-fatal):", redisErr);
    }

    return Response.json({ success: true, isLocked });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    console.error("Failed to toggle strategy lock:", message);
    return Response.json({ error: message }, { status: 500 });
  } finally {
    await sql.end();
  }
}
