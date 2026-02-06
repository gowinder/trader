import postgres from "postgres";

interface UsageStats {
  total_calls: number;
  total_tokens: number;
  total_cost_usd: number;
  today_cost_usd: number;
  success_rate: number;
  avg_latency_ms: number;
  by_provider: Record<string, { calls: number; tokens: number; cost_usd: number }>;
}

function getDb() {
  const dbUrl = process.env.DATABASE_URL;
  if (!dbUrl) {
    return null;
  }
  return postgres(dbUrl);
}

export async function loader({ request }: { request: Request }) {
  const url = new URL(request.url);
  const action = url.searchParams.get("action") || "stats";

  const sql = getDb();
  if (!sql) {
    // 返回空数据而不是错误
    if (action === "stats") {
      return Response.json({
        total_calls: 0,
        total_tokens: 0,
        total_cost_usd: 0,
        today_cost_usd: 0,
        success_rate: 0,
        avg_latency_ms: 0,
        by_provider: {},
      });
    } else if (action === "daily") {
      return Response.json([]);
    } else if (action === "records") {
      return Response.json({ records: [], total: 0, limit: 100, offset: 0 });
    }
    return Response.json({ error: "Database not configured" }, { status: 404 });
  }

  try {
    switch (action) {
      case "stats":
        return await handleStats(sql);
      case "daily":
        const days = parseInt(url.searchParams.get("days") || "30");
        return await handleDailyStats(sql, days);
      case "records":
        const limit = parseInt(url.searchParams.get("limit") || "100");
        const offset = parseInt(url.searchParams.get("offset") || "0");
        const provider = url.searchParams.get("provider") || undefined;
        return await handleRecords(sql, limit, offset, provider);
      default:
        return Response.json({ error: "Unknown action" }, { status: 400 });
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return Response.json({ error: message }, { status: 500 });
  } finally {
    await sql.end();
  }
}

async function handleStats(sql: postgres.Sql): Promise<Response> {
  // 总体统计
  const totalStatsResult = await sql`
    SELECT
      COUNT(*) as total_calls,
      COALESCE(SUM(total_tokens), 0) as total_tokens,
      COALESCE(SUM(cost_usd), 0) as total_cost_usd,
      COALESCE(AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END), 0) as success_rate,
      COALESCE(AVG(latency_ms), 0) as avg_latency_ms
    FROM llm_usage
  `;

  const totalStats = totalStatsResult.length > 0
    ? {
        total_calls: Number(totalStatsResult[0].total_calls),
        total_tokens: Number(totalStatsResult[0].total_tokens),
        total_cost_usd: Number(totalStatsResult[0].total_cost_usd),
        success_rate: Number(totalStatsResult[0].success_rate),
        avg_latency_ms: Number(totalStatsResult[0].avg_latency_ms),
      }
    : {
        total_calls: 0,
        total_tokens: 0,
        total_cost_usd: 0,
        success_rate: 0,
        avg_latency_ms: 0,
      };

  // 今日费用
  const todayStatsResult = await sql`
    SELECT COALESCE(SUM(cost_usd), 0) as today_cost_usd
    FROM llm_usage
    WHERE DATE(created_at) = CURRENT_DATE
  `;

  const todayStats = todayStatsResult.length > 0
    ? { today_cost_usd: Number(todayStatsResult[0].today_cost_usd) }
    : { today_cost_usd: 0 };

  // 按 provider 统计
  const byProviderResult = await sql`
    SELECT
      provider,
      COUNT(*) as calls,
      COALESCE(SUM(total_tokens), 0) as tokens,
      COALESCE(SUM(cost_usd), 0) as cost_usd
    FROM llm_usage
    GROUP BY provider
  `;

  const by_provider: Record<string, { calls: number; tokens: number; cost_usd: number }> = {};
  for (const row of byProviderResult) {
    by_provider[row.provider] = {
      calls: Number(row.calls),
      tokens: Number(row.tokens),
      cost_usd: Number(row.cost_usd),
    };
  }

  const stats: UsageStats = {
    total_calls: totalStats.total_calls,
    total_tokens: totalStats.total_tokens,
    total_cost_usd: totalStats.total_cost_usd,
    today_cost_usd: todayStats.today_cost_usd,
    success_rate: totalStats.success_rate * 100,
    avg_latency_ms: totalStats.avg_latency_ms,
    by_provider,
  };

  return Response.json(stats);
}

async function handleDailyStats(sql: postgres.Sql, days: number): Promise<Response> {
  const result = await sql`
    SELECT
      DATE(created_at) as date,
      provider,
      COUNT(*) as calls,
      COALESCE(SUM(total_tokens), 0) as tokens,
      COALESCE(SUM(cost_usd), 0) as cost_usd
    FROM llm_usage
    WHERE created_at >= NOW() - INTERVAL '${days} days'
    GROUP BY DATE(created_at), provider
    ORDER BY date
  `;

  const rows = result.map((row) => ({
    date: row.date,
    provider: row.provider,
    calls: Number(row.calls),
    tokens: Number(row.tokens),
    cost_usd: Number(row.cost_usd),
  }));

  return Response.json(rows);
}

async function handleRecords(
  sql: postgres.Sql,
  limit: number,
  offset: number,
  provider?: string
): Promise<Response> {
  let result;
  if (provider) {
    result = await sql`
      SELECT
        id, created_at, provider, model, input_tokens, output_tokens,
        total_tokens, cost_usd, latency_ms, success, error_message
      FROM llm_usage
      WHERE provider = ${provider}
      ORDER BY created_at DESC
      LIMIT ${limit} OFFSET ${offset}
    `;
  } else {
    result = await sql`
      SELECT
        id, created_at, provider, model, input_tokens, output_tokens,
        total_tokens, cost_usd, latency_ms, success, error_message
      FROM llm_usage
      ORDER BY created_at DESC
      LIMIT ${limit} OFFSET ${offset}
    `;
  }

  const rows = result.map((row) => ({
    id: row.id,
    timestamp: row.created_at,
    provider: row.provider,
    model: row.model,
    input_tokens: Number(row.input_tokens),
    output_tokens: Number(row.output_tokens),
    total_tokens: Number(row.total_tokens),
    cost_usd: Number(row.cost_usd),
    latency_ms: Number(row.latency_ms),
    success: row.success,
    error_message: row.error_message,
  }));

  // 获取总数
  let countResult;
  if (provider) {
    countResult = await sql`SELECT COUNT(*) as count FROM llm_usage WHERE provider = ${provider}`;
  } else {
    countResult = await sql`SELECT COUNT(*) as count FROM llm_usage`;
  }
  const total = Number(countResult[0].count);

  return Response.json({
    records: rows,
    total,
    limit,
    offset,
  });
}
