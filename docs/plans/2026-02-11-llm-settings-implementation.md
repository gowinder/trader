# LLM Settings Dashboard 实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在 Dashboard settings 页面实现完整的 LLM Provider 配置管理界面，替代 .env 手动配置。

**Architecture:** PostgreSQL 存储加密的 Provider 配置，Dashboard 提供 CRUD API 和配置 UI，保存时同步到 Redis 并通过 PubSub 通知 trader 热加载。完全向后兼容 .env 配置。

**Tech Stack:** React Router 7 + Drizzle ORM + PostgreSQL + Redis PubSub + Node.js crypto (AES-256-GCM) + Python asyncio

---

## Task 1: 加密工具模块

**Files:**
- Create: `dashboard/app/lib/encryption.ts`

**Step 1: 创建 AES-256-GCM 加密工具**

```typescript
// dashboard/app/lib/encryption.ts
import { createCipheriv, createDecipheriv, randomBytes } from "crypto";

const ALGORITHM = "aes-256-gcm";

function getKey(): Buffer {
  const key = process.env.ENCRYPTION_KEY;
  if (!key) throw new Error("ENCRYPTION_KEY environment variable is required");
  // 支持 hex 编码的 32 字节密钥
  if (key.length === 64) return Buffer.from(key, "hex");
  // 或直接使用 32 字节字符串
  if (key.length === 32) return Buffer.from(key, "utf-8");
  throw new Error("ENCRYPTION_KEY must be 32 bytes (or 64 hex chars)");
}

export function encrypt(plaintext: string): string {
  if (!plaintext) return "";
  const key = getKey();
  const iv = randomBytes(12);
  const cipher = createCipheriv(ALGORITHM, key, iv);
  const encrypted = Buffer.concat([cipher.update(plaintext, "utf8"), cipher.final()]);
  const tag = cipher.getAuthTag();
  // 格式: iv:tag:ciphertext (all hex)
  return `${iv.toString("hex")}:${tag.toString("hex")}:${encrypted.toString("hex")}`;
}

export function decrypt(ciphertext: string): string {
  if (!ciphertext) return "";
  const key = getKey();
  const [ivHex, tagHex, encHex] = ciphertext.split(":");
  if (!ivHex || !tagHex || !encHex) throw new Error("Invalid ciphertext format");
  const iv = Buffer.from(ivHex, "hex");
  const tag = Buffer.from(tagHex, "hex");
  const encrypted = Buffer.from(encHex, "hex");
  const decipher = createDecipheriv(ALGORITHM, key, iv);
  decipher.setAuthTag(tag);
  return Buffer.concat([decipher.update(encrypted), decipher.final()]).toString("utf8");
}

export function maskApiKey(key: string): string {
  if (!key || key.length <= 4) return "****";
  return "****" + key.slice(-4);
}
```

**Step 2: 更新 .env.example**

在 `.env.example` 末尾添加：

```bash
# ============= 加密配置 =============
# 用于加密 API Key 等敏感数据，32 字节字符串或 64 位 hex
# 可通过 node -e "console.log(require('crypto').randomBytes(32).toString('hex'))" 生成
ENCRYPTION_KEY=
```

**Step 3: Commit**

```bash
git add dashboard/app/lib/encryption.ts .env.example
git commit -m "feat: add AES-256-GCM encryption utility for API key storage"
```

---

## Task 2: 数据库 Schema 和迁移

**Files:**
- Modify: `dashboard/db/schema.ts` — 在文件末尾添加新表定义

**Step 1: 在 schema.ts 末尾添加 llmProviders 表**

在 `dashboard/db/schema.ts` 末尾追加：

```typescript
// ==================== LLM Provider 配置 ====================

export const llmProviders = pgTable("llm_providers", {
  id: integer("id").primaryKey().generatedAlwaysAsIdentity(),
  name: varchar("name", { length: 50 }).notNull().unique(),
  displayName: varchar("display_name", { length: 100 }).notNull(),
  providerType: varchar("provider_type", { length: 30 }).notNull(), // openai_compatible | anthropic_compatible | gemini_native
  apiKeyEncrypted: text("api_key_encrypted"),
  baseUrl: varchar("base_url", { length: 500 }),
  timeout: integer("timeout").notNull().default(60),
  models: jsonb("models").$type<string[]>().notNull().default([]),
  isBuiltin: boolean("is_builtin").notNull().default(false),
  isEnabled: boolean("is_enabled").notNull().default(true),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
});

export const llmRoutingConfig = pgTable("llm_routing_config", {
  id: integer("id").primaryKey().generatedAlwaysAsIdentity(),
  scope: varchar("scope", { length: 30 }).notNull(), // main | advisory
  providerId: integer("provider_id").notNull().references(() => llmProviders.id, { onDelete: "cascade" }),
  model: varchar("model", { length: 100 }).notNull(),
  priority: integer("priority").notNull().default(0),
  isEnabled: boolean("is_enabled").notNull().default(true),
});
```

**Step 2: 生成 Drizzle migration**

```bash
cd /Users/gowinder/code/gowinder/trader/dashboard && npx drizzle-kit generate
```

Expected: 在 `dashboard/db/migrations/` 下生成新的 SQL 迁移文件。

**Step 3: 执行迁移**

```bash
cd /Users/gowinder/code/gowinder/trader/dashboard && npx drizzle-kit push
```

**Step 4: Commit**

```bash
git add dashboard/db/schema.ts dashboard/db/migrations/
git commit -m "feat: add llm_providers and llm_routing_config tables"
```

---

## Task 3: Provider CRUD API

**Files:**
- Create: `dashboard/app/routes/api.llm-config.providers.ts`
- Modify: `dashboard/app/routes.ts` — 添加新路由

**Step 1: 创建 Provider API**

```typescript
// dashboard/app/routes/api.llm-config.providers.ts
import type { ActionFunctionArgs, LoaderFunctionArgs } from "react-router";
import { db } from "~/db/client";
import { llmProviders } from "~/db/schema";
import { eq } from "drizzle-orm";
import { encrypt, decrypt, maskApiKey } from "~/lib/encryption";
import { createClient } from "redis";

// 预定义 Provider 列表
const BUILTIN_PROVIDERS = [
  { name: "openrouter", displayName: "OpenRouter", providerType: "openai_compatible", baseUrl: "https://openrouter.ai/api/v1", models: ["deepseek/deepseek-chat", "google/gemini-2.0-flash-exp:free", "anthropic/claude-3.5-sonnet"] },
  { name: "deepseek", displayName: "DeepSeek", providerType: "openai_compatible", baseUrl: "https://api.deepseek.com/v1", models: ["deepseek-chat", "deepseek-reasoner"] },
  { name: "gemini", displayName: "Gemini", providerType: "gemini_native", baseUrl: "https://generativelanguage.googleapis.com/v1beta", models: ["gemini-2.0-flash", "gemini-2.5-pro"] },
  { name: "glm", displayName: "智谱 GLM", providerType: "anthropic_compatible", baseUrl: "https://open.bigmodel.cn/api/anthropic", models: ["glm-4-plus", "glm-4-flash"] },
  { name: "qwen", displayName: "通义千问", providerType: "openai_compatible", baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1", models: ["qwen-max", "qwen-plus", "qwen-turbo"] },
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
    }
  }
}

export async function loader(_args: LoaderFunctionArgs) {
  try {
    await ensureBuiltinProviders();
    const rows = await db.select().from(llmProviders).orderBy(llmProviders.id);

    const providers = rows.map((row) => ({
      ...row,
      apiKey: row.apiKeyEncrypted ? maskApiKey(decrypt(row.apiKeyEncrypted)) : "",
      apiKeyEncrypted: undefined, // 不返回加密值
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
      // 新增自定义 Provider
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

      return Response.json({ success: true, provider: result[0] });
    }

    if (request.method === "PUT") {
      // 更新 Provider
      const body = await request.json();
      const { id, displayName, apiKey, baseUrl, timeout, models, isEnabled } = body;

      if (!id) return Response.json({ error: "id is required" }, { status: 400 });

      const updates: Record<string, unknown> = { updatedAt: new Date() };
      if (displayName !== undefined) updates.displayName = displayName;
      if (baseUrl !== undefined) updates.baseUrl = baseUrl || null;
      if (timeout !== undefined) updates.timeout = timeout;
      if (models !== undefined) updates.models = models;
      if (isEnabled !== undefined) updates.isEnabled = isEnabled;
      // apiKey 为空字符串时不更新，非空时更新
      if (apiKey) updates.apiKeyEncrypted = encrypt(apiKey);

      await db.update(llmProviders).set(updates).where(eq(llmProviders.id, id));

      // 保存后同步到 Redis
      await syncToRedis();

      return Response.json({ success: true });
    }

    if (request.method === "DELETE") {
      const body = await request.json();
      const { id } = body;

      // 检查是否为内置 Provider
      const [provider] = await db.select().from(llmProviders).where(eq(llmProviders.id, id));
      if (!provider) return Response.json({ error: "Provider not found" }, { status: 404 });
      if (provider.isBuiltin) return Response.json({ error: "Cannot delete builtin provider" }, { status: 400 });

      await db.delete(llmProviders).where(eq(llmProviders.id, id));
      await syncToRedis();

      return Response.json({ success: true });
    }

    return Response.json({ error: "Method not allowed" }, { status: 405 });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    console.error("LLM config providers API error:", message);
    return Response.json({ error: message }, { status: 500 });
  }
}

async function syncToRedis() {
  // 读取所有启用的 provider 和 routing，同步到 Redis
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

  const redisUrl = process.env.REDIS_URL || "redis://localhost:6379";
  const client = createClient({ url: redisUrl });
  await client.connect();

  // 更新 provider 池信息
  await client.set("llm:providers:pool", JSON.stringify(providersMap));
  await client.publish("llm:config:updated", JSON.stringify({ type: "providers", providers: providersMap }));

  await client.disconnect();
}
```

**Step 2: 在 routes.ts 添加路由**

在 `dashboard/app/routes.ts` 中，在 `route("api/llm-providers", ...)` 后面添加：

```typescript
route("api/llm-config/providers", "routes/api.llm-config.providers.ts"),
route("api/llm-config/routing", "routes/api.llm-config.routing.ts"),
```

**Step 3: 确认 db client 存在**

检查 `dashboard/db/client.ts` 是否存在。如果不存在，需要创建一个复用已有模式的 db client。查看项目中其他 API 如何连接数据库（如 `api.llm-usage.ts`），复用同样的连接方式。

**Step 4: Commit**

```bash
git add dashboard/app/routes/api.llm-config.providers.ts dashboard/app/routes.ts
git commit -m "feat: add LLM provider CRUD API with encryption"
```

---

## Task 4: 调度配置 API

**Files:**
- Create: `dashboard/app/routes/api.llm-config.routing.ts`

**Step 1: 创建调度配置 API**

```typescript
// dashboard/app/routes/api.llm-config.routing.ts
import type { ActionFunctionArgs, LoaderFunctionArgs } from "react-router";
import { db } from "~/db/client";
import { llmProviders, llmRoutingConfig } from "~/db/schema";
import { eq, and } from "drizzle-orm";
import { decrypt } from "~/lib/encryption";
import { createClient } from "redis";

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
    // items: [{ providerId, model, priority }]

    if (!scope || !Array.isArray(items)) {
      return Response.json({ error: "scope and items are required" }, { status: 400 });
    }

    // 删除该 scope 的旧配置，写入新配置
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
  // 读取完整的 routing 配置 + provider 信息
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

  const redisUrl = process.env.REDIS_URL || "redis://localhost:6379";
  const client = createClient({ url: redisUrl });
  await client.connect();

  if (scope === "main") {
    // 构建兼容现有格式的 providers config
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

    // 同时发布兼容旧格式的事件（供现有 scheduler 使用）
    const legacyProviders = routingList.map((r) => ({ name: r.provider, model: r.model }));
    await client.publish("llm:providers:updated", JSON.stringify({ providers: legacyProviders }));
    // 发布新格式事件
    await client.publish("llm:config:updated", JSON.stringify({ type: "routing", scope: "main", config }));
  } else if (scope === "advisory") {
    // Advisory 只取第一个（优先级最高的）
    const first = routing[0];
    if (first) {
      const advisoryConfig = {
        provider: first.providerName,
        model: first.model,
        api_key: first.apiKeyEncrypted ? decrypt(first.apiKeyEncrypted) : "",
        base_url: first.baseUrl || "",
        timeout: first.timeout,
      };
      await client.set("llm:advisory:config", JSON.stringify(advisoryConfig));
      await client.publish("advisory:llm_config:updated", JSON.stringify(advisoryConfig));
    }
  }

  await client.disconnect();
}
```

**Step 2: Commit**

```bash
git add dashboard/app/routes/api.llm-config.routing.ts
git commit -m "feat: add LLM routing config API with Redis sync"
```

---

## Task 5: Settings 前端页面 — Provider 管理区域

**Files:**
- Modify: `dashboard/app/routes/dashboard.settings.tsx` — 完全重写

**Step 1: 实现 Provider 池管理 UI**

重写 `dashboard/app/routes/dashboard.settings.tsx`，实现 Provider 卡片列表：

关键功能点：
1. `useEffect` 加载 `GET /api/llm-config/providers`
2. 每个 Provider 渲染一张卡片，包含：
   - 显示名称 + 启用/禁用开关 + `isBuiltin` 标签
   - API Key 输入框（password type，带 eye toggle 按钮）
   - Base URL 输入框（内置 Provider 把默认值显示为 placeholder）
   - Timeout 数字输入框
   - 模型列表（tag 输入 — input + 回车添加 + x 删除）
   - 保存按钮（`PUT /api/llm-config/providers`）
   - 删除按钮（仅 `isBuiltin=false`，`DELETE /api/llm-config/providers`）
3. 右上角 "添加自定义 Provider" 按钮，弹出表单（使用 `@radix-ui/react-dialog`）：
   - name（唯一标识）
   - displayName
   - providerType 下拉（OpenAI 兼容 / Anthropic 兼容 / Gemini 原生）
   - apiKey / baseUrl / timeout / models
4. Toast 提示保存成功/失败

UI 组件复用：
- `Card` from `~/components/ui/card`
- `Button` from `~/components/ui/button`
- `Input` from `~/components/ui/input`
- `Label` from `~/components/ui/label`
- `Select` from `~/components/ui/select`

参考 `dashboard.advisory-settings.tsx` 的模式：useState + fetch + toast。

**Step 2: Commit**

```bash
git add dashboard/app/routes/dashboard.settings.tsx
git commit -m "feat: implement LLM provider management UI in settings page"
```

---

## Task 6: Settings 前端页面 — 调度配置区域

**Files:**
- Modify: `dashboard/app/routes/dashboard.settings.tsx` — 在 Provider 管理下方追加调度区域

**Step 1: 在 settings 页面添加调度配置区域**

在 Provider 卡片列表下方，添加：

1. 两个并排面板（grid-cols-2）：
   - **主 LLM 调度**：
     - `useEffect` 加载 `GET /api/llm-config/routing?scope=main`
     - 上下拖拽排序列表（使用 ChevronUp/ChevronDown 按钮，参考 `dashboard.llm-usage.tsx` 现有模式）
     - 每行：Provider 名 + 模型下拉（从对应 Provider 的 `models` 字段中选择）
     - "添加 Provider" 按钮，从已启用的 Provider 池中选择
     - 调度策略下拉：`cost_first` / `round_robin` / `priority`
   - **Advisory LLM 调度**：
     - 同样的排序列表，但单选（只取优先级最高的一个生效）
     - 无策略选择

2. 底部统一 "保存调度配置" 按钮：
   - `PUT /api/llm-config/routing` 分别提交 `scope=main` 和 `scope=advisory`

**Step 2: Commit**

```bash
git add dashboard/app/routes/dashboard.settings.tsx
git commit -m "feat: add LLM routing config UI to settings page"
```

---

## Task 7: Trader 端 LLMManager 支持完整配置热加载

**Files:**
- Modify: `src/ai_trader/ai/llm_manager.py:92-109` — 扩展 `_create_provider` 支持动态参数
- Modify: `src/ai_trader/ai/llm_manager.py:364-391` — 扩展 `update_providers` 支持完整配置

**Step 1: 扩展 _create_provider 支持动态 API Key 和 Base URL**

修改 `_create_provider` 方法，接受可选的 `api_key` 和 `base_url` 参数：

```python
def _create_provider(self, name: str, model: Optional[str] = None,
                     api_key: Optional[str] = None, base_url: Optional[str] = None,
                     timeout: Optional[float] = None) -> BaseLLMProvider:
    """创建 Provider 实例，支持动态参数覆盖"""
    if name == "qwen":
        if api_key:
            # 有 API Key 时使用 HTTP Provider
            from .providers.qwen_oauth import QwenOAuthProvider
            return QwenOAuthProvider(model=model or "qwen-max")
        return QwenCLIProvider(model=model or "qwen-max")
    elif name == "gemini":
        if api_key:
            from .providers.gemini import GeminiProvider
            return GeminiProvider(
                api_key=api_key,
                model=model or "gemini-2.0-flash",
                base_url=base_url or "https://generativelanguage.googleapis.com/v1beta",
                timeout=timeout or 60,
            )
        return GeminiCLIProvider(model=model or "gemini-2.0-flash")
    elif name == "codex":
        return CodexOAuthProvider(model=model or "gpt-4o")
    elif name == "openrouter":
        return OpenRouterProvider(
            api_key=api_key or config.openrouter_api_key or config.llm_api_key,
            model=model or config.llm_model,
            fallback_model=config.llm_fallback_model,
        )
    elif name == "deepseek":
        from .providers.deepseek import DeepSeekProvider
        return DeepSeekProvider(
            api_key=api_key or config.llm_api_key,
            model=model or "deepseek-chat",
            base_url=base_url or "https://api.deepseek.com/v1",
            timeout=timeout or 60,
        )
    elif name == "glm":
        from .providers.glm import GLMProvider
        return GLMProvider(
            api_key=api_key or config.llm_api_key,
            model=model or "glm-4-plus",
            base_url=base_url or "https://open.bigmodel.cn/api/anthropic",
            timeout=timeout or 60,
        )
    else:
        # 自定义 Provider — 默认按 OpenAI 兼容协议
        from .providers.base import HTTPBasedProvider
        if not api_key:
            raise ValueError(f"Custom provider '{name}' requires api_key")
        return HTTPBasedProvider(
            api_key=api_key,
            model=model or "default",
            base_url=base_url or "",
            timeout=timeout or 60,
        )
```

**Step 2: 扩展 update_providers 支持完整配置**

修改 `update_providers` 方法以接受包含 `api_key`、`base_url` 等完整信息：

```python
def update_providers(self, provider_list: List[Dict[str, Any]],
                     providers_pool: Optional[Dict[str, Dict[str, Any]]] = None):
    """动态更新 provider 配置（从 Redis 配置）

    provider_list 格式: [{"name": "qwen", "model": "qwen-max"}, ...]
    providers_pool 格式: {"qwen": {"api_key": "...", "base_url": "...", "timeout": 60}, ...}
    """
    new_configs = []
    for i, p in enumerate(provider_list):
        name = p.get("name", "") or p.get("provider", "")
        model = p.get("model")
        if not name:
            continue
        new_configs.append(ProviderConfig(
            name=name,
            priority=i + 1,
            cost_tier="free",
            weight=max(1, len(provider_list) - i),
            model=model,
        ))

    if new_configs:
        self.providers_config = new_configs
        self.strategy = ScheduleStrategy.PRIORITY
        # 清空缓存的 provider 实例，使用新参数重建
        for provider in self._providers.values():
            import asyncio
            try:
                asyncio.get_event_loop().create_task(provider.close())
            except Exception:
                pass
        self._providers.clear()

        # 保存 provider 池信息供 _create_provider 使用
        if providers_pool:
            self._providers_pool = providers_pool

        logger.info(
            f"Provider config updated: "
            f"{[f'{p.name}({p.model})' for p in new_configs]}"
        )
```

**Step 3: 修改 _create_provider 使用 _providers_pool**

在 `_create_provider` 中，从 `self._providers_pool` 获取 API Key 等参数：

```python
def _create_provider(self, name: str, model: Optional[str] = None) -> BaseLLMProvider:
    pool = getattr(self, '_providers_pool', {})
    pool_info = pool.get(name, {})
    api_key = pool_info.get("api_key")
    base_url = pool_info.get("base_url")
    timeout = pool_info.get("timeout")
    # ... 使用这些参数创建 provider（同 Step 1 逻辑）
```

**Step 4: 修改 _get_provider 传递 model**

确保 `_get_provider` 在缓存 key 中包含 model。

**Step 5: Commit**

```bash
git add src/ai_trader/ai/llm_manager.py
git commit -m "feat: extend LLMManager to support full provider config hot-reload"
```

---

## Task 8: Scheduler 配置监听适配

**Files:**
- Modify: `src/ai_trader/scheduler.py:317-334` — 适配新的 `llm:config:updated` 事件

**Step 1: 扩展 _config_listener 处理新事件**

在 `scheduler.py` 的 `_config_listener` 方法中：

1. 在 `pubsub.subscribe(...)` 中添加 `"llm:config:updated"` 频道
2. 添加对 `llm:config:updated` 的处理：

```python
elif channel == "llm:config:updated":
    cfg = json.loads(message["data"])
    update_type = cfg.get("type", "")
    if update_type == "routing" and cfg.get("scope") == "main":
        from .ai.llm_manager import get_llm_manager
        manager = get_llm_manager()
        config_data = cfg.get("config", {})
        providers_pool = config_data.get("providers", {})
        routing = config_data.get("routing", [])
        manager.update_providers(routing, providers_pool=providers_pool)
        logger.info(f"LLM full config updated via llm:config:updated")
    elif update_type == "providers":
        # Provider 池更新，刷新已有连接
        from .ai.llm_manager import get_llm_manager
        manager = get_llm_manager()
        providers_pool = cfg.get("providers", {})
        if hasattr(manager, '_providers_pool'):
            manager._providers_pool = providers_pool
            manager._providers.clear()
            logger.info(f"LLM providers pool refreshed")
```

保留现有的 `llm:providers:updated` 处理逻辑以保持向后兼容。

**Step 2: Commit**

```bash
git add src/ai_trader/scheduler.py
git commit -m "feat: extend scheduler config listener for full LLM config updates"
```

---

## Task 9: DB Client 和路由注册完善

**Files:**
- Possibly create: `dashboard/db/client.ts` — 如果不存在
- Modify: `dashboard/app/routes.ts` — 确认路由注册

**Step 1: 确认或创建 DB client**

检查项目中其他 API 路由如何访问数据库（如 `api.llm-usage.ts` 或 `api.advisory.ts`）。如果使用 `drizzle-orm` 直接连接，创建一个共享的 `db` 实例：

```typescript
// dashboard/db/client.ts
import { drizzle } from "drizzle-orm/postgres-js";
import postgres from "postgres";
import * as schema from "./schema";

const connectionString = process.env.DATABASE_URL!;
const sql = postgres(connectionString);
export const db = drizzle(sql, { schema });
```

如果已有类似文件，直接复用。

**Step 2: 确认 routes.ts 中两个新路由已添加**

```typescript
route("api/llm-config/providers", "routes/api.llm-config.providers.ts"),
route("api/llm-config/routing", "routes/api.llm-config.routing.ts"),
```

**Step 3: Commit**

```bash
git add dashboard/db/client.ts dashboard/app/routes.ts
git commit -m "feat: add db client and register LLM config routes"
```

---

## Task 10: 集成测试和验证

**Step 1: 启动 Dashboard 验证前端页面**

```bash
cd /Users/gowinder/code/gowinder/trader/dashboard && npm run dev
```

访问 `/dashboard/settings`，验证：
- [ ] Provider 卡片正确显示 5 个预定义 Provider
- [ ] 可以编辑 API Key、Base URL、Timeout、模型列表
- [ ] 保存后 toast 提示成功
- [ ] 可以添加自定义 Provider
- [ ] 可以删除自定义 Provider（不能删除预定义的）
- [ ] 调度配置区域可以添加/排序/保存 main 和 advisory 的路由

**Step 2: 验证 Redis 同步**

```bash
redis-cli get "llm:providers:config"
redis-cli get "llm:advisory:config"
```

确认保存后 Redis 中有正确的 JSON 数据。

**Step 3: 验证 Trader 热加载**

启动 trader 后在 Dashboard 修改配置，检查 trader 日志是否输出：
```
LLM full config updated via llm:config:updated
```

**Step 4: 最终 Commit**

如果有修复，统一提交：

```bash
git add -A
git commit -m "fix: integration fixes for LLM settings dashboard"
```
