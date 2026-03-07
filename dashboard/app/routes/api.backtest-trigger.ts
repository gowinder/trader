import type { ActionFunctionArgs, LoaderFunctionArgs } from "react-router";
import { createClient } from "redis";

// 查询回测任务状态
export async function loader({ request }: LoaderFunctionArgs) {
  const url = new URL(request.url);
  const taskId = url.searchParams.get("task_id");

  if (!taskId) {
    return Response.json({ error: "task_id is required" }, { status: 400 });
  }

  const redisUrl = process.env.REDIS_URL || "redis://localhost:6379";
  let client: ReturnType<typeof createClient> | null = null;

  try {
    client = createClient({ url: redisUrl });
    await client.connect();

    const status = await client.hGetAll(`backtest:status:${taskId}`);

    if (!status || Object.keys(status).length === 0) {
      return Response.json({
        task_id: taskId,
        status: "pending",
        message: "Task is waiting to be processed",
      });
    }

    return Response.json({
      task_id: taskId,
      ...status,
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

  const body = await request.json();
  const {
    symbol = "BTCUSDT",
    startDate,
    endDate,
    interval = "1h",
    capital = 10000,
  } = body;

  // 验证日期
  if (!startDate || !endDate) {
    return Response.json({ error: "startDate and endDate are required" }, { status: 400 });
  }

  const redisUrl = process.env.REDIS_URL || "redis://localhost:6379";
  let client: ReturnType<typeof createClient> | null = null;

  try {
    // 通过 Redis 队列发送回测任务
    client = createClient({ url: redisUrl });
    await client.connect();

    const taskId = `backtest-${Date.now()}`;
    const task = {
      task_id: taskId,
      type: "backtest",
      symbol,
      start_date: startDate,
      end_date: endDate,
      interval,
      capital,
      created_at: new Date().toISOString(),
    };

    // 推送到回测任务队列
    await client.lPush("backtest:tasks", JSON.stringify(task));

    return Response.json({
      success: true,
      message: "Backtest task queued",
      task_id: taskId,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    console.error("Failed to queue backtest task:", message);
    return Response.json({ error: message }, { status: 500 });
  } finally {
    if (client) { try { await client.disconnect(); } catch { /* ignore */ } }
  }
}
