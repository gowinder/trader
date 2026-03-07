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

// PUT: overwrite save a preset's config
export async function action({ request }: { request: Request }) {
  if (request.method !== "PUT") {
    return Response.json({ error: "Method not allowed" }, { status: 405 });
  }

  const sql = getDb();
  if (!sql) {
    return Response.json({ error: "Database not configured" }, { status: 500 });
  }

  try {
    const body = await request.json();
    const { presetId, config } = body;

    if (!presetId || !config) {
      return Response.json({ error: "presetId and config are required" }, { status: 400 });
    }

    // Verify preset exists
    const preset = await sql`
      SELECT id, name, is_system, config_json FROM strategy_presets WHERE id = ${presetId}
    `;
    if (preset.length === 0) {
      return Response.json({ error: "Preset not found" }, { status: 404 });
    }

    const isSystem = preset[0].is_system;

    // Update config
    if (isSystem) {
      await sql`
        UPDATE strategy_presets
        SET config_json = ${JSON.stringify(config)}, is_modified = true, updated_at = NOW()
        WHERE id = ${presetId}
      `;
    } else {
      await sql`
        UPDATE strategy_presets
        SET config_json = ${JSON.stringify(config)}, updated_at = NOW()
        WHERE id = ${presetId}
      `;
    }

    // If this preset is currently active, notify backend via Redis
    const active = await sql`
      SELECT preset_id FROM active_strategy
      WHERE deactivated_at IS NULL AND preset_id = ${presetId}
      LIMIT 1
    `;
    if (active.length > 0) {
      try {
        const redisClient = await getRedisClient();
        const payload = JSON.stringify({
          preset_id: presetId,
          name: preset[0].name,
          config,
        });
        await redisClient.set("strategy:active_preset", payload);
        await redisClient.publish("strategy:preset:updated", payload);
        await redisClient.disconnect();
      } catch (redisErr) {
        console.error("Redis update failed (non-fatal):", redisErr);
      }
    }

    return Response.json({ success: true, presetId, isModified: isSystem });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    console.error("Failed to update preset:", message);
    return Response.json({ error: message }, { status: 500 });
  } finally {
    await sql.end();
  }
}
