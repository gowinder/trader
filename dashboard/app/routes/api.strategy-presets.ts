import postgres from "postgres";

function getDb() {
  const dbUrl = process.env.DATABASE_URL;
  if (!dbUrl) return null;
  return postgres(dbUrl);
}

export async function loader() {
  const sql = getDb();
  if (!sql) {
    return Response.json({ presets: [], activePresetId: null, activatedAt: null });
  }

  try {
    // 获取所有预设
    const presets = await sql`
      SELECT id, name, display_name, description, category, risk_level, config_json, is_system
      FROM strategy_presets
      ORDER BY id
    `;

    // 获取当前活跃策略
    const activeRows = await sql`
      SELECT preset_id, activated_at
      FROM active_strategy
      WHERE deactivated_at IS NULL
      ORDER BY activated_at DESC
      LIMIT 1
    `;

    const activePresetId = activeRows.length > 0 ? Number(activeRows[0].preset_id) : null;
    const activatedAt = activeRows.length > 0 ? activeRows[0].activated_at : null;

    // 为每个预设获取统计数据
    const presetsWithStats = await Promise.all(
      presets.map(async (p) => {
        const presetId = Number(p.id);

        // 获取该预设所有激活时段
        const activations = await sql`
          SELECT activated_at, deactivated_at
          FROM active_strategy
          WHERE preset_id = ${presetId}
          ORDER BY activated_at
        `;

        let totalTrades = 0;
        let totalPnl = 0;
        let wins = 0;

        for (const act of activations) {
          const start = act.activated_at;
          const end = act.deactivated_at || new Date();

          const stats = await sql`
            SELECT
              COUNT(*) as trade_count,
              COALESCE(SUM(realized_pnl), 0) as total_pnl,
              COUNT(*) FILTER (WHERE realized_pnl > 0) as win_count
            FROM position_history
            WHERE closed_at BETWEEN ${start} AND ${end}
          `;

          if (stats.length > 0) {
            totalTrades += Number(stats[0].trade_count);
            totalPnl += Number(stats[0].total_pnl);
            wins += Number(stats[0].win_count);
          }
        }

        const winRate = totalTrades > 0 ? Math.round((wins / totalTrades) * 1000) / 10 : 0;

        return {
          id: presetId,
          name: p.name,
          displayName: p.display_name,
          description: p.description,
          category: p.category,
          riskLevel: p.risk_level,
          configJson: typeof p.config_json === "string" ? JSON.parse(p.config_json) : p.config_json,
          isSystem: p.is_system,
          stats: {
            totalTrades,
            totalPnl: Math.round(totalPnl * 100) / 100,
            winRate,
          },
        };
      })
    );

    return Response.json({
      presets: presetsWithStats,
      activePresetId,
      activatedAt,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    console.error("Failed to load strategy presets:", message);
    return Response.json({ presets: [], activePresetId: null, activatedAt: null });
  } finally {
    await sql.end();
  }
}
