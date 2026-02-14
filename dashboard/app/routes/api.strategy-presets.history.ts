import postgres from "postgres";

function getDb() {
  const dbUrl = process.env.DATABASE_URL;
  if (!dbUrl) return null;
  return postgres(dbUrl);
}

export async function loader({ request }: { request: Request }) {
  const sql = getDb();
  if (!sql) {
    return Response.json([]);
  }

  try {
    const url = new URL(request.url);
    const limit = parseInt(url.searchParams.get("limit") || "20");

    const rows = await sql`
      SELECT
        a.id,
        a.preset_id,
        a.activated_at,
        a.deactivated_at,
        sp.name,
        sp.display_name,
        sp.risk_level
      FROM active_strategy a
      JOIN strategy_presets sp ON sp.id = a.preset_id
      ORDER BY a.activated_at DESC
      LIMIT ${limit}
    `;

    const history = rows.map((r) => ({
      id: Number(r.id),
      presetId: Number(r.preset_id),
      name: r.name,
      displayName: r.display_name,
      riskLevel: r.risk_level,
      activatedAt: r.activated_at,
      deactivatedAt: r.deactivated_at,
    }));

    return Response.json(history);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    console.error("Failed to load strategy history:", message);
    return Response.json([]);
  }
}
