import type { ActionFunctionArgs } from "react-router";
import { db } from "db";
import { llmProviders } from "db/schema";
import { eq } from "drizzle-orm";
import { decrypt } from "~/lib/encryption";

export async function action({ request }: ActionFunctionArgs) {
  if (request.method !== "POST") {
    return Response.json({ error: "Method not allowed" }, { status: 405 });
  }

  try {
    const body = await request.json();
    const { providerId, apiKey: clientApiKey } = body as { providerId: number; apiKey?: string };

    const [provider] = await db.select().from(llmProviders).where(eq(llmProviders.id, providerId));
    if (!provider) {
      return Response.json({ error: "Provider 不存在" }, { status: 404 });
    }

    const apiKey = clientApiKey || (provider.apiKeyEncrypted ? decrypt(provider.apiKeyEncrypted) : "");
    if (!apiKey) {
      return Response.json({ error: "API Key 未配置" }, { status: 400 });
    }

    const baseUrl = (provider.baseUrl || "").replace(/\/+$/, "");
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);

    try {
      let models: string[] = [];

      if (provider.providerType === "openai_compatible") {
        const res = await fetch(`${baseUrl}/models`, {
          headers: { Authorization: `Bearer ${apiKey}` },
          signal: controller.signal,
        });
        if (!res.ok) {
          const text = await res.text().catch(() => "");
          return Response.json({ error: `获取失败 (${res.status}): ${text.slice(0, 200)}` }, { status: 502 });
        }
        const data = await res.json();
        models = (data.data || []).map((m: { id: string }) => m.id).sort();
      } else if (provider.providerType === "gemini_native") {
        const res = await fetch(`${baseUrl}/models?key=${apiKey}`, {
          signal: controller.signal,
        });
        if (!res.ok) {
          const text = await res.text().catch(() => "");
          return Response.json({ error: `获取失败 (${res.status}): ${text.slice(0, 200)}` }, { status: 502 });
        }
        const data = await res.json();
        models = (data.models || [])
          .filter((m: { supportedGenerationMethods?: string[] }) =>
            m.supportedGenerationMethods?.includes("generateContent")
          )
          .map((m: { name: string }) => m.name.replace(/^models\//, ""))
          .sort();
      } else if (provider.providerType === "anthropic_compatible") {
        return Response.json({ models: [], message: "该 Provider 不支持获取模型列表，请手动添加" });
      } else {
        return Response.json({ models: [], message: "未知 Provider 类型" });
      }

      return Response.json({ models });
    } finally {
      clearTimeout(timer);
    }
  } catch (e: unknown) {
    if (e instanceof Error && e.name === "AbortError") {
      return Response.json({ error: "请求超时 (15s)" }, { status: 504 });
    }
    return Response.json({ error: `获取模型列表失败: ${e instanceof Error ? e.message : String(e)}` }, { status: 500 });
  }
}
