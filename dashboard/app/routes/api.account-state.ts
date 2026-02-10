import type { LoaderFunctionArgs } from "react-router";
import { createClient } from "redis";

export async function loader(_args: LoaderFunctionArgs) {
  const redisUrl = process.env.REDIS_URL || "redis://localhost:6379";
  let client: ReturnType<typeof createClient> | null = null;

  try {
    client = createClient({ url: redisUrl });
    await client.connect();

    const stateJson = await client.get("trading:account_state");

    if (!stateJson) {
      return Response.json({
        success: true,
        data: null,
        message: "No account state available (trader may be offline)",
      });
    }

    const state = JSON.parse(stateJson);
    return Response.json({
      success: true,
      data: state,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    console.error("Failed to fetch account state:", message);
    return Response.json(
      { success: false, error: message },
      { status: 500 }
    );
  } finally {
    if (client) { try { await client.disconnect(); } catch { /* ignore */ } }
  }
}
