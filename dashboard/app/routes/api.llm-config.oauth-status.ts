import type { ActionFunctionArgs } from "react-router";
import { db } from "db";
import { llmProviders } from "db/schema";
import { eq } from "drizzle-orm";
import { readFile } from "fs/promises";
import { homedir } from "os";
import { join } from "path";

interface OAuthTokenConfig {
  path: string;
  extractToken: (data: Record<string, unknown>) => string;
  extractExpiry: (data: Record<string, unknown>) => number | null;
  loginHint: string;
}

const QWEN_OAUTH_CONFIG: OAuthTokenConfig = {
  path: ".qwen/oauth_creds.json",
  extractToken: (data) => (data.access_token as string) || "",
  extractExpiry: (data) => (data.expiry_date as number) || null,
  loginHint: "请点击「授权登录」完成 OAuth 认证",
};

const OAUTH_TOKEN_CONFIGS: Record<string, OAuthTokenConfig> = {
  "qwen-code": QWEN_OAUTH_CONFIG,
  qwen: QWEN_OAUTH_CONFIG, // legacy alias
  codex: {
    path: ".codex/auth.json",
    extractToken: (data) => {
      const tokens = data.tokens as Record<string, string> | undefined;
      return tokens?.access_token || "";
    },
    extractExpiry: (data) => {
      // Parse JWT exp claim from access_token
      const tokens = data.tokens as Record<string, string> | undefined;
      const accessToken = tokens?.access_token || "";
      if (!accessToken) return null;
      try {
        const parts = accessToken.split(".");
        if (parts.length < 2) return null;
        const payload = JSON.parse(Buffer.from(parts[1], "base64url").toString());
        return payload.exp ? payload.exp * 1000 : null; // convert to ms
      } catch {
        return null;
      }
    },
    loginHint: "请在宿主机运行 `codex auth` 完成授权",
  },
};

export async function action({ request }: ActionFunctionArgs) {
  if (request.method !== "POST") {
    return Response.json({ error: "Method not allowed" }, { status: 405 });
  }

  try {
    const body = await request.json();
    const { providerId } = body as { providerId: number };

    const [provider] = await db.select().from(llmProviders).where(eq(llmProviders.id, providerId));
    if (!provider) {
      return Response.json({ error: "Provider 不存在" }, { status: 404 });
    }

    const tokenConfig = OAUTH_TOKEN_CONFIGS[provider.name];
    if (!tokenConfig) {
      return Response.json({ hasToken: false, message: "该 Provider 不支持 OAuth" });
    }

    const tokenPath = join(homedir(), tokenConfig.path);

    try {
      const raw = await readFile(tokenPath, "utf-8");
      const data = JSON.parse(raw);

      const accessToken = tokenConfig.extractToken(data);
      const expiryMs = tokenConfig.extractExpiry(data);
      const hasToken = !!accessToken;

      let expired = false;
      let expiresAt: string | null = null;
      let canRefresh = false;

      if (expiryMs) {
        const expiryDate = new Date(expiryMs);
        expiresAt = expiryDate.toISOString();
        expired = Date.now() >= expiryMs;
      }

      // Check if provider has refresh_token (Codex/Qwen can auto-refresh)
      if (expired) {
        const tokens = data.tokens as Record<string, string> | undefined;
        const refreshToken = tokens?.refresh_token || (data.refresh_token as string) || "";
        if (refreshToken) {
          canRefresh = true;
        }
      }

      return Response.json({
        hasToken,
        expired: canRefresh ? false : expired, // Refreshable tokens are not truly expired
        expiresAt,
        tokenPath,
        message: hasToken
          ? expired
            ? canRefresh
              ? `Access token 已过期但可自动刷新${expiresAt ? `（过期: ${new Date(expiresAt).toLocaleString("zh-CN")}）` : ""}`
              : "Token 已过期，需要重新登录"
            : `Token 有效${expiresAt ? `，过期时间: ${new Date(expiresAt).toLocaleString("zh-CN")}` : ""}`
          : "Token 文件存在但 access_token 为空",
      });
    } catch {
      return Response.json({
        hasToken: false,
        expired: true,
        expiresAt: null,
        tokenPath,
        message: `Token 文件不存在: ${tokenPath}，${tokenConfig.loginHint}`,
      });
    }
  } catch (e: unknown) {
    return Response.json({
      error: `查询失败: ${e instanceof Error ? e.message : String(e)}`,
    }, { status: 500 });
  }
}
