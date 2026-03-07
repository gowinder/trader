import type { ActionFunctionArgs } from "react-router";
import { createClient } from "redis";

export async function action({ request }: ActionFunctionArgs) {
  if (request.method !== "POST") {
    return Response.json({ error: "Method not allowed" }, { status: 405 });
  }

  const redisUrl = process.env.REDIS_URL || "redis://localhost:6379";
  let client: ReturnType<typeof createClient> | null = null;

  try {
    client = createClient({ url: redisUrl });
    await client.connect();

    const taskId = `advisory-trigger-${Date.now()}`;
    const task = {
      task_id: taskId,
      type: "manual_advisory_trigger",
      triggered_at: new Date().toISOString(),
    };

    await client.publish("advisory:manual_trigger", JSON.stringify(task));

    return Response.json({
      success: true,
      message: "AI 建议分析已触发",
      task_id: taskId,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    console.error("Failed to trigger advisory analysis:", message);
    return Response.json({ error: message }, { status: 500 });
  } finally {
    if (client) { try { await client.disconnect(); } catch { /* ignore */ } }
  }
}
