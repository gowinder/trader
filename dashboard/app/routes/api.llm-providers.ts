import type { ActionFunctionArgs, LoaderFunctionArgs } from "react-router";
import { createClient } from "redis";

const REDIS_KEY = "llm:providers:config";

interface ProviderItem {
  name: string;
  model: string;
}

const DEFAULT_PROVIDERS: ProviderItem[] = [
  { name: "qwen-code", model: "coder-model" },
  { name: "gemini", model: "gemini-2.0-flash" },
  { name: "codex", model: "gpt-4o" },
  { name: "openrouter", model: "google/gemini-2.0-flash-exp:free" },
];

async function getRedisClient() {
  const redisUrl = process.env.REDIS_URL || "redis://localhost:6379";
  const client = createClient({ url: redisUrl });
  await client.connect();
  return client;
}

export async function loader(_args: LoaderFunctionArgs) {
  try {
    const client = await getRedisClient();
    const data = await client.get(REDIS_KEY);
    await client.disconnect();

    if (data) {
      return Response.json(JSON.parse(data));
    }

    return Response.json({ providers: DEFAULT_PROVIDERS });
  } catch (error) {
    console.error("Failed to get LLM providers config:", error);
    return Response.json({ providers: DEFAULT_PROVIDERS });
  }
}

export async function action({ request }: ActionFunctionArgs) {
  if (request.method !== "POST") {
    return Response.json({ error: "Method not allowed" }, { status: 405 });
  }

  try {
    const body = await request.json();
    const providers: ProviderItem[] = body.providers;

    if (!Array.isArray(providers) || providers.length === 0) {
      return Response.json({ error: "providers must be a non-empty array" }, { status: 400 });
    }

    const config = {
      providers,
      updatedAt: new Date().toISOString(),
    };

    const client = await getRedisClient();
    await client.set(REDIS_KEY, JSON.stringify(config));
    await client.publish("llm:providers:updated", JSON.stringify(config));
    await client.disconnect();

    return Response.json({ success: true, config });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    console.error("Failed to save LLM providers config:", message);
    return Response.json({ error: message }, { status: 500 });
  }
}
