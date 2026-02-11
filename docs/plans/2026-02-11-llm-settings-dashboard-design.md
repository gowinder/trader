# LLM Settings Dashboard 设计文档

> 日期：2026-02-11
> 目标：在 Dashboard 提供完整的 LLM Provider 配置管理界面，替代 .env 手动配置

## 1. 需求概述

- 在 Dashboard `/settings` 页面管理所有 LLM 参数（API Key、Base URL、Timeout、模型列表等）
- 统一管理主 LLM 和 Advisory LLM 配置
- 预定义常见 Provider + 支持自定义 Provider
- API Key 加密存储于 PostgreSQL，通过 Redis PubSub 热更新到 trader 进程
- 完全向后兼容现有 .env 配置方式

## 2. 数据模型

### 2.1 `llm_providers` 表 — Provider 配置池

| 字段 | 类型 | 说明 |
|------|------|------|
| id | serial PK | 主键 |
| name | varchar(50) UNIQUE | 唯一标识，如 `openrouter`、`deepseek`、`custom-1` |
| display_name | varchar(100) | 显示名称 |
| provider_type | varchar(30) | 协议类型：`openai_compatible` / `anthropic_compatible` / `gemini_native` |
| api_key_encrypted | text | AES-256-GCM 加密的 API Key |
| base_url | varchar(500) | API 端点，预定义 Provider 有默认值 |
| timeout | integer DEFAULT 60 | 超时秒数 |
| models | jsonb | 可用模型列表，如 `["deepseek-chat", "deepseek-reasoner"]` |
| is_builtin | boolean DEFAULT false | 是否为预定义 Provider |
| is_enabled | boolean DEFAULT true | 是否启用 |
| created_at | timestamp | |
| updated_at | timestamp | |

### 2.2 `llm_routing_config` 表 — 调度配置

| 字段 | 类型 | 说明 |
|------|------|------|
| id | serial PK | |
| scope | varchar(30) | `main` 或 `advisory` |
| provider_id | integer FK → llm_providers.id | 关联 Provider |
| model | varchar(100) | 使用的模型名 |
| priority | integer | 优先级排序（数字越小优先级越高） |
| is_enabled | boolean DEFAULT true | |

### 2.3 预定义 Provider 初始数据

| name | display_name | provider_type | 默认 base_url |
|------|-------------|---------------|---------------|
| openrouter | OpenRouter | openai_compatible | https://openrouter.ai/api/v1 |
| deepseek | DeepSeek | openai_compatible | https://api.deepseek.com/v1 |
| gemini | Gemini | gemini_native | https://generativelanguage.googleapis.com/v1beta |
| glm | 智谱 GLM | anthropic_compatible | https://open.bigmodel.cn/api/anthropic |
| qwen | 通义千问 | openai_compatible | https://dashscope.aliyuncs.com/compatible-mode/v1 |

## 3. API 接口

### 3.1 Provider 管理

**`GET /api/llm-config/providers`**
- 返回所有 Provider 列表
- API Key 脱敏（只显示末尾 4 位）

**`POST /api/llm-config/providers`**
- 新增自定义 Provider
- Body: `{ name, display_name, provider_type, api_key, base_url, timeout, models }`

**`PUT /api/llm-config/providers/:id`**
- 更新 Provider 配置
- API Key 为空字符串时不更新（保留原值）

**`DELETE /api/llm-config/providers/:id`**
- 仅可删除自定义 Provider（`is_builtin=false`）
- 预定义 Provider 只能禁用，不可删除

### 3.2 调度配置

**`GET /api/llm-config/routing?scope=main|advisory`**
- 获取指定 scope 的调度链

**`PUT /api/llm-config/routing`**
- 保存调度链
- Body: `{ scope, strategy?, items: [{ provider_id, model, priority }] }`

### 3.3 配置生效流程

```
Dashboard 保存
  → 写入 PostgreSQL（API Key 加密）
  → 同步到 Redis（API Key 解密后写入）
  → 发布 Redis PubSub `llm:config:updated`
  → Trader 接收事件，热加载配置
```

## 4. 加密方案

- 新增环境变量 `ENCRYPTION_KEY`（在 .env 中配置一次，32 字节密钥）
- 算法：AES-256-GCM
- Dashboard 端用 Node.js `crypto` 模块加密/解密
- 入库前加密，读取时解密后脱敏返回前端
- 同步到 Redis 时传递解密后的明文值（内网环境，trader 需要明文使用）

## 5. 前端 UI

### 5.1 页面位置

`/dashboard/settings` 页面（当前为空页面）

### 5.2 布局

页面分两个区域，上下排列：

**区域一：Provider 池管理**

卡片列表，每个 Provider 一张卡片：
- 头部：显示名称 + 启用/禁用开关 + 预定义标签（如有）
- 内容：
  - API Key 输入框（密码模式，带显示/隐藏切换）
  - Base URL 输入框（预定义 Provider 显示默认值为 placeholder）
  - Timeout 数字输入框
  - 模型列表（tag 形式，可添加/删除）
- 底部：保存按钮 | 删除按钮（仅自定义 Provider）

右上角 **"+ 添加自定义 Provider"** 按钮，弹出表单：
- Provider 名称（唯一标识）
- 显示名称
- 协议类型下拉（OpenAI 兼容 / Anthropic 兼容 / Gemini 原生）
- API Key / Base URL / Timeout / 模型列表

**区域二：调度配置**

两个并排面板：

| 主 LLM 调度 | Advisory LLM 调度 |
|---|---|
| 拖拽排序的 Provider 列表 | 拖拽排序的 Provider 列表 |
| 每行：Provider 名 + 模型下拉（从该 Provider 的 models 中选） | 同左 |
| "+ 添加" 从已启用的 Provider 池中选择 | 同左 |
| 调度策略下拉（成本优先 / 轮询 / 优先级） | 无（Advisory 固定单 Provider） |

底部统一 **"保存调度配置"** 按钮。

## 6. 后端对接 & 热加载

### 6.1 Trader 端配置加载优先级

```
Redis 缓存 → PostgreSQL → .env 环境变量（兜底）
```

首次部署时 PG 和 Redis 都为空，系统照常从 .env 启动。用户在 Dashboard 保存配置后，后续都从 PG/Redis 读取。

### 6.2 LLMManager 改造

- 新增 `load_from_config(providers_config)` 方法
- 扩展 `update_providers()`：不仅更新优先级，还更新 Provider 实例的连接参数
- 订阅 `llm:config:updated` 事件（替代现有 `llm:providers:updated`）

### 6.3 AdvisoryLLMClient 改造

- 新增从 Redis 读取 `llm:advisory:config` 的逻辑
- 订阅 `llm:config:updated` 事件，重新初始化客户端

### 6.4 Redis 配置格式

**`llm:providers:config`（主 LLM）：**

```json
{
  "providers": {
    "openrouter": {
      "api_key": "sk-...",
      "base_url": "https://openrouter.ai/api/v1",
      "timeout": 60,
      "models": ["deepseek/deepseek-chat", "google/gemini-2.0-flash-exp:free"]
    }
  },
  "routing": [
    {"provider": "openrouter", "model": "deepseek/deepseek-chat", "priority": 1},
    {"provider": "gemini", "model": "gemini-2.0-flash", "priority": 2}
  ],
  "strategy": "priority"
}
```

**`llm:advisory:config`（Advisory LLM）：**

```json
{
  "provider": "openrouter",
  "model": "deepseek/deepseek-chat",
  "api_key": "sk-...",
  "base_url": "https://openrouter.ai/api/v1",
  "timeout": 120
}
```

## 7. 数据库迁移

- 用 Drizzle ORM 在 `dashboard/db/schema.ts` 中定义 `llm_providers` 和 `llm_routing_config` 表
- 生成 Drizzle migration 文件
- 提供初始化脚本，将 5 个预定义 Provider 写入 `llm_providers` 表（API Key 为空，用户自行填写）

## 8. 涉及文件

### 新增文件
- `dashboard/db/schema.ts` — 新增表定义
- `dashboard/app/routes/api.llm-config.providers.ts` — Provider CRUD API
- `dashboard/app/routes/api.llm-config.routing.ts` — 调度配置 API
- `dashboard/app/routes/dashboard.settings.tsx` — 重写 settings 页面
- `dashboard/app/lib/encryption.ts` — AES-256-GCM 加密工具

### 修改文件
- `src/ai_trader/ai/llm_manager.py` — 新增 `load_from_config()`，扩展热更新逻辑
- `src/ai_trader/advisory/llm_client.py` — 新增 Redis 配置读取和热更新
- `src/ai_trader/config.py` — 配置加载优先级调整
- `.env.example` — 新增 `ENCRYPTION_KEY`
