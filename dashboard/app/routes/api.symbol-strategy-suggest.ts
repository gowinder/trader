import type { ActionFunctionArgs, LoaderFunctionArgs } from "react-router";
import { createClient } from "redis";
import { randomBytes } from "crypto";

async function getRedisClient() {
  const redisUrl = process.env.REDIS_URL || "redis://localhost:6379";
  const client = createClient({ url: redisUrl });
  await client.connect();
  return client;
}

// POST: trigger per-symbol strategy suggestion
export async function action({ request }: ActionFunctionArgs) {
  if (request.method !== "POST") {
    return Response.json({ error: "Method not allowed" }, { status: 405 });
  }

  let client: Awaited<ReturnType<typeof getRedisClient>> | null = null;
  try {
    const { symbols } = (await request.json()) as { symbols: string[] };
    if (!Array.isArray(symbols) || symbols.length === 0) {
      return Response.json({ error: "symbols array is required" }, { status: 400 });
    }

    client = await getRedisClient();
    const taskId = `symbol-strategy-suggest-${Date.now()}-${randomBytes(4).toString("hex")}`;

    // Check if trader consumer is online
    const consumerAlive = await client.get("strategy:suggest:consumer_alive");
    if (!consumerAlive) {
      return Response.json(
        { error: "策略建议服务未就绪，Trader 可能未启动或 Advisory 未初始化" },
        { status: 503 }
      );
    }

    await client.rPush(
      "symbol_strategy:suggest_queue",
      JSON.stringify({ task_id: taskId, symbols })
    );

    return Response.json({ taskId });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    console.error("Failed to trigger symbol strategy suggestion:", message);
    return Response.json({ error: message }, { status: 500 });
  } finally {
    if (client) { try { await client.disconnect(); } catch { /* ignore */ } }
  }
}

// GET: poll for result
export async function loader({ request }: LoaderFunctionArgs) {
  const url = new URL(request.url);
  const taskId = url.searchParams.get("taskId");

  if (!taskId) {
    return Response.json({ error: "taskId is required" }, { status: 400 });
  }

  let client: Awaited<ReturnType<typeof getRedisClient>> | null = null;
  try {
    client = await getRedisClient();
    const resultKey = `symbol_strategy:suggest:result:${taskId}`;
    const raw = await client.get(resultKey);

    if (!raw) {
      return Response.json({ status: "pending" });
    }

    return Response.json(JSON.parse(raw));
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    console.error("Failed to get symbol strategy suggestion result:", message);
    return Response.json({ error: message }, { status: 500 });
  } finally {
    if (client) { try { await client.disconnect(); } catch { /* ignore */ } }
  }
}
