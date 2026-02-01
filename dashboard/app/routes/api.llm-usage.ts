import { spawn } from "child_process";
import path from "path";

interface UsageStats {
  total_calls: number;
  total_tokens: number;
  total_cost_usd: number;
  today_cost_usd: number;
  success_rate: number;
  avg_latency_ms: number;
  by_provider: Record<string, { calls: number; tokens: number; cost_usd: number }>;
}

function getDbPath(): string {
  return (
    process.env.LLM_USAGE_DB ||
    path.resolve(process.cwd(), "..", "data", "llm_usage.db")
  );
}

async function runSqlite(dbPath: string, query: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const sqlite = spawn("sqlite3", ["-json", dbPath, query]);
    let stdout = "";
    let stderr = "";

    sqlite.stdout.on("data", (data) => {
      stdout += data.toString();
    });

    sqlite.stderr.on("data", (data) => {
      stderr += data.toString();
    });

    sqlite.on("close", (code) => {
      if (code === 0) {
        resolve(stdout);
      } else {
        reject(new Error(stderr || `sqlite3 exited with code ${code}`));
      }
    });

    sqlite.on("error", (err) => {
      reject(err);
    });
  });
}

export async function loader({ request }: { request: Request }) {
  const url = new URL(request.url);
  const action = url.searchParams.get("action") || "stats";
  const dbPath = getDbPath();

  try {
    switch (action) {
      case "stats":
        return await handleStats(dbPath);
      case "daily":
        const days = parseInt(url.searchParams.get("days") || "30");
        return await handleDailyStats(dbPath, days);
      case "records":
        const limit = parseInt(url.searchParams.get("limit") || "100");
        const offset = parseInt(url.searchParams.get("offset") || "0");
        const provider = url.searchParams.get("provider") || undefined;
        return await handleRecords(dbPath, limit, offset, provider);
      default:
        return new Response(
          JSON.stringify({ error: "Unknown action" }),
          { status: 400, headers: { "Content-Type": "application/json" } }
        );
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return new Response(
      JSON.stringify({ error: message }),
      { status: 500, headers: { "Content-Type": "application/json" } }
    );
  }
}

async function handleStats(dbPath: string): Promise<Response> {
  // 总体统计
  const totalStatsJson = await runSqlite(
    dbPath,
    `SELECT
      COUNT(*) as total_calls,
      COALESCE(SUM(total_tokens), 0) as total_tokens,
      COALESCE(SUM(cost_usd), 0) as total_cost_usd,
      COALESCE(AVG(CASE WHEN success = 1 THEN 1.0 ELSE 0.0 END), 0) as success_rate,
      COALESCE(AVG(latency_ms), 0) as avg_latency_ms
    FROM llm_usage`
  );

  const totalStats = JSON.parse(totalStatsJson || "[{}]")[0] || {
    total_calls: 0,
    total_tokens: 0,
    total_cost_usd: 0,
    success_rate: 0,
    avg_latency_ms: 0,
  };

  // 今日费用
  const today = new Date().toISOString().split("T")[0];
  const todayStatsJson = await runSqlite(
    dbPath,
    `SELECT COALESCE(SUM(cost_usd), 0) as today_cost_usd
    FROM llm_usage
    WHERE DATE(timestamp) = '${today}'`
  );
  const todayStats = JSON.parse(todayStatsJson || "[{}]")[0] || { today_cost_usd: 0 };

  // 按 provider 统计
  const byProviderJson = await runSqlite(
    dbPath,
    `SELECT
      provider,
      COUNT(*) as calls,
      COALESCE(SUM(total_tokens), 0) as tokens,
      COALESCE(SUM(cost_usd), 0) as cost_usd
    FROM llm_usage
    GROUP BY provider`
  );

  const byProviderRows = JSON.parse(byProviderJson || "[]") as Array<{
    provider: string;
    calls: number;
    tokens: number;
    cost_usd: number;
  }>;

  const by_provider: Record<string, { calls: number; tokens: number; cost_usd: number }> = {};
  for (const row of byProviderRows) {
    by_provider[row.provider] = {
      calls: row.calls,
      tokens: row.tokens,
      cost_usd: row.cost_usd,
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

  return new Response(JSON.stringify(stats), {
    headers: { "Content-Type": "application/json" },
  });
}

async function handleDailyStats(dbPath: string, days: number): Promise<Response> {
  const startDate = new Date();
  startDate.setDate(startDate.getDate() - days);
  const startDateStr = startDate.toISOString();

  const rowsJson = await runSqlite(
    dbPath,
    `SELECT
      DATE(timestamp) as date,
      provider,
      COUNT(*) as calls,
      COALESCE(SUM(total_tokens), 0) as tokens,
      COALESCE(SUM(cost_usd), 0) as cost_usd
    FROM llm_usage
    WHERE timestamp >= '${startDateStr}'
    GROUP BY DATE(timestamp), provider
    ORDER BY date`
  );

  const rows = JSON.parse(rowsJson || "[]");

  return new Response(JSON.stringify(rows), {
    headers: { "Content-Type": "application/json" },
  });
}

async function handleRecords(
  dbPath: string,
  limit: number,
  offset: number,
  provider?: string
): Promise<Response> {
  let whereClause = "";
  if (provider) {
    whereClause = `WHERE provider = '${provider}'`;
  }

  const rowsJson = await runSqlite(
    dbPath,
    `SELECT
      id, timestamp, provider, model, input_tokens, output_tokens,
      total_tokens, cost_usd, latency_ms, success, error_message
    FROM llm_usage
    ${whereClause}
    ORDER BY timestamp DESC
    LIMIT ${limit} OFFSET ${offset}`
  );

  const rows = JSON.parse(rowsJson || "[]");

  // 获取总数
  const countJson = await runSqlite(
    dbPath,
    `SELECT COUNT(*) as count FROM llm_usage ${whereClause}`
  );
  const countResult = JSON.parse(countJson || "[{}]")[0] || { count: 0 };

  return new Response(
    JSON.stringify({
      records: rows,
      total: countResult.count,
      limit,
      offset,
    }),
    {
      headers: { "Content-Type": "application/json" },
    }
  );
}
