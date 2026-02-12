import type { ActionFunctionArgs, LoaderFunctionArgs } from "react-router";
import { createClient } from "redis";

const NOTIFICATION_CONFIG_KEY = "notification:config";

const DEFAULT_CONFIG = {
  telegram_enabled: true,
  trade: {
    enabled: true,
    open_long: true,
    open_short: true,
    close_long: true,
    close_short: true,
    add_reduce: true,
    stop_loss_take_profit: true,
  },
  decision: {
    enabled: true,
    action: true,
    hold: false,
  },
  backtest: {
    enabled: true,
    completed: true,
  },
  advisory: {
    enabled: true,
    suggestion: true,
  },
};

async function getRedisClient() {
  const redisUrl = process.env.REDIS_URL || "redis://localhost:6379";
  const client = createClient({ url: redisUrl });
  await client.connect();
  return client;
}

export async function loader(_args: LoaderFunctionArgs) {
  let client: Awaited<ReturnType<typeof getRedisClient>> | null = null;
  try {
    client = await getRedisClient();
    const config = await client.get(NOTIFICATION_CONFIG_KEY);

    return Response.json(config ? JSON.parse(config) : DEFAULT_CONFIG);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return Response.json({ error: message }, { status: 500 });
  } finally {
    if (client) { try { await client.disconnect(); } catch { /* ignore */ } }
  }
}

export async function action({ request }: ActionFunctionArgs) {
  if (request.method !== "POST" && request.method !== "PUT") {
    return Response.json({ error: "Method not allowed" }, { status: 405 });
  }

  let client: Awaited<ReturnType<typeof getRedisClient>> | null = null;
  try {
    const body = await request.json();
    client = await getRedisClient();

    if (body._action === "test") {
      await client.publish("notification:test", JSON.stringify({ timestamp: Date.now() }));
      return Response.json({ success: true });
    }

    const { _action, ...configData } = body;
    await client.set(NOTIFICATION_CONFIG_KEY, JSON.stringify(configData));
    await client.publish("notification:config:updated", JSON.stringify(configData));

    return Response.json({ success: true });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return Response.json({ error: message }, { status: 500 });
  } finally {
    if (client) { try { await client.disconnect(); } catch { /* ignore */ } }
  }
}
