import type { ActionFunctionArgs } from "react-router";
import { db } from "db";
import { llmProviders } from "db/schema";
import { eq } from "drizzle-orm";
import { readFile } from "fs/promises";
import { homedir } from "os";
import { join } from "path";

const OAUTH_TOKEN_PATHS: Record<string, string> = {
  qwen: ".qwen/oauth_creds.json",
  "qwen-code": ".qwen/oauth_creds.json",
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

    const tokenRelPath = OAUTH_TOKEN_PATHS[provider.name];
    if (!tokenRelPath) {
      return Response.json({ hasToken: false, message: "该 Provider 不支持 OAuth" });
    }

    const tokenPath = join(homedir(), tokenRelPath);

    try {
      const raw = await readFile(tokenPath, "utf-8");
      const data = JSON.parse(raw);

      const accessToken = data.access_token || "";
      const expiryMs = data.expiry_date;
      const hasToken = !!accessToken;

      let expired = false;
      let expiresAt: string | null = null;

      if (expiryMs) {
        const expiryDate = new Date(expiryMs);
        expiresAt = expiryDate.toISOString();
        expired = Date.now() >= expiryMs;
      }

      return Response.json({
        hasToken,
        expired,
        expiresAt,
        tokenPath,
        message: hasToken
          ? expired
            ? "Token 已过期，需要重新登录"
            : `Token 有效${expiresAt ? `，过期时间: ${new Date(expiresAt).toLocaleString("zh-CN")}` : ""}`
          : "Token 文件存在但 access_token 为空",
      });
    } catch {
      return Response.json({
        hasToken: false,
        expired: true,
        expiresAt: null,
        tokenPath,
        message: `Token 文件不存在: ${tokenPath}，请先运行 qwen auth login`,
      });
    }
  } catch (e: unknown) {
    return Response.json({
      error: `查询失败: ${e instanceof Error ? e.message : String(e)}`,
    }, { status: 500 });
  }
}
