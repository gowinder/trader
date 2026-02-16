import type { ActionFunctionArgs, LoaderFunctionArgs } from "react-router";
import { createClient } from "redis";

const REDIS_KEY = "trading:config";

interface TradingConfig {
  enabled: boolean;
  decisionInterval: number;
  lastTrigger?: string;
  updatedAt?: string;
}

async function getRedisClient() {
  const redisUrl = process.env.REDIS_URL || "redis://localhost:6379";
  const client = createClient({ url: redisUrl });
  await client.connect();
  return client;
}

export async function loader({ request }: LoaderFunctionArgs) {
  try {
    const client = await getRedisClient();
    const data = await client.get(REDIS_KEY);
    await client.disconnect();

    if (data) {
      return Response.json(JSON.parse(data));
    }

    // 默认配置
    return Response.json({
      enabled: true,
      decisionInterval: 1,
    });
  } catch (error) {
    console.error("Failed to get trading config:", error);
    return Response.json({
      enabled: true,
      decisionInterval: 1,
    });
  }
}

export async function action({ request }: ActionFunctionArgs) {
  if (request.method !== "POST") {
    return Response.json({ error: "Method not allowed" }, { status: 405 });
  }

  try {
    const body = await request.json();
    const client = await getRedisClient();

    // 读取现有配置并合并更新，保留其他字段
    const existing = await client.get(REDIS_KEY);
    const prev = existing ? JSON.parse(existing) : {};
    const config = {
      ...prev,
      ...body,
      updatedAt: new Date().toISOString(),
    };

    await client.set(REDIS_KEY, JSON.stringify(config));

    // 同时发布配置更新事件，让 trader 服务能够实时响应
    await client.publish("trading:config:updated", JSON.stringify(config));

    await client.disconnect();

    return Response.json({ success: true, config });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    console.error("Failed to save trading config:", message);
    return Response.json({ error: message }, { status: 500 });
  }
}
