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
    const presetId = body.presetId;
    const isLocked = body.isLocked === true;

    if (!presetId) {
      return Response.json({ error: "presetId is required" }, { status: 400 });
    }

    // 验证预设存在
    const preset = await sql`
      SELECT id, name, config_json FROM strategy_presets WHERE id = ${presetId}
    `;
    if (preset.length === 0) {
      return Response.json({ error: "Preset not found" }, { status: 404 });
    }

    // Check if current strategy is locked
    const activeRows = await sql`
      SELECT COALESCE(is_locked, false) as is_locked
      FROM active_strategy
      WHERE deactivated_at IS NULL
      ORDER BY activated_at DESC LIMIT 1
    `;
    if (activeRows.length > 0 && activeRows[0].is_locked) {
      return Response.json({ error: "Current strategy is locked" }, { status: 423 });
    }

    // 停用当前活跃策略
    await sql`
      UPDATE active_strategy SET deactivated_at = NOW()
      WHERE deactivated_at IS NULL
    `;

    // 激活新策略
    await sql`
      INSERT INTO active_strategy (preset_id, is_locked) VALUES (${presetId}, ${isLocked})
    `;

    // 更新 Redis 缓存并发布更新事件
    try {
      const configJson = typeof preset[0].config_json === "string"
        ? preset[0].config_json
        : JSON.stringify(preset[0].config_json);

      const redisClient = await getRedisClient();
      const redisPayload = JSON.stringify({
        preset_id: presetId,
        name: preset[0].name,
        config: typeof configJson === "string" ? JSON.parse(configJson) : configJson,
        is_locked: isLocked,
      });

      await redisClient.set("strategy:active_preset", redisPayload);
      await redisClient.publish("strategy:preset:updated", redisPayload);
      await redisClient.disconnect();
    } catch (redisErr) {
      console.error("Redis update failed (non-fatal):", redisErr);
    }

    return Response.json({ success: true, presetId, isLocked });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    console.error("Failed to activate preset:", message);
    return Response.json({ error: message }, { status: 500 });
  }
}
