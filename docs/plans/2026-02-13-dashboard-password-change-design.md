# Dashboard 密码修改功能设计

## 背景

当前 Dashboard 使用环境变量 `DASHBOARD_PASSWORD` 明文存储密码，修改密码需要手动编辑 `.env` 文件并重启服务。需要在 Dashboard Settings 页面增加密码修改功能，密码使用 bcrypt 哈希后存储在 PostgreSQL 数据库中。

## 设计概览

### 1. 数据库层

在 `dashboard/db/schema.ts` 中新增 `system_settings` 表：

```typescript
export const systemSettings = pgTable("system_settings", {
  key: varchar("key", { length: 50 }).primaryKey(),
  value: text("value").notNull(),
  updatedAt: timestamp("updated_at").defaultNow().notNull(),
});
```

用 `key = 'dashboard_password'` 存储 bcrypt 哈希密码。

### 2. 认证逻辑改造

修改 `dashboard/app/services/auth.server.ts`：

- **`verifyPassword(password: string): Promise<boolean>`** — 改为异步，从数据库读取哈希密码，用 bcrypt 比对
- **`changePassword(oldPassword: string, newPassword: string): Promise<boolean>`** — 验证旧密码，bcrypt 哈希新密码，更新数据库
- **`initializePassword(): Promise<void>`** — 启动时检查数据库，无记录则从 `DASHBOARD_PASSWORD` 环境变量哈希后写入

bcrypt salt rounds: 12，依赖包：`bcryptjs`。

### 3. 密码初始化

应用启动时调用 `initializePassword`：
- 查询 `system_settings` 中 `key = 'dashboard_password'` 是否存在
- 不存在：读取 `DASHBOARD_PASSWORD` 环境变量，bcrypt 哈希后插入数据库
- 已存在：跳过，不做任何操作
- 环境变量未设置且数据库无记录：抛出错误

初始化完成后，环境变量不再参与密码验证。

### 4. API 路由

新增 `dashboard/app/routes/api.change-password.ts`：

- 方法：POST
- 请求体：`{ oldPassword: string, newPassword: string }`
- 需要 session 认证保护
- 返回：`{ success: boolean, error?: string }`
- 流程：验证 session → 验证旧密码 → 哈希新密码 → 更新数据库

### 5. Settings 页面 UI

在现有 Settings 页面中增加「修改密码」区域：

- 三个输入框：旧密码、新密码、确认新密码
- 前端校验：新密码最少 6 位，两次输入一致
- 提交后显示成功/失败提示（toast）
- 成功后清空输入框，无需强制重新登录

## 文件改动清单

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `dashboard/db/schema.ts` | 修改 | 新增 `system_settings` 表定义 |
| `dashboard/app/services/auth.server.ts` | 修改 | 改造验证逻辑，新增 changePassword、initializePassword |
| `dashboard/app/routes/api.change-password.ts` | 新增 | 修改密码 API |
| `dashboard/app/routes/settings.tsx` | 修改 | 增加密码修改表单区域 |
| `dashboard/package.json` | 修改 | 新增 bcryptjs 依赖 |

## 依赖新增

- `bcryptjs`：纯 JS 实现的 bcrypt，无需编译原生模块
- `@types/bcryptjs`：TypeScript 类型定义
