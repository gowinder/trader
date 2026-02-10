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
  try {
    const client = await getRedisClient();
    const triggerConfig = await client.get(TRIGGER_CONFIG_KEY);
    const llmConfig = await client.get(LLM_CONFIG_KEY);
    await client.disconnect();

    return Response.json({
      triggerConfig: triggerConfig ? JSON.parse(triggerConfig) : {
        interval_minutes: 60,
        price_volatility_enabled: true,
        price_volatility_threshold: 5.0,
        consecutive_loss_enabled: true,
        consecutive_loss_threshold: 3,
        unrealized_pnl_enabled: true,
        unrealized_pnl_threshold: -5.0,
        sentiment_shift_enabled: true,
        cooldown_minutes: 30,
      },
      llmConfig: llmConfig ? JSON.parse(llmConfig) : {
        provider: "openrouter",
        model: "deepseek/deepseek-chat",
        base_url: "",
      },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return Response.json({ error: message }, { status: 500 });
  }
}

export async function action({ request }: ActionFunctionArgs) {
  if (request.method !== "POST") {
    return Response.json({ error: "Method not allowed" }, { status: 405 });
  }

  try {
    const body = await request.json();
    const client = await getRedisClient();

    if (body.triggerConfig) {
      await client.set(TRIGGER_CONFIG_KEY, JSON.stringify(body.triggerConfig));
      await client.publish("advisory:config:updated", JSON.stringify(body.triggerConfig));
    }
    if (body.llmConfig) {
      await client.set(LLM_CONFIG_KEY, JSON.stringify(body.llmConfig));
      await client.publish("advisory:llm_config:updated", JSON.stringify(body.llmConfig));
    }

    await client.disconnect();
    return Response.json({ success: true });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return Response.json({ error: message }, { status: 500 });
  }
}
