# AI Trader

AI 驱动的加密货币合约量化交易系统，融合 LLM 智能分析与传统量化策略。

## 特性

- **混合决策引擎** — AI (LLM) + 量化信号融合，权重可调
- **多 LLM 供应商** — OpenRouter / Deepseek / GLM / Gemini / Qwen / Codex，支持自动 Fallback
- **多交易所支持** — WEEX / Binance / Bybit / OKX (基于 ccxt)
- **事件驱动** — 市场事件实时检测，自动触发 LLM 决策
- **AI 顾问系统** — 多种触发条件（定时/价格波动/连续亏损/浮亏/情绪变化）+ Telegram 通知
- **量化策略库** — 趋势跟随、均值回归、突破策略 + K线形态识别 + 市场状态分类
- **完整风控** — 每日亏损限制、连续止损休息、信号间隔控制、反向交易冷却
- **影子交易** — 新参数虚拟运行验证
- **情绪分析** — CryptoPanic + NewsAPI + LLM 情绪评分
- **交易记忆与反思** — 历史决策评分与改进
- **Dashboard** — React 全功能管理面板（策略编辑、实时图表、决策历史、日志查看、LLM 用量统计）

## 技术栈

| 层 | 技术 |
|---|------|
| 后端 | Python 3.12+, asyncio, ccxt, pydantic, pandas, redis |
| 前端 | React 19, React Router 7, TypeScript, TailwindCSS, Radix UI |
| 数据库 | PostgreSQL (Drizzle ORM) + SQLite |
| 缓存/消息 | Redis (Pub/Sub) |
| 部署 | Docker Compose |

## 快速开始

### 环境要求

- Python 3.12+
- Node.js 18+
- PostgreSQL
- Redis
- Docker & Docker Compose (生产部署)

### 配置

```bash
cp .env.example .env
# 编辑 .env，填入交易所 API Key、LLM API Key 等配置
```

### Docker 部署 (推荐)

```bash
docker-compose up -d
```

服务列表：
- **trader** — 交易机器人主程序
- **dashboard** — 管理面板 (http://localhost:3500)
- **reflection** — 反思/优化后台服务
- **db-migrate** — 数据库迁移 (启动后自动退出)

### 本地开发

```bash
# 后端
uv sync
uv run python -m ai_trader.main

# 前端
cd dashboard
npm install
npm run dev
```

### 测试

```bash
uv run pytest tests/ -v
```

## 配置说明

| 配置项 | 说明 | 示例值 |
|--------|------|--------|
| `EXCHANGE_TYPE` | 交易所类型 | weex / binance / bybit / okx |
| `TRADING_MODE` | 交易模式 | testnet / live |
| `LLM_PROVIDER` | LLM 供应商 | openrouter / deepseek / glm / gemini / qwen |
| `LLM_MODEL` | 主模型 | deepseek/deepseek-v3.2 |
| `LLM_FALLBACK_MODEL` | 备用模型 | deepseek/deepseek-chat |
| `LEVERAGE_MIN/MAX/DEFAULT` | 杠杆范围 | 3 / 10 / 5 |
| `STOP_LOSS_PERCENT` | 止损比例 | 5.0 |
| `TAKE_PROFIT_PERCENT` | 止盈比例 | 10.0 |
| `ADVISORY_ENABLED` | 启用 AI 顾问 | false |
| `ENABLE_DECISION_PERSISTENCE` | 启用决策持久化 | false |

完整配置参考 `.env.example`。

## 项目结构

```
src/ai_trader/          # Python 后端核心
  ai/                   # LLM 决策引擎 + 多供应商适配
  exchange/             # 交易所适配层
  strategies/           # 量化策略库
  events/               # 事件驱动系统
  advisory/             # AI 顾问系统
  persistence/          # 数据持久化
  prompts/              # LLM 提示词模板
  optimization/         # 参数优化 + 影子交易
  sentiment/            # 情绪分析
  memory/               # 交易记忆与反思
  scheduler.py          # 主调度器
  config.py             # 配置管理

dashboard/              # React 管理面板
  app/routes/           # API 端点 + 页面路由
  db/schema.ts          # 数据库 Schema

tests/                  # 测试
docs/plans/             # 设计文档
```

## License

Private
