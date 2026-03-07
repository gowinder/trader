import type { ActionFunctionArgs } from "react-router";
import { db } from "db";
import { llmProviders } from "db/schema";
import { eq } from "drizzle-orm";
import { writeFile, mkdir } from "fs/promises";
import { homedir } from "os";
import { join, dirname } from "path";
import { randomBytes, createHash } from "crypto";

// ── 多 Provider OAuth Device Flow 配置 ────────────────────────────────────

interface OAuthProviderConfig {
  clientId: string;
  deviceCodeUrl: string;
  tokenUrl: string;
  scope: string;
  grantType: string;
  tokenPath: string;        // 相对于 homedir
  usePKCE: boolean;
  buildTokenData: (data: Record<string, unknown>) => Record<string, unknown>;
}

const OAUTH_CONFIGS: Record<string, OAuthProviderConfig> = {
  "qwen-code": {
    clientId: "f0304373b74a44d2b584a3fb70ca9e56",
    deviceCodeUrl: "https://chat.qwen.ai/api/v1/oauth2/device/code",
    tokenUrl: "https://chat.qwen.ai/api/v1/oauth2/token",
    scope: "openid profile email model.completion",
    grantType: "urn:ietf:params:oauth:grant-type:device_code",
    tokenPath: ".qwen/oauth_creds.json",
    usePKCE: true,
    buildTokenData: (data) => ({
      access_token: data.access_token,
      refresh_token: data.refresh_token || "",
      token_type: data.token_type || "Bearer",
      resource_url: data.resource_url || "portal.qwen.ai",
      expiry_date: Date.now() + ((data.expires_in as number) || 3600) * 1000,
    }),
  },
  // 注意: Codex 使用 Authorization Code + 本地回调服务器流程，不支持 Device Flow
  // 用户需在宿主机运行 `codex auth` 完成授权，token 通过卷挂载共享到容器
};

// 进行中的授权会话（内存存储）
interface PendingAuth {
  deviceCode: string;
  codeVerifier: string;
  expiresAt: number;
  providerName: string;
}
const pendingAuths = new Map<number, PendingAuth>();

// PKCE 工具函数
function generateCodeVerifier(): string {
  return randomBytes(32).toString("base64url");
}

function generateCodeChallenge(verifier: string): string {
  return createHash("sha256").update(verifier).digest("base64url");
}

export async function action({ request }: ActionFunctionArgs) {
  if (request.method !== "POST") {
    return Response.json({ error: "Method not allowed" }, { status: 405 });
  }

  try {
    const body = await request.json();
    const { providerId, action: authAction } = body as {
      providerId: number;
      action: "start" | "poll" | "cancel";
    };

    // 验证 provider 存在且为 oauth 类型
    const [provider] = await db.select().from(llmProviders).where(eq(llmProviders.id, providerId));
    if (!provider) {
      return Response.json({ error: "Provider 不存在" }, { status: 404 });
    }
    if (provider.providerType !== "oauth") {
      return Response.json({ error: "该 Provider 不支持 OAuth 授权" }, { status: 400 });
    }

    const oauthConfig = OAUTH_CONFIGS[provider.name];
    if (!oauthConfig) {
      if (provider.name === "codex") {
        return Response.json({
          error: "Codex 不支持 Dashboard 授权，请在宿主机运行 `codex auth` 完成授权",
        }, { status: 400 });
      }
      return Response.json({ error: `Provider '${provider.name}' 无 OAuth 配置` }, { status: 400 });
    }

    // ── action: start ─────────────────────────────────────────────────
    if (authAction === "start") {
      const codeVerifier = generateCodeVerifier();
      const codeChallenge = generateCodeChallenge(codeVerifier);

      const params = new URLSearchParams({
        client_id: oauthConfig.clientId,
        scope: oauthConfig.scope,
      });

      if (oauthConfig.usePKCE) {
        params.set("code_challenge", codeChallenge);
        params.set("code_challenge_method", "S256");
      }

      const res = await fetch(oauthConfig.deviceCodeUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
          Accept: "application/json",
          "x-request-id": randomBytes(16).toString("hex"),
        },
        body: params.toString(),
      });

      if (!res.ok) {
        const text = await res.text().catch(() => "");
        return Response.json({
          error: `请求设备代码失败 (${res.status}): ${text.slice(0, 300)}`,
        }, { status: 502 });
      }

      const data = await res.json();
      const { device_code, user_code, verification_uri_complete, verification_uri, expires_in, interval } = data;

      // 存储进行中的授权
      pendingAuths.set(providerId, {
        deviceCode: device_code,
        codeVerifier,
        expiresAt: Date.now() + (expires_in || 600) * 1000,
        providerName: provider.name,
      });

      return Response.json({
        status: "started",
        verificationUri: verification_uri_complete || verification_uri,
        userCode: user_code,
        expiresIn: expires_in,
        interval: interval || 5,
      });
    }

    // ── action: poll ──────────────────────────────────────────────────
    if (authAction === "poll") {
      const pending = pendingAuths.get(providerId);
      if (!pending) {
        return Response.json({ status: "error", message: "没有进行中的授权流程" });
      }

      // 检查过期
      if (Date.now() > pending.expiresAt) {
        pendingAuths.delete(providerId);
        return Response.json({ status: "expired", message: "授权已超时，请重新发起" });
      }

      const params = new URLSearchParams({
        grant_type: oauthConfig.grantType,
        client_id: oauthConfig.clientId,
        device_code: pending.deviceCode,
      });

      if (oauthConfig.usePKCE) {
        params.set("code_verifier", pending.codeVerifier);
      }

      const res = await fetch(oauthConfig.tokenUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
          Accept: "application/json",
        },
        body: params.toString(),
      });

      const data = await res.json();

      // 用户还未授权
      if (data.error === "authorization_pending") {
        return Response.json({ status: "pending", message: "等待用户授权..." });
      }

      // 服务器请求降速
      if (data.error === "slow_down") {
        return Response.json({ status: "pending", message: "请降低轮询频率" });
      }

      // 其他错误
      if (data.error) {
        pendingAuths.delete(providerId);
        return Response.json({
          status: "error",
          message: `授权失败: ${data.error_description || data.error}`,
        });
      }

      // 成功获取 token
      if (data.access_token) {
        pendingAuths.delete(providerId);

        const tokenData = oauthConfig.buildTokenData(data);

        // 写入文件
        const tokenPath = join(homedir(), oauthConfig.tokenPath);
        await mkdir(dirname(tokenPath), { recursive: true });
        await writeFile(tokenPath, JSON.stringify(tokenData, null, 2), "utf-8");

        const expiresIn = (data.expires_in as number) || 3600;
        return Response.json({
          status: "success",
          message: "OAuth 授权成功",
          expiresAt: new Date(Date.now() + expiresIn * 1000).toISOString(),
        });
      }

      // 未知响应
      pendingAuths.delete(providerId);
      return Response.json({
        status: "error",
        message: `未知响应: ${JSON.stringify(data).slice(0, 300)}`,
      });
    }

    // ── action: cancel ────────────────────────────────────────────────
    if (authAction === "cancel") {
      pendingAuths.delete(providerId);
      return Response.json({ status: "cancelled", message: "已取消授权" });
    }

    return Response.json({ error: "无效的 action" }, { status: 400 });
  } catch (e: unknown) {
    return Response.json({
      error: `OAuth 授权失败: ${e instanceof Error ? e.message : String(e)}`,
    }, { status: 500 });
  }
}
