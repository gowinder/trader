# Dashboard 密码修改功能 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在 Dashboard Settings 页面增加密码修改功能，密码用 bcrypt 哈希存储在 PostgreSQL 中。

**Architecture:** 新增 `system_settings` 表存储哈希密码，改造 `auth.server.ts` 为异步 bcrypt 验证，新增修改密码 API，Settings 页面增加密码修改表单。启动时从环境变量初始化密码到数据库。

**Tech Stack:** React Router v7, Drizzle ORM, PostgreSQL, bcryptjs, shadcn/ui 风格

---

### Task 1: 安装 bcryptjs 依赖

**Files:**
- Modify: `dashboard/package.json`

**Step 1: 安装依赖**

Run: `cd /Users/gowinder/code/gowinder/trader/dashboard && npm install bcryptjs && npm install -D @types/bcryptjs`

**Step 2: 确认安装成功**

Run: `cd /Users/gowinder/code/gowinder/trader/dashboard && node -e "require('bcryptjs')"`
Expected: 无报错

**Step 3: Commit**

```bash
git add dashboard/package.json dashboard/package-lock.json
git commit -m "feat: add bcryptjs dependency for password hashing"
```

---

### Task 2: 新增 system_settings 表

**Files:**
- Modify: `dashboard/db/schema.ts` (末尾添加)

**Step 1: 在 schema.ts 末尾添加表定义**

在 `dashboard/db/schema.ts` 文件末尾（`llmRoutingConfig` 表之后）添加：

```typescript
// ==================== 系统设置 ====================

export const systemSettings = pgTable("system_settings", {
  key: varchar("key", { length: 50 }).primaryKey(),
  value: text("value").notNull(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
});
```

**Step 2: 生成迁移并推送到数据库**

Run: `cd /Users/gowinder/code/gowinder/trader/dashboard && npx drizzle-kit generate && npx drizzle-kit migrate`

Expected: 生成迁移文件，表创建成功

**Step 3: Commit**

```bash
git add dashboard/db/schema.ts dashboard/db/migrations/
git commit -m "feat: add system_settings table for password storage"
```

---

### Task 3: 改造 auth.server.ts

**Files:**
- Modify: `dashboard/app/services/auth.server.ts`

**Step 1: 重写 auth.server.ts**

将 `dashboard/app/services/auth.server.ts` 改造为：

```typescript
import { createCookieSessionStorage, redirect } from "react-router";
import bcrypt from "bcryptjs";
import { db } from "../../db";
import { systemSettings } from "../../db/schema";
import { eq } from "drizzle-orm";

const sessionSecret = process.env.SESSION_SECRET;
if (!sessionSecret) {
  throw new Error("SESSION_SECRET must be set");
}

const storage = createCookieSessionStorage({
  cookie: {
    name: "_session",
    httpOnly: true,
    maxAge: 60 * 60 * 24 * 7, // 7 days
    path: "/",
    sameSite: "lax",
    secrets: [sessionSecret],
    secure: process.env.COOKIE_SECURE === "true",
  },
});

const SALT_ROUNDS = 12;
const PASSWORD_KEY = "dashboard_password";

export async function getSession(request: Request) {
  return storage.getSession(request.headers.get("Cookie"));
}

export async function createUserSession(redirectTo: string) {
  const session = await storage.getSession();
  session.set("authenticated", true);
  session.set("authenticatedAt", Date.now());
  return redirect(redirectTo, {
    headers: {
      "Set-Cookie": await storage.commitSession(session),
    },
  });
}

export async function logout(request: Request) {
  const session = await getSession(request);
  return redirect("/login", {
    headers: {
      "Set-Cookie": await storage.destroySession(session),
    },
  });
}

export async function requireAuth(request: Request) {
  const session = await getSession(request);
  const authenticated = session.get("authenticated");

  if (!authenticated) {
    throw redirect("/login");
  }

  return session;
}

export async function isAuthenticated(request: Request) {
  const session = await getSession(request);
  return session.get("authenticated") === true;
}

export async function initializePassword() {
  const existing = await db
    .select()
    .from(systemSettings)
    .where(eq(systemSettings.key, PASSWORD_KEY));

  if (existing.length > 0) return;

  const envPassword = process.env.DASHBOARD_PASSWORD;
  if (!envPassword) {
    throw new Error("DASHBOARD_PASSWORD must be set for initial setup");
  }

  const hashed = await bcrypt.hash(envPassword, SALT_ROUNDS);
  await db.insert(systemSettings).values({
    key: PASSWORD_KEY,
    value: hashed,
  });
}

export async function verifyPassword(password: string): Promise<boolean> {
  const result = await db
    .select()
    .from(systemSettings)
    .where(eq(systemSettings.key, PASSWORD_KEY));

  if (result.length === 0) {
    throw new Error("Password not initialized");
  }

  return bcrypt.compare(password, result[0].value);
}

export async function changePassword(
  oldPassword: string,
  newPassword: string
): Promise<{ success: boolean; error?: string }> {
  const valid = await verifyPassword(oldPassword);
  if (!valid) {
    return { success: false, error: "旧密码错误" };
  }

  const hashed = await bcrypt.hash(newPassword, SALT_ROUNDS);
  await db
    .update(systemSettings)
    .set({ value: hashed, updatedAt: new Date() })
    .where(eq(systemSettings.key, PASSWORD_KEY));

  return { success: true };
}
```

**Step 2: 更新 login.tsx 中 verifyPassword 调用为 await**

在 `dashboard/app/routes/login.tsx` 第 27 行，将：
```typescript
if (!verifyPassword(password)) {
```
改为：
```typescript
if (!await verifyPassword(password)) {
```

**Step 3: 验证 TypeScript 编译通过**

Run: `cd /Users/gowinder/code/gowinder/trader/dashboard && npx tsc --noEmit`
Expected: 无错误

**Step 4: Commit**

```bash
git add dashboard/app/services/auth.server.ts dashboard/app/routes/login.tsx
git commit -m "feat: migrate password auth to bcrypt with database storage"
```

---

### Task 4: 新增修改密码 API 路由

**Files:**
- Create: `dashboard/app/routes/api.change-password.ts`

**Step 1: 创建 API 路由文件**

创建 `dashboard/app/routes/api.change-password.ts`：

```typescript
import type { Route } from "./+types/api.change-password";
import { requireAuth, changePassword } from "~/services/auth.server";

export async function action({ request }: Route.ActionArgs) {
  await requireAuth(request);

  if (request.method !== "POST") {
    return Response.json({ success: false, error: "Method not allowed" }, { status: 405 });
  }

  const body = await request.json();
  const { oldPassword, newPassword } = body;

  if (!oldPassword || !newPassword) {
    return Response.json({ success: false, error: "请填写所有字段" }, { status: 400 });
  }

  if (newPassword.length < 6) {
    return Response.json({ success: false, error: "新密码至少 6 位" }, { status: 400 });
  }

  const result = await changePassword(oldPassword, newPassword);
  if (!result.success) {
    return Response.json({ success: false, error: result.error }, { status: 400 });
  }

  return Response.json({ success: true });
}
```

**Step 2: 验证 TypeScript 编译通过**

Run: `cd /Users/gowinder/code/gowinder/trader/dashboard && npx tsc --noEmit`
Expected: 无错误

**Step 3: Commit**

```bash
git add dashboard/app/routes/api.change-password.ts
git commit -m "feat: add change-password API endpoint"
```

---

### Task 5: Settings 页面增加密码修改区域

**Files:**
- Modify: `dashboard/app/routes/dashboard.settings.tsx`

**Step 1: 在 Settings 页面组件中添加密码修改状态和逻辑**

在 `SettingsPage` 组件中（约第 78 行 `savingAdvisory` 状态之后）添加：

```typescript
// password change
const [oldPassword, setOldPassword] = useState("");
const [newPassword, setNewPassword] = useState("");
const [confirmPassword, setConfirmPassword] = useState("");
const [changingPassword, setChangingPassword] = useState(false);

const handleChangePassword = async () => {
  if (!oldPassword || !newPassword || !confirmPassword) {
    showToast("error", "请填写所有密码字段");
    return;
  }
  if (newPassword.length < 6) {
    showToast("error", "新密码至少 6 位");
    return;
  }
  if (newPassword !== confirmPassword) {
    showToast("error", "两次输入的新密码不一致");
    return;
  }
  setChangingPassword(true);
  try {
    const res = await fetch("/api/change-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ oldPassword, newPassword }),
    });
    const data = await res.json();
    if (data.success) {
      showToast("success", "密码修改成功");
      setOldPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } else {
      showToast("error", data.error || "密码修改失败");
    }
  } catch {
    showToast("error", "网络错误");
  } finally {
    setChangingPassword(false);
  }
};
```

**Step 2: 在 return JSX 中添加密码修改区域**

在 Settings 页面 return 的 JSX 中，在 LLM 调度配置 section（约第 739 行 `{/* ── Section 2: Routing Config */}`）之后、Add Provider Modal 之前，添加：

```tsx
{/* ── Section 3: Password ──────────────────────────────────── */}
<div>
  <h2 className="text-2xl font-bold mb-4">修改密码</h2>
  <div className="rounded-lg border border-border bg-card p-6 max-w-md">
    <div className="space-y-4">
      <div>
        <label className="block text-sm text-muted-foreground mb-1">旧密码</label>
        <input
          type="password"
          value={oldPassword}
          onChange={(e) => setOldPassword(e.target.value)}
          placeholder="请输入当前密码"
          className={inputCls}
        />
      </div>
      <div>
        <label className="block text-sm text-muted-foreground mb-1">新密码</label>
        <input
          type="password"
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          placeholder="至少 6 位"
          className={inputCls}
        />
      </div>
      <div>
        <label className="block text-sm text-muted-foreground mb-1">确认新密码</label>
        <input
          type="password"
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
          placeholder="再次输入新密码"
          className={inputCls}
        />
      </div>
      <button
        type="button"
        onClick={handleChangePassword}
        disabled={changingPassword}
        className="inline-flex items-center gap-1 px-4 py-1.5 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-50"
      >
        <Save className="h-3.5 w-3.5" /> {changingPassword ? "修改中..." : "修改密码"}
      </button>
    </div>
  </div>
</div>
```

**Step 3: 验证 TypeScript 编译通过**

Run: `cd /Users/gowinder/code/gowinder/trader/dashboard && npx tsc --noEmit`
Expected: 无错误

**Step 4: Commit**

```bash
git add dashboard/app/routes/dashboard.settings.tsx
git commit -m "feat: add password change form to Settings page"
```

---

### Task 6: 添加密码初始化调用

**Files:**
- Modify: `dashboard/app/services/auth.server.ts` (在模块加载时自动调用)

**Step 1: 在 auth.server.ts 末尾添加自动初始化**

在 `auth.server.ts` 末尾添加：

```typescript
// 自动初始化密码（模块加载时执行一次）
initializePassword().catch((err) => {
  console.error("Failed to initialize password:", err.message);
});
```

**Step 2: 验证 TypeScript 编译通过**

Run: `cd /Users/gowinder/code/gowinder/trader/dashboard && npx tsc --noEmit`
Expected: 无错误

**Step 3: Commit**

```bash
git add dashboard/app/services/auth.server.ts
git commit -m "feat: auto-initialize password from env on first startup"
```

---

### Task 7: 手动测试验证

**Step 1: 启动 Dashboard 开发服务器**

Run: `cd /Users/gowinder/code/gowinder/trader/dashboard && npm run dev`

**Step 2: 手动测试检查项**

1. 访问登录页面，使用原有密码登录成功
2. 进入 Settings 页面，确认底部出现「修改密码」区域
3. 测试修改密码：输入旧密码 + 新密码 + 确认密码，提交成功
4. 退出登录，使用新密码登录成功
5. 测试错误场景：旧密码错误、新密码太短、两次密码不一致

**Step 3: Final commit**

```bash
git add -A
git commit -m "feat: dashboard password change feature complete"
```
