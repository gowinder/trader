import postgres from "postgres";

function getDb() {
  const dbUrl = process.env.DATABASE_URL;
  if (!dbUrl) return null;
  return postgres(dbUrl);
}

export async function loader() {
  const sql = getDb();
  if (!sql) {
    return Response.json({ presets: [] });
  }

  try {
    const rows = await sql`
      SELECT name, display_name, description, category, risk_level, config_json
      FROM strategy_presets
      ORDER BY id
    `;

    const presets = rows.map((r) => ({
      name: r.name,
      displayName: r.display_name,
      description: r.description,
      category: r.category,
      riskLevel: r.risk_level,
      config: typeof r.config_json === "string" ? JSON.parse(r.config_json) : r.config_json,
    }));

    return Response.json({ presets });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    console.error("Failed to load presets list:", message);
    return Response.json({ presets: [] });
  } finally {
    await sql.end();
  }
}
