import type { ActionFunctionArgs, LoaderFunctionArgs } from "react-router";
import { createClient } from "redis";
import postgres from "postgres";

const AVAILABLE_SYMBOLS_KEY = "trading:available_symbols";
const CONFIG_KEY = "trading:config";
const DEFAULT_SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"];

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

export async function loader({ request }: LoaderFunctionArgs) {
  let client: ReturnType<typeof createClient> | null = null;
  const sql = getDb();

  try {
    client = await getRedisClient();

    // 1. 获取交易所支持的所有 symbol
    const availableRaw = await client.get(AVAILABLE_SYMBOLS_KEY);
    const available: string[] = availableRaw ? JSON.parse(availableRaw) : [];

    // 2. 从数据库获取已配置的 symbol_strategy + preset 信息
    let configured: Array<{
      symbol: string;
      presetName: string;
      presetDisplayName: string;
      presetCategory: string;
      presetRiskLevel: string;
      configOverrides: Record<string, unknown>;
      enabled: boolean;
    }> = [];

    if (sql) {
      try {
        const rows = await sql`
          SELECT
            ss.symbol,
            ss.config_overrides,
            ss.enabled,
            sp.name as preset_name,
            sp.display_name as preset_display_name,
            sp.category as preset_category,
            sp.risk_level as preset_risk_level
          FROM symbol_strategy ss
          JOIN strategy_presets sp ON ss.preset_id = sp.id
          ORDER BY ss.symbol
        `;

        configured = rows.map((r) => ({
          symbol: r.symbol,
          presetName: r.preset_name,
          presetDisplayName: r.preset_display_name,
          presetCategory: r.preset_category,
          presetRiskLevel: r.preset_risk_level,
          configOverrides:
            typeof r.config_overrides === "string"
              ? JSON.parse(r.config_overrides)
              : r.config_overrides || {},
          enabled: r.enabled === true,
        }));
      } catch (dbErr) {
        console.error("Failed to query symbol_strategy:", dbErr);
      }
    }

    return Response.json({ available, configured });
  } catch (error) {
    console.error("Failed to get symbols:", error);
    return Response.json({ available: [], configured: [] });
  } finally {
    if (client) {
      try { await client.disconnect(); } catch { /* ignore */ }
    }
    if (sql) {
      try { await sql.end(); } catch { /* ignore */ }
    }
  }
}

export async function action({ request }: ActionFunctionArgs) {
  if (request.method !== "POST") {
    return Response.json({ error: "Method not allowed" }, { status: 405 });
  }

  let client: ReturnType<typeof createClient> | null = null;
  const sql = getDb();

  try {
    const { configured } = (await request.json()) as {
      configured: Array<{
        symbol: string;
        preset_name: string;
        config_overrides?: Record<string, unknown>;
      }>;
    };

    if (!Array.isArray(configured) || configured.length === 0) {
      return Response.json({ error: "至少需要配置一个交易对" }, { status: 400 });
    }

    if (!sql) {
      return Response.json({ error: "数据库未配置" }, { status: 500 });
    }

    // 1. 查找 preset name → id 映射
    const presetNames = [...new Set(configured.map((c) => c.preset_name))];
    const presets = await sql`
      SELECT id, name FROM strategy_presets WHERE name = ANY(${presetNames})
    `;
    const presetMap = new Map<string, number>();
    for (const p of presets) {
      presetMap.set(p.name, Number(p.id));
    }

    // 验证所有 preset_name 都存在
    for (const c of configured) {
      if (!presetMap.has(c.preset_name)) {
        return Response.json(
          { error: `未知策略预设: ${c.preset_name}` },
          { status: 400 }
        );
      }
    }

    // 2. 将所有现有记录设为 disabled
    await sql`UPDATE symbol_strategy SET enabled = false, updated_at = NOW()`;

    // 3. Upsert 每个配置的 symbol
    for (const c of configured) {
      const presetId = presetMap.get(c.preset_name)!;
      const overrides = JSON.stringify(c.config_overrides || {});

      await sql`
        INSERT INTO symbol_strategy (symbol, preset_id, config_overrides, enabled, created_at, updated_at)
        VALUES (${c.symbol}, ${presetId}, ${overrides}::jsonb, true, NOW(), NOW())
        ON CONFLICT (symbol)
        DO UPDATE SET
          preset_id = ${presetId},
          config_overrides = ${overrides}::jsonb,
          enabled = true,
          updated_at = NOW()
      `;
    }

    // 4. 同步到 Redis（向后兼容）
    client = await getRedisClient();

    const enabledSymbols = configured.map((c) => c.symbol);
    const existingRaw = await client.get(CONFIG_KEY);
    const prev = existingRaw ? JSON.parse(existingRaw) : {};
    const config = {
      ...prev,
      trading_symbols: enabledSymbols.join(","),
      updatedAt: new Date().toISOString(),
    };

    await client.set(CONFIG_KEY, JSON.stringify(config));

    // 5. 发布事件
    await client.publish("trading:config:updated", JSON.stringify(config));
    await client.publish(
      "symbol_strategy:updated",
      JSON.stringify({
        symbols: enabledSymbols,
        timestamp: new Date().toISOString(),
      })
    );

    return Response.json({ success: true, symbols: enabledSymbols });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    console.error("Failed to save symbols:", message);
    return Response.json({ error: message }, { status: 500 });
  } finally {
    if (client) {
      try { await client.disconnect(); } catch { /* ignore */ }
    }
    if (sql) {
      try { await sql.end(); } catch { /* ignore */ }
    }
  }
}
