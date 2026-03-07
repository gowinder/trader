# AI Trader - Claude Code 项目指南

## 项目概述

AI 量化交易系统，融合 LLM 智能分析和量化策略，支持多交易所合约交易。

## 技术栈

- **后端**: Python 3.12+, asyncio, ccxt, pydantic, pandas, redis, loguru
- **前端**: React 19, React Router 7, TypeScript, Drizzle ORM, TailwindCSS, Radix UI
- **数据库**: PostgreSQL (Drizzle ORM) + SQLite (LLM 用量)
- **缓存/消息**: Redis
- **部署**: Docker Compose (4 个服务: db-migrate, trader, reflection, dashboard)
- **包管理**: uv (Python), npm (前端)

## 项目结构

```
src/ai_trader/           # Python 后端
  scheduler.py           # 主调度器（核心入口）
  config.py              # 配置管理 (pydantic-settings)
  main.py                # 程序入口
  ai/                    # LLM 决策引擎
    providers/           # LLM 供应商: openrouter, deepseek, glm, gemini, qwen, codex
    decision.py          # 交易决策引擎
    hybrid_decision.py   # 混合决策（AI+量化）
    token_manager.py     # Token 计费
  exchange/              # 交易所适配: weex, binance, bybit, okx
  strategies/            # 量化策略: 趋势跟随, 均值回归, 突破等
  events/                # 事件驱动系统（市场事件检测+触发）
  advisory/              # AI 顾问系统（多触发条件）
  persistence/           # 数据持久化层
  prompts/               # LLM 提示词模板
  optimization/          # 影子交易+参数优化
  sentiment/             # 情绪分析（CryptoPanic, NewsAPI）
  memory/                # 交易记忆与反思
  notification/          # 通知系统
  models/                # 数据模型

dashboard/               # React 前端
  app/routes/            # API 端点 + 页面路由 (55+)
  app/components/        # React 组件
  app/services/          # API 客户端
  db/schema.ts           # 数据库 Schema 定义
  db/migrations/         # 数据库迁移

tests/                   # pytest 测试
docs/plans/              # 设计文档
```

## 常用命令

```bash
# 后端运行
uv run python -m ai_trader.main

# 前端开发
cd dashboard && npm run dev

# 测试
uv run pytest tests/ -v

# Docker 部署
docker-compose up -d

# 数据库迁移
cd dashboard && npm run db:push
```

## 开发规范

- 后端配置通过 `.env` + `pydantic-settings` 管理，参考 `.env.example`
- 前端 API 端点在 `dashboard/app/routes/api.*.ts`
- 前端页面路由在 `dashboard/app/routes/dashboard.*.tsx`
- 数据库 Schema 在 `dashboard/db/schema.ts`，修改后需运行迁移
- LLM Provider 实现在 `src/ai_trader/ai/providers/`，遵循工厂模式
- 交易所适配在 `src/ai_trader/exchange/`，使用 ccxt 统一接口
- 所有交易决策经过 HybridDecisionEngine 融合 AI 和量化信号

## 关键配置

- `TRADING_MODE`: testnet / live
- `EXCHANGE_TYPE`: weex / binance / bybit / okx
- `LLM_PROVIDER`: openrouter / deepseek / glm / gemini / qwen / codex
- `QUANT_WEIGHT` / `AI_WEIGHT`: 量化与 AI 权重比例
- Dashboard 端口: 3500 (映射容器 3000)

## 注意事项

- scheduler.py 是核心文件（3500+ 行），修改需谨慎
- 交易相关代码涉及真实资金，修改风控逻辑前务必确认
- LLM Provider 支持 OAuth 认证（Gemini, Qwen, Codex），token 持久化在 Docker volume
- Redis 用于 trader ↔ dashboard 实时通信（Pub/Sub）
- 前端使用 SSR (React Router v7)，API 路由同时处理 loader 和 action
