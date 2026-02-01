# 多 LLM Provider 负载均衡设计

## 概述

解决 OpenRouter 免费模型 429 限流问题，通过集成多个 LLM Provider（gemini-cli, codex cli, qwen-code, opencode）实现负载均衡、成本优化和故障转移。

## 目标

1. **负载均衡**：多个 provider 轮询，分散请求压力
2. **成本优化**：优先使用免费的 CLI 工具，付费模型作为备用
3. **故障转移**：主模型限流/失败时自动切换

## 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                    LLMManager                           │
│  (负载均衡 + 成本优化 + 故障转移)                          │
├─────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐      │
│  │ OpenRouter  │  │ Gemini CLI  │  │ Codex CLI   │      │
│  │ Provider    │  │ Provider    │  │ Provider    │      │
│  └─────────────┘  └─────────────┘  └─────────────┘      │
│  ┌─────────────┐  ┌─────────────┐                       │
│  │ Qwen        │  │ OpenCode    │                       │
│  │ Provider    │  │ Provider    │                       │
│  └─────────────┘  └─────────────┘                       │
├─────────────────────────────────────────────────────────┤
│  ┌─────────────────────┐  ┌─────────────────────┐       │
│  │ TokenManager        │  │ UsageTracker        │       │
│  │ (OAuth 刷新)        │  │ (调用统计/费用)      │       │
│  └─────────────────────┘  └─────────────────────┘       │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│  Dashboard (统计图表展示)                                │
└─────────────────────────────────────────────────────────┘
```

### 核心组件

- **LLMManager**: 统一入口，实现轮询/成本优先/故障转移策略
- **TokenManager**: 管理 OAuth token，定期检查过期并刷新
- **UsageTracker**: 记录每次调用的 token 消耗和费用

## Provider 配置

### Token 文件路径

| Provider | Token 文件 | API 端点 |
|----------|-----------|----------|
| gemini | `~/.gemini/oauth_creds.json` | `https://generativelanguage.googleapis.com/v1beta` |
| codex | `~/.codex/auth.json` | `https://api.openai.com/v1` |
| qwen | `~/.qwen/oauth_creds.json` | `https://portal.qwen.ai/api` |
| opencode | `~/.codex/auth.json` (复用) | `https://api.openai.com/v1` |
| openrouter | API Key | `https://openrouter.ai/api/v1` |

### 调度策略配置

```python
providers_config = {
    "strategy": "cost_first",  # cost_first | round_robin | priority

    "providers": [
        # 免费优先，qwen 为默认
        {"name": "qwen", "priority": 1, "cost_tier": "free", "weight": 4, "default": True},
        {"name": "gemini", "priority": 1, "cost_tier": "free", "weight": 3},
        {"name": "codex", "priority": 1, "cost_tier": "free", "weight": 3},
        {"name": "opencode", "priority": 1, "cost_tier": "free", "weight": 2},
        # 付费备用
        {"name": "openrouter", "priority": 2, "cost_tier": "paid", "weight": 1,
         "model": "deepseek/deepseek-v3.2"},
    ],

    # 故障处理
    "retry": {
        "max_retries": 3,
        "backoff_seconds": [1, 5, 15],
        "cooldown_on_429": 60,  # 限流后冷却时间(秒)
    }
}
```

### 调度逻辑

1. **cost_first** (默认): 按 cost_tier 分组，免费组内按 weight 轮询，用尽后才用付费
2. **round_robin**: 所有 provider 按 weight 加权轮询
3. **priority**: 严格按 priority 顺序，失败才用下一个

## Token 管理

### 主动刷新机制

1. 启动时加载所有 token，检查 `expiry_date`
2. 后台任务每 5 分钟检查，过期前 10 分钟自动刷新
3. 刷新失败时标记 provider 为不可用，降级到下一个

### 刷新策略（混合方式）

1. 优先使用 refresh_token 直接调用 OAuth API 刷新
2. API 刷新失败时，调用 CLI 命令刷新：
   - gemini: `gemini auth refresh`
   - codex: `codex auth refresh`
   - qwen: `qwen auth refresh`

### TokenManager 接口

```python
class TokenManager:
    async def get_token(self, provider: str) -> str:
        """获取有效 token，自动刷新过期的"""

    async def refresh_token(self, provider: str) -> bool:
        """刷新指定 provider 的 token"""

    async def check_and_refresh_all(self):
        """检查并刷新所有即将过期的 token"""

    def is_available(self, provider: str) -> bool:
        """检查 provider 是否可用"""
```

## 调用统计与费用追踪

### 数据模型

```python
class LLMUsageRecord:
    id: int
    timestamp: datetime
    provider: str          # gemini, codex, qwen, openrouter
    model: str             # 具体模型名
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float        # 预估费用(美元)
    latency_ms: int        # 响应延迟
    success: bool
    error_message: str     # 失败原因
```

### 价格配置

文件路径: `config/llm_pricing.json`

```json
{
    "openrouter": {
        "deepseek/deepseek-v3.2": {"input": 0.14, "output": 0.28},
        "deepseek/deepseek-chat": {"input": 0.14, "output": 0.28}
    },
    "gemini": {
        "gemini-2.0-flash": {"input": 0, "output": 0}
    },
    "codex": {
        "gpt-4o": {"input": 2.5, "output": 10}
    },
    "qwen": {
        "qwen-max": {"input": 0, "output": 0}
    }
}
```

价格单位: USD per 1M tokens

### 价格更新策略

1. 配置文件为主要数据源
2. 支持从 OpenRouter API 自动更新价格（定期拉取）
3. 免费 Provider 价格固定为 0

## Dashboard 统计图表

### 路由

`/dashboard/llm-usage`

### 页面布局

```
┌─────────────────────────────────────────────────────────────┐
│  LLM Usage Dashboard                                        │
├─────────────────────────────────────────────────────────────┤
│  [汇总卡片]                                                 │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌─────────────┐ │
│  │ 总计调用  │ │ 总计Token │ │ 总计费用  │ │ 今日费用    │ │
│  │  12,456   │ │   8.5M    │ │  $45.67   │ │   $0.12     │ │
│  └───────────┘ └───────────┘ └───────────┘ └─────────────┘ │
├─────────────────────────────────────────────────────────────┤
│  [每日 Token 消耗曲线]                    时间范围: [30天 ▼]│
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Token│                    ╱╲                        │   │
│  │      │        ╱╲    ╱╲   ╱  ╲   ╱╲                 │   │
│  │      │   ╱╲  ╱  ╲  ╱  ╲─╱    ╲─╱  ╲               │   │
│  │      │  ╱  ╲╱    ╲╱                  ╲──           │   │
│  │      └────────────────────────────────────── 日期  │   │
│  └─────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│  [每日费用曲线 - 堆叠面积图]                                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │   $ │ ▓▓                      ▓▓                    │   │
│  │     │ ▓▓▒▒          ▓▓      ▓▓▒▒▒                  │   │
│  │     │ ▓▓▒▒▒▒  ▓▓   ▓▓▒▒    ▓▓▒▒▒▒▒                │   │
│  │     │ ▓▓▒▒▒▒▒▓▓▒▒ ▓▓▒▒▒▒  ▓▓▒▒▒▒▒▒▒               │   │
│  │     └────────────────────────────────────── 日期   │   │
│  │     ▓ openrouter  ▒ codex  (qwen/gemini 免费不显示) │   │
│  └─────────────────────────────────────────────────────┘   │
├──────────────────────────┬──────────────────────────────────┤
│ [Provider 占比 - 饼图]   │ [Provider 费用统计 - 柱状图]     │
│   按调用次数/Token 切换  │   显示各 Provider 累计费用       │
└──────────────────────────┴──────────────────────────────────┤
│  [历史记录表格]                              [导出 CSV]     │
│  时间 | Provider | Model | Input | Output | 费用 | 状态    │
└─────────────────────────────────────────────────────────────┘
```

### 统计指标

**汇总卡片：**
- 总计调用次数（历史累计）
- 总计 Token 消耗（历史累计）
- 总计费用（历史累计）
- 今日费用

**图表：**
- 每日 Token 消耗曲线（折线图）
- 每日费用曲线（按 Provider 堆叠面积图）
- Provider 占比（饼图，支持调用次数/Token 切换）
- Provider 费用统计（柱状图）

**表格：**
- 历史调用记录，支持分页和导出 CSV

### 技术实现

- 图表库: Recharts (复用现有 Dashboard)
- API 端点: `/api/llm-usage/stats`, `/api/llm-usage/records`

## 文件结构

```
src/ai_trader/ai/
├── llm_manager.py          # LLMManager 主类
├── token_manager.py        # TokenManager OAuth 管理
├── usage_tracker.py        # UsageTracker 统计追踪
├── providers/
│   ├── base.py             # (已有) 基类
│   ├── openrouter.py       # (已有) OpenRouter
│   ├── gemini_oauth.py     # 新增: Gemini OAuth Provider
│   ├── codex_oauth.py      # 新增: Codex OAuth Provider
│   ├── qwen_oauth.py       # 新增: Qwen OAuth Provider
│   └── opencode_oauth.py   # 新增: OpenCode Provider

config/
├── llm_providers.yaml      # Provider 配置
└── llm_pricing.json        # 价格配置

dashboard/app/routes/
└── dashboard.llm-usage.tsx # Dashboard 页面
```

## 实现步骤

### Phase 1: 基础设施
1. 切换 OpenRouter 模型到 `deepseek/deepseek-v3.2`
2. 实现 TokenManager 和 OAuth token 读取
3. 实现 token 主动刷新机制（API + CLI 混合）

### Phase 2: Provider 集成
4. 实现 GeminiOAuthProvider
5. 实现 CodexOAuthProvider
6. 实现 QwenOAuthProvider
7. 实现 LLMManager 调度逻辑

### Phase 3: 统计追踪
8. 实现 UsageTracker 和数据库模型
9. 创建价格配置文件
10. 集成到现有 LLM 调用流程

### Phase 4: Dashboard
11. 实现 API 端点
12. 实现 Dashboard 页面和图表

## 配置示例

### 环境变量

```bash
# 默认 Provider
LLM_PROVIDER=qwen

# OpenRouter 备用
OPENROUTER_API_KEY=sk-xxx
LLM_MODEL=deepseek/deepseek-v3.2
LLM_FALLBACK_MODEL=deepseek/deepseek-chat

# OAuth token 路径 (可选，有默认值)
GEMINI_TOKEN_PATH=~/.gemini/oauth_creds.json
CODEX_TOKEN_PATH=~/.codex/auth.json
QWEN_TOKEN_PATH=~/.qwen/oauth_creds.json
```

### 运行时切换

```python
# 通过 LLMManager 使用
manager = LLMManager()
response = await manager.chat(messages)  # 自动选择最优 provider

# 强制使用指定 provider
response = await manager.chat(messages, provider="openrouter")
```
