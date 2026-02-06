import type { ActionFunctionArgs } from "react-router";
import { createClient } from "redis";

export async function action({ request }: ActionFunctionArgs) {
  if (request.method !== "POST") {
    return Response.json({ error: "Method not allowed" }, { status: 405 });
  }

  const redisUrl = process.env.REDIS_URL || "redis://localhost:6379";

  try {
    const client = createClient({ url: redisUrl });
    await client.connect();

    const taskId = `manual-trigger-${Date.now()}`;
    const task = {
      task_id: taskId,
      type: "manual_trigger",
      triggered_at: new Date().toISOString(),
    };

    // 发布手动触发事件
    await client.publish("trading:manual_trigger", JSON.stringify(task));

    // 同时记录到队列（备用方案）
    await client.lPush("trading:manual_triggers", JSON.stringify(task));

    await client.disconnect();

    return Response.json({
      success: true,
      message: "交易分析已触发",
      task_id: taskId,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    console.error("Failed to trigger trading analysis:", message);
    return Response.json({ error: message }, { status: 500 });
  }
}
