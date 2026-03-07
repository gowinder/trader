import type { ActionFunctionArgs } from "react-router";
import { db } from "db";
import { llmProviders } from "db/schema";
import { eq } from "drizzle-orm";
import { decrypt } from "~/lib/encryption";
import { readFile } from "fs/promises";
import { homedir } from "os";
import { join } from "path";

const OAUTH_TOKEN_PATHS: Record<string, string> = {
  "qwen-code": ".qwen/oauth_creds.json",
  codex: ".codex/auth.json",
};

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

    // OAuth provider: 从本地 token 文件读取
    if (provider.providerType === "oauth") {
      const tokenRelPath = OAUTH_TOKEN_PATHS[provider.name];
      if (!tokenRelPath) {
        return Response.json({ success: false, latency: 0, message: "该 OAuth Provider 无 token 路径配置" });
      }

      let oauthToken: string;
      try {
        const tokenPath = join(homedir(), tokenRelPath);
        const raw = await readFile(tokenPath, "utf-8");
        const tokenData = JSON.parse(raw);
        // Codex: tokens.access_token; Qwen: access_token
        if (provider.name === "codex") {
          oauthToken = tokenData?.tokens?.access_token || "";
        } else {
          oauthToken = tokenData.access_token || "";
        }
        if (!oauthToken) {
          return Response.json({ success: false, latency: 0, message: "Token 文件中 access_token 为空" });
        }
        // Check token expiry: Qwen uses expiry_date field, Codex uses JWT exp claim
        let expiryMs: number | null = tokenData.expiry_date || null;
        if (!expiryMs && provider.name === "codex") {
          try {
            const parts = oauthToken.split(".");
            if (parts.length >= 2) {
              const payload = JSON.parse(Buffer.from(parts[1], "base64url").toString());
              if (payload.exp) expiryMs = payload.exp * 1000;
            }
          } catch { /* ignore JWT parse errors */ }
        }
        if (expiryMs && Date.now() >= expiryMs) {
          return Response.json({ success: false, latency: 0, message: "Token 已过期，请重新授权登录" });
        }
      } catch {
        return Response.json({ success: false, latency: 0, message: "Token 文件不存在，请先点击「授权登录」" });
      }

      const baseUrl = (provider.baseUrl || "https://portal.qwen.ai/v1").replace(/\/+$/, "");
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 15000);
      const startTime = Date.now();

      try {
        const reqUrl = `${baseUrl}/chat/completions`;
        const reqBody = { model, messages: [{ role: "user", content: "Hi" }], max_tokens: 10, stream: false };
        const res = await fetch(reqUrl, {
          method: "POST",
          headers: { Authorization: `Bearer ${oauthToken}`, "Content-Type": "application/json" },
          body: JSON.stringify(reqBody),
          signal: controller.signal,
        });
        const latency = Date.now() - startTime;
        const resText = await res.text().catch(() => "");

        console.log(`[LLM Test OAuth] URL: ${reqUrl}`);
        console.log(`[LLM Test OAuth] Status: ${res.status}, Response: ${resText.slice(0, 200)}`);

        if (res.ok) {
          return Response.json({ success: true, latency, message: `OAuth 连接成功，延迟 ${latency}ms` });
        }
        if (res.status === 401) {
          return Response.json({ success: false, latency, message: "Token 无效或已过期 (401)，请重新登录" });
        }
        return Response.json({ success: false, latency, message: `请求失败 (${res.status}): ${resText.slice(0, 500)}` });
      } finally {
        clearTimeout(timer);
      }
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
