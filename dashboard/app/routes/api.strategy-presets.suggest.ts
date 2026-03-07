import type { ActionFunctionArgs, LoaderFunctionArgs } from "react-router";
import { createClient } from "redis";
import { randomBytes } from "crypto";

async function getRedisClient() {
  const redisUrl = process.env.REDIS_URL || "redis://localhost:6379";
  const client = createClient({ url: redisUrl });
  await client.connect();
  return client;
}

// POST: trigger strategy suggestion
export async function action({ request }: ActionFunctionArgs) {
  if (request.method !== "POST") {
    return Response.json({ error: "Method not allowed" }, { status: 405 });
  }

  try {
    const client = await getRedisClient();
    const taskId = `strategy-suggest-${Date.now()}-${randomBytes(4).toString("hex")}`;

    // Check if trader consumer is actually online (heartbeat flag with TTL)
    const consumerAlive = await client.get("strategy:suggest:consumer_alive");
    if (!consumerAlive) {
      // Also check LLM config for a more specific error message
      const llmConfig = await client.get("advisory:llm_config");
      await client.disconnect();
      if (!llmConfig) {
        return Response.json(
          { error: "Advisory LLM 未配置，请先在 Advisory Settings 中配置 LLM" },
          { status: 503 }
        );
      }
      return Response.json(
        { error: "策略建议服务未就绪，Trader 可能未启动或 Advisory 未初始化" },
        { status: 503 }
      );
    }

    // Push request to Redis list (persistent queue, won't lose messages)
    await client.rPush(
      "strategy:suggest_queue",
      JSON.stringify({ task_id: taskId })
    );

    await client.disconnect();

    return Response.json({ taskId });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    console.error("Failed to trigger strategy suggestion:", message);
    return Response.json({ error: message }, { status: 500 });
  }
}

// GET: poll for result
export async function loader({ request }: LoaderFunctionArgs) {
  const url = new URL(request.url);
  const taskId = url.searchParams.get("taskId");

  if (!taskId) {
    return Response.json({ error: "taskId is required" }, { status: 400 });
  }

  try {
    const client = await getRedisClient();
    const resultKey = `strategy:suggest:result:${taskId}`;
    const raw = await client.get(resultKey);
    await client.disconnect();

    if (!raw) {
      return Response.json({ status: "pending" });
    }

    const result = JSON.parse(raw);
    return Response.json(result);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    console.error("Failed to get strategy suggestion result:", message);
    return Response.json({ error: message }, { status: 500 });
  }
}
