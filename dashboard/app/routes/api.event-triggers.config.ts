import type { ActionFunctionArgs, LoaderFunctionArgs } from "react-router";
import { createClient } from "redis";

const CONFIG_KEY = "trading:event_trigger_config";
const CONFIG_UPDATED_CHANNEL = "trading:event_trigger_config:updated";

async function getRedisClient() {
  const redisUrl = process.env.REDIS_URL || "redis://localhost:6379";
  const client = createClient({ url: redisUrl });
  await client.connect();
  return client;
}

const DEFAULT_CONFIG = {
  enabled: true,
  scan_interval_seconds: 30,
  global_cooldown_seconds: 300,
  per_event_cooldown_seconds: 600,
  reset_decision_timer: true,
  events: {
    price_surge: { enabled: true, atr_multiplier: 1.5, lookback_seconds: 300 },
    volume_spike: { enabled: true, volume_multiplier: 2.5 },
    rsi_extreme: { enabled: true, upper_threshold: 75, lower_threshold: 25 },
    macd_cross: { enabled: true },
    bollinger_break: { enabled: true },
    market_state_change: { enabled: true },
    position_pnl: { enabled: true, profit_threshold_percent: 3.0, loss_threshold_percent: -2.0 },
  },
};

export async function loader(_args: LoaderFunctionArgs) {
  let client: Awaited<ReturnType<typeof getRedisClient>> | null = null;
  try {
    client = await getRedisClient();
    const raw = await client.get(CONFIG_KEY);
    const config = raw ? JSON.parse(raw) : DEFAULT_CONFIG;
    return Response.json({ config });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return Response.json({ error: message }, { status: 500 });
  } finally {
    if (client) { try { await client.disconnect(); } catch { /* ignore */ } }
  }
}

export async function action({ request }: ActionFunctionArgs) {
  if (request.method !== "POST") {
    return Response.json({ error: "Method not allowed" }, { status: 405 });
  }

  let client: Awaited<ReturnType<typeof getRedisClient>> | null = null;
  try {
    const body = await request.json();
    client = await getRedisClient();

    await client.set(CONFIG_KEY, JSON.stringify(body.config));
    await client.publish(CONFIG_UPDATED_CHANNEL, JSON.stringify(body.config));

    return Response.json({ success: true });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return Response.json({ error: message }, { status: 500 });
  } finally {
    if (client) { try { await client.disconnect(); } catch { /* ignore */ } }
  }
}
