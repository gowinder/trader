import postgres from "postgres";

function getDb() {
  const dbUrl = process.env.DATABASE_URL;
  if (!dbUrl) return null;
  return postgres(dbUrl);
}

// POST: save as a new custom preset
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
    const { sourcePresetId, config, displayName } = body;

    if (!sourcePresetId || !config) {
      return Response.json({ error: "sourcePresetId and config are required" }, { status: 400 });
    }

    // Get source preset
    const source = await sql`
      SELECT id, name, display_name, description, category, risk_level
      FROM strategy_presets WHERE id = ${sourcePresetId}
    `;
    if (source.length === 0) {
      return Response.json({ error: "Source preset not found" }, { status: 404 });
    }

    const s = source[0];
    const now = new Date();
    const dateSuffix = `${String(now.getMonth() + 1).padStart(2, "0")}${String(now.getDate()).padStart(2, "0")}`;

    // Generate unique name
    const baseName = `${s.name}-${dateSuffix}`;
    const baseDisplayName = displayName || `${s.display_name}-${dateSuffix}`;
    let finalName = baseName;
    let finalDisplayName = baseDisplayName;
    let suffix = 1;

    // Check for name conflicts
    while (true) {
      const existing = await sql`
        SELECT id FROM strategy_presets WHERE name = ${finalName}
      `;
      if (existing.length === 0) break;
      suffix++;
      finalName = `${baseName}-${suffix}`;
      finalDisplayName = `${baseDisplayName}-${suffix}`;
    }

    // Insert new custom preset
    const result = await sql`
      INSERT INTO strategy_presets
        (name, display_name, description, category, risk_level,
         config_json, is_system, source_preset_id)
      VALUES
        (${finalName}, ${finalDisplayName}, ${s.description},
         ${s.category}, ${s.risk_level},
         ${JSON.stringify(config)}, false, ${sourcePresetId})
      RETURNING id
    `;

    return Response.json({
      success: true,
      presetId: Number(result[0].id),
      name: finalName,
      displayName: finalDisplayName,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    console.error("Failed to save preset as new:", message);
    return Response.json({ error: message }, { status: 500 });
  } finally {
    await sql.end();
  }
}
