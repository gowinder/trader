import type { ActionFunctionArgs, LoaderFunctionArgs } from "react-router";
import { db } from "db";
import { llmProviders, llmRoutingConfig } from "db/schema";
import { eq, and } from "drizzle-orm";
import { decrypt } from "~/lib/encryption";
import { createClient } from "redis";

async function getRedisClient() {
  const redisUrl = process.env.REDIS_URL || "redis://localhost:6379";
  const client = createClient({ url: redisUrl });
  await client.connect();
  return client;
}

export async function loader({ request }: LoaderFunctionArgs) {
  try {
    const url = new URL(request.url);
    const scope = url.searchParams.get("scope") || "main";

    const rows = await db
      .select({
        id: llmRoutingConfig.id,
        scope: llmRoutingConfig.scope,
        providerId: llmRoutingConfig.providerId,
        model: llmRoutingConfig.model,
        priority: llmRoutingConfig.priority,
        isEnabled: llmRoutingConfig.isEnabled,
        providerName: llmProviders.name,
        providerDisplayName: llmProviders.displayName,
      })
      .from(llmRoutingConfig)
      .innerJoin(llmProviders, eq(llmRoutingConfig.providerId, llmProviders.id))
      .where(eq(llmRoutingConfig.scope, scope))
      .orderBy(llmRoutingConfig.priority);

    return Response.json({ routing: rows, scope });
  } catch (error) {
    console.error("Failed to get routing config:", error);
    return Response.json({ error: "Failed to load routing" }, { status: 500 });
  }
}

export async function action({ request }: ActionFunctionArgs) {
  if (request.method !== "PUT") {
    return Response.json({ error: "Method not allowed" }, { status: 405 });
  }

  try {
    const body = await request.json();
    const { scope, strategy, items } = body;

    if (!scope || !Array.isArray(items)) {
      return Response.json({ error: "scope and items are required" }, { status: 400 });
    }

    // 删除旧配置，写入新配置
    await db.delete(llmRoutingConfig).where(eq(llmRoutingConfig.scope, scope));

    if (items.length > 0) {
      await db.insert(llmRoutingConfig).values(
        items.map((item: { providerId: number; model: string; priority: number }) => ({
          scope,
          providerId: item.providerId,
          model: item.model,
          priority: item.priority,
        }))
      );
    }

    // 同步到 Redis
    await syncRoutingToRedis(scope, strategy);

    return Response.json({ success: true });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    console.error("LLM routing API error:", message);
    return Response.json({ error: message }, { status: 500 });
  }
}

async function syncRoutingToRedis(scope: string, strategy?: string) {
  const routing = await db
    .select({
      providerName: llmProviders.name,
      model: llmRoutingConfig.model,
      priority: llmRoutingConfig.priority,
      apiKeyEncrypted: llmProviders.apiKeyEncrypted,
      baseUrl: llmProviders.baseUrl,
      timeout: llmProviders.timeout,
      providerType: llmProviders.providerType,
    })
    .from(llmRoutingConfig)
    .innerJoin(llmProviders, eq(llmRoutingConfig.providerId, llmProviders.id))
    .where(and(eq(llmRoutingConfig.scope, scope), eq(llmRoutingConfig.isEnabled, true)))
    .orderBy(llmRoutingConfig.priority);

  const client = await getRedisClient();
  try {
    if (scope === "main") {
      const providersMap: Record<string, unknown> = {};
      const routingList = routing.map((r) => {
        const apiKey = r.apiKeyEncrypted ? decrypt(r.apiKeyEncrypted) : "";
        if (!providersMap[r.providerName]) {
          providersMap[r.providerName] = {
            api_key: apiKey,
            base_url: r.baseUrl || "",
            timeout: r.timeout,
            provider_type: r.providerType,
          };
        }
        return { provider: r.providerName, model: r.model, priority: r.priority };
      });

      const config = {
        providers: providersMap,
        routing: routingList,
        strategy: strategy || "priority",
        updatedAt: new Date().toISOString(),
      };

      await client.set("llm:providers:config", JSON.stringify(config));

      // 兼容旧格式事件
      const legacyProviders = routingList.map((r) => ({ name: r.provider, model: r.model }));
      await client.publish("llm:providers:updated", JSON.stringify({ providers: legacyProviders }));
      // 新格式事件
      await client.publish("llm:config:updated", JSON.stringify({ type: "routing", scope: "main", config }));
    } else if (scope === "advisory") {
      const first = routing[0];
      if (first) {
        const advisoryConfig = {
          provider: first.providerName,
          model: first.model,
          api_key: first.apiKeyEncrypted ? decrypt(first.apiKeyEncrypted) : "",
          base_url: first.baseUrl || "",
          timeout: first.timeout,
        };
        await client.set("advisory:llm_config", JSON.stringify(advisoryConfig));
        await client.publish("advisory:llm_config:updated", JSON.stringify(advisoryConfig));
      }
    }
  } finally {
    try { await client.disconnect(); } catch { /* ignore */ }
  }
}
