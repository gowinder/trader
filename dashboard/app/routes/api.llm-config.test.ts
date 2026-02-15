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
    const { providerId, model, apiKey: clientApiKey } = body as {
      providerId: number;
      model: string;
      apiKey?: string;
    };

    if (!model) {
      return Response.json({ error: "请指定模型" }, { status: 400 });
    }

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
    const startTime = Date.now();

    try {
      let res: Response;
      let reqUrl: string;
      let reqBody: Record<string, unknown>;

      if (provider.providerType === "openai_compatible") {
        reqUrl = `${baseUrl}/chat/completions`;
        reqBody = { model, messages: [{ role: "user", content: "Hi" }], max_tokens: 10 };
        res = await fetch(reqUrl, {
          method: "POST",
          headers: { Authorization: `Bearer ${apiKey}`, "Content-Type": "application/json" },
          body: JSON.stringify(reqBody),
          signal: controller.signal,
        });
      } else if (provider.providerType === "gemini_native") {
        reqUrl = `${baseUrl}/models/${model}:generateContent?key=${apiKey.slice(0, 6)}...`;
        reqBody = { contents: [{ role: "user", parts: [{ text: "Hi" }] }], generationConfig: { maxOutputTokens: 10 } };
        res = await fetch(`${baseUrl}/models/${model}:generateContent?key=${apiKey}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(reqBody),
          signal: controller.signal,
        });
      } else if (provider.providerType === "anthropic_compatible") {
        reqUrl = `${baseUrl}/v1/messages`;
        reqBody = { model, messages: [{ role: "user", content: "Hi" }], max_tokens: 10 };
        res = await fetch(reqUrl, {
          method: "POST",
          headers: { "x-api-key": apiKey, "anthropic-version": "2023-06-01", "Content-Type": "application/json" },
          body: JSON.stringify(reqBody),
          signal: controller.signal,
        });
      } else {
        return Response.json({ success: false, latency: 0, message: "未知 Provider 类型" });
      }

      const latency = Date.now() - startTime;
      const resText = await res.text().catch(() => "");

      console.log(`[LLM Test] URL: ${reqUrl}`);
      console.log(`[LLM Test] Body: ${JSON.stringify(reqBody)}`);
      console.log(`[LLM Test] Status: ${res.status}, Response: ${resText}`);

      if (res.ok) {
        return Response.json({ success: true, latency, message: `连接成功，延迟 ${latency}ms` });
      }

      return Response.json({
        success: false,
        latency,
        message: `请求失败 (${res.status}): ${resText.slice(0, 500)}`,
      });
    } finally {
      clearTimeout(timer);
    }
  } catch (e: unknown) {
    if (e instanceof Error && e.name === "AbortError") {
      return Response.json({ success: false, latency: 15000, message: "请求超时 (15s)" });
    }
    return Response.json({
      success: false,
      latency: 0,
      message: `测试失败: ${e instanceof Error ? e.message : String(e)}`,
    });
  }
}
