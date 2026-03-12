import postgres from "postgres";

function getDb() {
  const dbUrl = process.env.DATABASE_URL;
  if (!dbUrl) return null;
  return postgres(dbUrl);
}

// POST: delete a custom (non-system) preset
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
    const { presetId } = body;

    if (!presetId) {
      return Response.json({ error: "presetId is required" }, { status: 400 });
    }

    // Check global strategy lock
    const lockCheck = await sql`
      SELECT COALESCE(is_locked, false) as is_locked
      FROM active_strategy WHERE deactivated_at IS NULL
      ORDER BY activated_at DESC LIMIT 1
    `;
    if (lockCheck.length > 0 && lockCheck[0].is_locked) {
      return Response.json({ error: "策略已锁定，请先解锁再修改" }, { status: 423 });
    }

    // Verify preset exists and is not a system preset
    const preset = await sql`
      SELECT id, name, is_system FROM strategy_presets WHERE id = ${presetId}
    `;
    if (preset.length === 0) {
      return Response.json({ error: "Preset not found" }, { status: 404 });
    }
    if (preset[0].is_system) {
      return Response.json({ error: "Cannot delete system presets" }, { status: 400 });
    }

    // Check if currently active
    const active = await sql`
      SELECT preset_id FROM active_strategy
      WHERE deactivated_at IS NULL AND preset_id = ${presetId}
      LIMIT 1
    `;
    if (active.length > 0) {
      return Response.json(
        { error: "Cannot delete the currently active preset. Switch to another preset first." },
        { status: 409 }
      );
    }

    // Clear source_preset_id references from child presets
    await sql`UPDATE strategy_presets SET source_preset_id = NULL WHERE source_preset_id = ${presetId}`;

    // Delete
    await sql`DELETE FROM strategy_presets WHERE id = ${presetId} AND is_system = false`;

    return Response.json({ success: true, presetId });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    console.error("Failed to delete preset:", message);
    return Response.json({ error: message }, { status: 500 });
  }
}
