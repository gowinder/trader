import type { ActionFunctionArgs, LoaderFunctionArgs } from "react-router";
import { createClient } from "redis";

const TRIGGER_CONFIG_KEY = "advisory:trigger_config";
const LLM_CONFIG_KEY = "advisory:llm_config";

async function getRedisClient() {
  const redisUrl = process.env.REDIS_URL || "redis://localhost:6379";
  const client = createClient({ url: redisUrl });
  await client.connect();
  return client;
}

export async function loader({ request }: LoaderFunctionArgs) {
  let client: Awaited<ReturnType<typeof getRedisClient>> | null = null;
  try {
    client = await getRedisClient();
    const triggerConfig = await client.get(TRIGGER_CONFIG_KEY);
    const llmConfig = await client.get(LLM_CONFIG_KEY);

    // 返回 Redis 中的配置，null 表示尚未配置（前端用自身默认值展示）
    let parsedLlmConfig = null;
    if (llmConfig) {
      const cfg = JSON.parse(llmConfig);
      const { api_key, ...safe } = cfg;
      parsedLlmConfig = safe;
    }
    return Response.json({
      triggerConfig: triggerConfig ? JSON.parse(triggerConfig) : null,
      llmConfig: parsedLlmConfig,
    });
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

    if (body.triggerConfig) {
      await client.set(TRIGGER_CONFIG_KEY, JSON.stringify(body.triggerConfig));
      await client.publish("advisory:config:updated", JSON.stringify(body.triggerConfig));
    }
    if (body.llmConfig) {
      // 合并已有配置，保留 api_key 等字段不被覆盖
      const existingRaw = await client.get(LLM_CONFIG_KEY);
      const existing = existingRaw ? JSON.parse(existingRaw) : {};
      const merged = { ...existing, ...body.llmConfig };
      await client.set(LLM_CONFIG_KEY, JSON.stringify(merged));
      await client.publish("advisory:llm_config:updated", JSON.stringify(merged));
    }

    return Response.json({ success: true });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return Response.json({ error: message }, { status: 500 });
  } finally {
    if (client) { try { await client.disconnect(); } catch { /* ignore */ } }
  }
}
