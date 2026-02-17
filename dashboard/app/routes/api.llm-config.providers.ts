import type { ActionFunctionArgs, LoaderFunctionArgs } from "react-router";
import { db } from "db";
import { llmProviders } from "db/schema";
import { eq } from "drizzle-orm";
import { encrypt, decrypt, maskApiKey } from "~/lib/encryption";
import { createClient } from "redis";

const BUILTIN_PROVIDERS = [
  { name: "openrouter", displayName: "OpenRouter", providerType: "openai_compatible", baseUrl: "https://openrouter.ai/api/v1", models: ["deepseek/deepseek-chat", "google/gemini-2.0-flash-exp:free", "anthropic/claude-3.5-sonnet"] },
  { name: "deepseek", displayName: "DeepSeek", providerType: "openai_compatible", baseUrl: "https://api.deepseek.com/v1", models: ["deepseek-chat", "deepseek-reasoner"] },
  { name: "gemini", displayName: "Gemini", providerType: "gemini_native", baseUrl: "https://generativelanguage.googleapis.com/v1beta", models: ["gemini-2.0-flash", "gemini-2.5-pro"] },
  { name: "glm", displayName: "智谱 GLM", providerType: "anthropic_compatible", baseUrl: "https://open.bigmodel.cn/api/anthropic", models: ["glm-4.7", "glm-4.7-flash", "glm-4-plus", "glm-4-flash"] },
  { name: "qwen", displayName: "通义千问 (Dashscope)", providerType: "openai_compatible", baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1", models: ["qwen-max", "qwen-plus", "qwen-turbo"] },
  { name: "qwen-code", displayName: "通义千问 (OAuth)", providerType: "oauth", baseUrl: "https://portal.qwen.ai/v1", models: ["coder-model", "qwen3-coder-plus", "qwen3-max"] },
];

async function ensureBuiltinProviders() {
  const existing = await db.select({ name: llmProviders.name }).from(llmProviders).where(eq(llmProviders.isBuiltin, true));
  const existingNames = new Set(existing.map((e) => e.name));

  for (const bp of BUILTIN_PROVIDERS) {
    if (!existingNames.has(bp.name)) {
      await db.insert(llmProviders).values({
        name: bp.name,
        displayName: bp.displayName,
        providerType: bp.providerType,
        baseUrl: bp.baseUrl,
        models: bp.models,
        isBuiltin: true,
      });
    } else {
      // 同步内置 provider 的 providerType、baseUrl 和 models
      await db.update(llmProviders).set({
        providerType: bp.providerType,
        baseUrl: bp.baseUrl,
        models: bp.models,
      }).where(eq(llmProviders.name, bp.name));
    }
  }
}

async function getRedisClient() {
  const redisUrl = process.env.REDIS_URL || "redis://localhost:6379";
  const client = createClient({ url: redisUrl });
  await client.connect();
  return client;
}

async function syncProvidersToRedis() {
  const providers = await db.select().from(llmProviders).where(eq(llmProviders.isEnabled, true));

  const providersMap: Record<string, { api_key: string; base_url: string; timeout: number; models: string[]; provider_type: string }> = {};
  for (const p of providers) {
    providersMap[p.name] = {
      api_key: p.apiKeyEncrypted ? decrypt(p.apiKeyEncrypted) : "",
      base_url: p.baseUrl || "",
      timeout: p.timeout,
      models: (p.models as string[]) || [],
      provider_type: p.providerType,
    };
  }

  const client = await getRedisClient();
  await client.set("llm:providers:pool", JSON.stringify(providersMap));
  await client.publish("llm:config:updated", JSON.stringify({ type: "providers", providers: providersMap }));
  await client.disconnect();
}

export async function loader(_args: LoaderFunctionArgs) {
  try {
    await ensureBuiltinProviders();
    const rows = await db.select().from(llmProviders).orderBy(llmProviders.id);

    const providers = rows.map((row) => ({
      id: row.id,
      name: row.name,
      displayName: row.displayName,
      providerType: row.providerType,
      apiKey: row.apiKeyEncrypted ? maskApiKey(decrypt(row.apiKeyEncrypted)) : "",
      hasApiKey: !!row.apiKeyEncrypted,
      baseUrl: row.baseUrl,
      timeout: row.timeout,
      models: row.models,
      isBuiltin: row.isBuiltin,
      isEnabled: row.isEnabled,
      createdAt: row.createdAt,
      updatedAt: row.updatedAt,
    }));

    return Response.json({ providers });
  } catch (error) {
    console.error("Failed to get LLM providers:", error);
    return Response.json({ error: "Failed to load providers" }, { status: 500 });
  }
}

export async function action({ request }: ActionFunctionArgs) {
  try {
    if (request.method === "POST") {
      const body = await request.json();
      const { name, displayName, providerType, apiKey, baseUrl, timeout, models } = body;

      if (!name || !displayName || !providerType) {
        return Response.json({ error: "name, displayName, providerType are required" }, { status: 400 });
      }

      const result = await db.insert(llmProviders).values({
        name,
        displayName,
        providerType,
        apiKeyEncrypted: apiKey ? encrypt(apiKey) : null,
        baseUrl: baseUrl || null,
        timeout: timeout || 60,
        models: models || [],
        isBuiltin: false,
      }).returning();

      await syncProvidersToRedis();
      return Response.json({ success: true, provider: { ...result[0], apiKeyEncrypted: undefined } });
    }

    if (request.method === "PUT") {
      const body = await request.json();
      const { id, displayName, apiKey, baseUrl, timeout, models, isEnabled } = body;

      if (!id) return Response.json({ error: "id is required" }, { status: 400 });

      const updates: Record<string, unknown> = { updatedAt: new Date() };
      if (displayName !== undefined) updates.displayName = displayName;
      if (baseUrl !== undefined) updates.baseUrl = baseUrl || null;
      if (timeout !== undefined) updates.timeout = timeout;
      if (models !== undefined) updates.models = models;
      if (isEnabled !== undefined) updates.isEnabled = isEnabled;
      if (apiKey) updates.apiKeyEncrypted = encrypt(apiKey);

      await db.update(llmProviders).set(updates).where(eq(llmProviders.id, id));
      await syncProvidersToRedis();

      return Response.json({ success: true });
    }

    if (request.method === "DELETE") {
      const body = await request.json();
      const { id } = body;

      const [provider] = await db.select().from(llmProviders).where(eq(llmProviders.id, id));
      if (!provider) return Response.json({ error: "Provider not found" }, { status: 404 });
      if (provider.isBuiltin) return Response.json({ error: "Cannot delete builtin provider" }, { status: 400 });

      await db.delete(llmProviders).where(eq(llmProviders.id, id));
      await syncProvidersToRedis();

      return Response.json({ success: true });
    }

    return Response.json({ error: "Method not allowed" }, { status: 405 });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    console.error("LLM config providers API error:", message);
    return Response.json({ error: message }, { status: 500 });
  }
}
