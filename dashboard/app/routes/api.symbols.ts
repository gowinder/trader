import type { ActionFunctionArgs, LoaderFunctionArgs } from "react-router";
import { createClient } from "redis";

const AVAILABLE_SYMBOLS_KEY = "trading:available_symbols";
const CONFIG_KEY = "trading:config";

const DEFAULT_SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"];

async function getRedisClient() {
  const redisUrl = process.env.REDIS_URL || "redis://localhost:6379";
  const client = createClient({ url: redisUrl });
  await client.connect();
  return client;
}

export async function loader({ request }: LoaderFunctionArgs) {
  let client: ReturnType<typeof createClient> | null = null;
  try {
    client = await getRedisClient();

    // 获取交易所支持的所有 symbol
    const availableRaw = await client.get(AVAILABLE_SYMBOLS_KEY);
    const available: string[] = availableRaw ? JSON.parse(availableRaw) : [];

    // 获取当前启用的 symbol（从 trading:config 的 trading_symbols 字段）
    const configRaw = await client.get(CONFIG_KEY);
    const config = configRaw ? JSON.parse(configRaw) : {};
    const tradingSymbols: string = config.trading_symbols || "";
    const enabled: string[] = tradingSymbols
      ? tradingSymbols.split(",").map((s: string) => s.trim()).filter(Boolean)
      : DEFAULT_SYMBOLS;

    return Response.json({ available, enabled });
  } catch (error) {
    console.error("Failed to get symbols:", error);
    return Response.json({ available: [], enabled: DEFAULT_SYMBOLS });
  } finally {
    if (client) { try { await client.disconnect(); } catch { /* ignore */ } }
  }
}

export async function action({ request }: ActionFunctionArgs) {
  if (request.method !== "POST") {
    return Response.json({ error: "Method not allowed" }, { status: 405 });
  }

  let client: ReturnType<typeof createClient> | null = null;
  try {
    const { enabled } = await request.json() as { enabled: string[] };
    if (!Array.isArray(enabled) || enabled.length === 0) {
      return Response.json({ error: "至少需要启用一个交易对" }, { status: 400 });
    }

    client = await getRedisClient();

    // 更新 trading:config 中的 trading_symbols
    const existingRaw = await client.get(CONFIG_KEY);
    const prev = existingRaw ? JSON.parse(existingRaw) : {};
    const config = {
      ...prev,
      trading_symbols: enabled.join(","),
      updatedAt: new Date().toISOString(),
    };

    await client.set(CONFIG_KEY, JSON.stringify(config));
    // 发布配置更新事件
    await client.publish("trading:config:updated", JSON.stringify(config));

    return Response.json({ success: true, enabled });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    console.error("Failed to save symbols:", message);
    return Response.json({ error: message }, { status: 500 });
  } finally {
    if (client) { try { await client.disconnect(); } catch { /* ignore */ } }
  }
}
