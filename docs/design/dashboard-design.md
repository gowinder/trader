# Trader Dashboard 设计文档

## 1. 项目概述

### 1.1 目标

为 AI Trader 系统构建一个现代化的 Web Dashboard，用于：

- 实时监控交易状态和持仓情况
- 查看 AI 决策详情和历史记录
- 分析交易绩效和统计数据
- 管理系统配置和风控参数
- 执行回测和对比分析

### 1.2 核心需求

1. **数据持久化** - 将每次交易决策（理由、参数、LLM 输出、仓位、分析结果）写入数据库
2. **决策展示** - 查看每次决策的详细情况、PnL、胜率、仓位记录
3. **UI/UX** - 现代化金融风格，深色主题，响应式设计
4. **技术栈** - 不限于 Python，采用最适合的技术方案

---

## 2. 技术架构

### 2.1 整体架构

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Python Trader  │────▶│   PostgreSQL    │◀────│   Dashboard     │
│   (现有系统)     │     │    Database     │     │    (Remix)      │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                       ▲                       │
        │                       │                       │
        ▼                       │                       ▼
   WebSocket Server        Drizzle ORM            React + SSE
   (FastAPI/决策推送)                            (实时数据展示)
```

### 2.2 技术栈

| 层级 | 技术选型 | 说明 |
|------|----------|------|
| **前端框架** | Remix (React Router v7) | SSR、loader/action 模式、嵌套路由 |
| **UI 组件** | shadcn/ui + Radix UI | 现代化、可定制、无障碍 |
| **样式方案** | Tailwind CSS | 原子化 CSS、深色主题 |
| **图表库** | TradingView Lightweight Charts + Recharts | K线图 + 统计图表 |
| **状态管理** | Zustand | 轻量级状态管理 |
| **数据库** | PostgreSQL | 可靠的关系型数据库 |
| **ORM** | Drizzle | 类型安全、接近原生 SQL |
| **实时数据** | SSE + WebSocket | SSE 用于决策推送，WS 用于 K 线 |
| **部署** | Docker 自托管 | 完全掌控 |

### 2.3 为什么选择这些技术

**Remix vs Next.js:**
- loader/action 模式更直观
- 嵌套路由天然适合 Dashboard 布局
- 更接近 Web 标准，渐进增强

**Drizzle vs Prisma:**
- 金融系统需要精确 SQL 控制
- 无运行时引擎开销
- 类型推断更精确

---

## 3. 数据库设计

### 3.1 ER 图

```
decisions (核心)
    ├── technical_snapshots (1:1)
    ├── risk_snapshots (1:1)
    ├── sentiment_snapshots (1:1)
    └── orders (1:0..1)
         └── position_history (N:1 入场/出场)

backtests
    ├── backtest_trades (1:N)
    └── backtest_equity (1:N)

alert_settings (1:1)
alert_history (独立)

correlation_cache (独立)
price_history (独立)

operation_logs (审计)
```

### 3.2 表结构

#### 3.2.1 决策相关

```sql
-- 交易决策记录（核心表）
CREATE TABLE decisions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- 基础信息
    symbol              VARCHAR(20) NOT NULL,
    timeframe           VARCHAR(10) NOT NULL,

    -- 决策结果
    action              VARCHAR(20) NOT NULL,  -- open_long, close_short, hold...
    confidence          SMALLINT NOT NULL,     -- 0-100
    leverage            DECIMAL(4,1),
    position_size_pct   DECIMAL(5,2),
    entry_price         DECIMAL(20,8),
    stop_loss           DECIMAL(20,8),
    take_profit         DECIMAL(20,8),
    reasoning           TEXT,

    -- LLM 原始输出
    llm_provider        VARCHAR(30),
    llm_model           VARCHAR(50),
    llm_raw_output      TEXT,
    llm_tokens_used     INTEGER,

    -- 关联
    order_id            UUID REFERENCES orders(id)
);

CREATE INDEX idx_decisions_symbol_time ON decisions(symbol, created_at DESC);

-- 技术分析快照
CREATE TABLE technical_snapshots (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    decision_id         UUID NOT NULL REFERENCES decisions(id) ON DELETE CASCADE,

    -- 趋势
    trend               VARCHAR(20),
    trend_confidence    SMALLINT,
    signal_strength     VARCHAR(20),

    -- 指标
    price               DECIMAL(20,8),
    rsi                 DECIMAL(6,2),
    macd                DECIMAL(20,8),
    macd_signal         DECIMAL(20,8),
    ma7                 DECIMAL(20,8),
    ma25                DECIMAL(20,8),
    ma99                DECIMAL(20,8),
    atr                 DECIMAL(20,8),
    boll_upper          DECIMAL(20,8),
    boll_lower          DECIMAL(20,8),

    -- 支撑阻力
    support_levels      JSONB,
    resistance_levels   JSONB,

    -- 其他
    volume_trend        VARCHAR(20),
    pattern             VARCHAR(50),
    key_observations    JSONB
);

-- 风险评估快照
CREATE TABLE risk_snapshots (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    decision_id                 UUID NOT NULL REFERENCES decisions(id) ON DELETE CASCADE,

    risk_level                  VARCHAR(20),
    risk_score                  SMALLINT,
    recommended_leverage        DECIMAL(4,1),
    recommended_position_pct    DECIMAL(5,2),
    should_trade                BOOLEAN,
    risk_factors                JSONB,
    mitigation_suggestions      JSONB
);

-- 情感分析快照
CREATE TABLE sentiment_snapshots (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    decision_id         UUID NOT NULL REFERENCES decisions(id) ON DELETE CASCADE,

    overall_score       DECIMAL(4,2),  -- -1 to 1
    news_count          INTEGER,
    bullish_count       INTEGER,
    bearish_count       INTEGER,
    top_news            JSONB,         -- [{title, sentiment, source}]
    data_source         VARCHAR(30)
);
```

#### 3.2.2 订单与仓位

```sql
-- 订单记录
CREATE TABLE orders (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    symbol              VARCHAR(20) NOT NULL,
    exchange_order_id   VARCHAR(50),
    side                VARCHAR(20) NOT NULL,
    order_type          VARCHAR(10) NOT NULL,

    price               DECIMAL(20,8),
    size                DECIMAL(20,8) NOT NULL,
    filled_price        DECIMAL(20,8),
    filled_size         DECIMAL(20,8),
    fee                 DECIMAL(20,8),

    status              VARCHAR(20) NOT NULL,
    closed_at           TIMESTAMPTZ
);

CREATE INDEX idx_orders_symbol_time ON orders(symbol, created_at DESC);

-- 仓位历史
CREATE TABLE position_history (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    symbol              VARCHAR(20) NOT NULL,
    side                VARCHAR(10) NOT NULL,

    -- 入场
    entry_time          TIMESTAMPTZ NOT NULL,
    entry_price         DECIMAL(20,8) NOT NULL,
    entry_size          DECIMAL(20,8) NOT NULL,
    leverage            DECIMAL(4,1),

    -- 出场
    exit_time           TIMESTAMPTZ,
    exit_price          DECIMAL(20,8),

    -- 盈亏
    realized_pnl        DECIMAL(20,8),
    pnl_percent         DECIMAL(8,4),
    fee_total           DECIMAL(20,8),

    -- 关联决策
    entry_decision_id   UUID REFERENCES decisions(id),
    exit_decision_id    UUID REFERENCES decisions(id),

    status              VARCHAR(20) NOT NULL  -- open, closed
);

CREATE INDEX idx_positions_symbol ON position_history(symbol, entry_time DESC);

-- 每日统计（聚合表）
CREATE TABLE daily_stats (
    date                DATE NOT NULL,
    symbol              VARCHAR(20) NOT NULL,

    total_trades        INTEGER DEFAULT 0,
    winning_trades      INTEGER DEFAULT 0,
    losing_trades       INTEGER DEFAULT 0,

    total_pnl           DECIMAL(20,8) DEFAULT 0,
    max_drawdown        DECIMAL(8,4),

    PRIMARY KEY (date, symbol)
);
```

#### 3.2.3 回测相关

```sql
-- 回测记录
CREATE TABLE backtests (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- 模式
    mode                VARCHAR(20) NOT NULL,  -- single | portfolio

    -- 单币种参数
    symbol              VARCHAR(20),

    -- 组合参数
    symbols_config      JSONB,
    -- [{ symbol: "BTCUSDT", weight: 50, maxPosition: 30 }, ...]

    portfolio_params    JSONB,
    -- { totalMaxPosition: 60, correlationFilter: true, allocation: "weighted" }

    -- 通用参数
    start_date          DATE NOT NULL,
    end_date            DATE NOT NULL,
    initial_capital     DECIMAL(20,2) NOT NULL,
    leverage            DECIMAL(4,1),
    strategy_mode       VARCHAR(20),
    params              JSONB,

    -- 状态
    status              VARCHAR(20) NOT NULL,  -- pending, running, completed, failed, cancelled
    progress            SMALLINT DEFAULT 0,    -- 0-100
    error_message       TEXT,

    -- 结果
    final_capital       DECIMAL(20,2),
    total_pnl           DECIMAL(20,2),
    total_trades        INTEGER,
    winning_trades      INTEGER,
    max_drawdown        DECIMAL(8,4),
    sharpe_ratio        DECIMAL(8,4),

    -- 组合各币种结果
    symbol_results      JSONB,
    -- { "BTCUSDT": { pnl: 1820, trades: 45, winRate: 62 }, ... }

    completed_at        TIMESTAMPTZ
);

-- 回测交易明细
CREATE TABLE backtest_trades (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    backtest_id         UUID NOT NULL REFERENCES backtests(id) ON DELETE CASCADE,

    symbol              VARCHAR(20) NOT NULL,
    entry_time          TIMESTAMPTZ NOT NULL,
    exit_time           TIMESTAMPTZ,
    side                VARCHAR(10) NOT NULL,
    entry_price         DECIMAL(20,8) NOT NULL,
    exit_price          DECIMAL(20,8),
    size                DECIMAL(20,8) NOT NULL,
    pnl                 DECIMAL(20,8),
    pnl_percent         DECIMAL(8,4),

    decision_snapshot   JSONB
);

-- 回测资金曲线
CREATE TABLE backtest_equity (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    backtest_id         UUID NOT NULL REFERENCES backtests(id) ON DELETE CASCADE,

    timestamp           TIMESTAMPTZ NOT NULL,
    total_equity        DECIMAL(20,2) NOT NULL,
    symbol_equity       JSONB  -- { "BTCUSDT": 5200, "ETHUSDT": 3100, ... }
);

CREATE INDEX idx_equity_backtest_time ON backtest_equity(backtest_id, timestamp);
```

#### 3.2.4 相关性分析

```sql
-- 相关性缓存
CREATE TABLE correlation_cache (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    calculated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    symbol_a            VARCHAR(20) NOT NULL,
    symbol_b            VARCHAR(20) NOT NULL,
    timeframe           VARCHAR(10) NOT NULL,  -- 1d, 7d, 30d, 90d

    correlation         DECIMAL(5,4) NOT NULL, -- -1 to 1
    sample_size         INTEGER NOT NULL,

    UNIQUE (symbol_a, symbol_b, timeframe)
);

-- 价格历史
CREATE TABLE price_history (
    symbol              VARCHAR(20) NOT NULL,
    timestamp           TIMESTAMPTZ NOT NULL,
    close_price         DECIMAL(20,8) NOT NULL,

    PRIMARY KEY (symbol, timestamp)
);
```

#### 3.2.5 告警系统

```sql
-- 告警配置
CREATE TABLE alert_settings (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- 通知渠道
    channels            JSONB NOT NULL DEFAULT '{}',

    -- 告警规则
    rules               JSONB NOT NULL DEFAULT '{}',

    -- 价格告警
    price_alerts        JSONB NOT NULL DEFAULT '[]',

    -- 静默时段
    quiet_hours         JSONB
);

-- 告警历史
CREATE TABLE alert_history (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    level               VARCHAR(10) NOT NULL,  -- critical, warning, success, info
    category            VARCHAR(20) NOT NULL,  -- trade, risk, system, price
    title               VARCHAR(100) NOT NULL,
    message             TEXT NOT NULL,

    -- 关联
    symbol              VARCHAR(20),
    decision_id         UUID REFERENCES decisions(id),
    order_id            UUID REFERENCES orders(id),

    -- 发送状态
    channels_sent       JSONB
);

CREATE INDEX idx_alerts_time ON alert_history(created_at DESC);
CREATE INDEX idx_alerts_level ON alert_history(level, created_at DESC);
```

#### 3.2.6 系统管理

```sql
-- 操作日志
CREATE TABLE operation_logs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    action              VARCHAR(50) NOT NULL,  -- pause, resume, close_all, update_settings
    operator            VARCHAR(50),           -- user / system / auto
    details             JSONB,
    ip_address          VARCHAR(50)
);
```

---

## 4. API 接口设计

### 4.1 基础信息

```
Base URL:    /api
认证方式:    Session Cookie (简单密码认证)
响应格式:    JSON
```

### 4.2 认证

```typescript
// POST /api/auth/login
Request:  { password: string }
Response: { success: true }

// POST /api/auth/logout
Response: { success: true }

// GET /api/auth/check
Response: { authenticated: boolean }
```

### 4.3 账户

```typescript
// GET /api/account/summary
Response: {
  balance: {
    total: number,
    available: number,
    margin: number
  },
  position: {
    symbol: string,
    side: "long" | "short",
    size: number,
    entryPrice: number,
    markPrice: number,
    unrealizedPnl: number,
    leverage: number,
    liquidationPrice: number
  } | null,
  todayPnl: number,
  todayTrades: number,
  todayWinRate: number
}

// GET /api/account/balance
// GET /api/account/position
```

### 4.4 决策

```typescript
// GET /api/decisions
Query: { symbol?, limit?, offset?, from?, to? }
Response: {
  data: Decision[],
  total: number,
  hasMore: boolean
}

// GET /api/decisions/:id
Response: {
  ...decision,
  llmRawOutput: string,
  technical: TechnicalSnapshot,
  risk: RiskSnapshot,
  sentiment: SentimentSnapshot
}

// GET /api/decisions/latest
Response: Decision
```

### 4.5 仓位历史

```typescript
// GET /api/positions/history
Query: { symbol?, limit?, offset? }
Response: {
  data: PositionHistory[],
  total: number
}

// GET /api/orders
Query: { symbol?, status?, limit?, offset? }
Response: {
  data: Order[],
  total: number
}
```

### 4.6 统计分析

```typescript
// GET /api/analytics/summary
Query: { from?, to? }
Response: {
  totalPnl: number,
  totalTrades: number,
  winningTrades: number,
  losingTrades: number,
  winRate: number,
  profitFactor: number,
  avgWin: number,
  avgLoss: number,
  maxDrawdown: number,
  sharpeRatio: number,
  bestTrade: number,
  worstTrade: number
}

// GET /api/analytics/daily
Query: { days?: number }
Response: {
  data: Array<{ date: string, pnl: number, trades: number, winRate: number }>
}

// GET /api/analytics/by-symbol
Response: {
  data: Array<{ symbol: string, pnl: number, trades: number, winRate: number }>
}
```

### 4.7 相关性分析

```typescript
// GET /api/analytics/correlation/matrix
Query: { timeframe: "7d" | "30d" | "90d" }
Response: {
  timeframe: string,
  calculatedAt: string,
  symbols: string[],
  matrix: number[][]
}

// GET /api/analytics/correlation/pair
Query: { a: string, b: string, timeframe: string }
Response: {
  symbolA: string,
  symbolB: string,
  current: number,
  avg30d: number,
  min30d: number,
  max30d: number,
  rolling: Array<{ time: string, correlation: number }>
}

// GET /api/analytics/correlation/suggestions
Response: {
  recommended: Array<{ symbols: string[], correlation: number }>,
  avoid: Array<{ symbols: string[], correlation: number }>
}

// GET /api/analytics/price-comparison
Query: { symbols: string, days: number }
Response: {
  symbols: string[],
  data: Array<{ time: string, [symbol: string]: number }>
}
```

### 4.8 市场数据

```typescript
// GET /api/market/klines
Query: { symbol: string, interval: string, limit?: number }
Response: {
  symbol: string,
  interval: string,
  klines: Array<{ time: number, open: number, high: number, low: number, close: number, volume: number }>
}

// GET /api/market/symbols
Response: {
  symbols: Array<{ symbol: string, status: "running" | "paused", hasPosition: boolean }>
}
```

### 4.9 系统控制

```typescript
// GET /api/control/status
Response: {
  status: "running" | "paused" | "error",
  pausedAt?: string,
  pauseReason?: string,
  symbols: Record<string, { status: string, hasPosition: boolean }>
}

// POST /api/control/pause
Request: { reason?: string }

// POST /api/control/resume

// POST /api/control/close-all
Request: { confirm: true }

// POST /api/control/symbol/:symbol/pause
// POST /api/control/symbol/:symbol/resume
```

### 4.10 设置

```typescript
// GET /api/settings
Response: {
  symbols: string[],
  risk: { riskPerTrade: number, maxLeverage: number, maxPositionSize: number, dailyLossLimit: number },
  strategy: { mode: string, minConfidence: number, llmProvider: string, sentimentEnabled: boolean, sentimentWeight: number },
  slTp: { defaultStopLoss: number, defaultTakeProfit: number, trailingStop: { enabled: boolean, trigger: number, callback: number } }
}

// PATCH /api/settings/risk
// PATCH /api/settings/strategy
// PATCH /api/settings/sl-tp
```

### 4.11 告警

```typescript
// GET /api/settings/alerts
// PATCH /api/settings/alerts
Request/Response: {
  channels: {
    telegram: { enabled: boolean, botToken: string, chatId: string },
    webhook: { enabled: boolean, url: string },
    email: { enabled: boolean, address: string }
  },
  rules: {
    trade: { onOpen: boolean, onClose: boolean, largePnl: number, onFail: boolean },
    risk: { dailyLoss: number, consecutiveLoss: number, drawdown: number, marginRate: number },
    system: { onError: boolean, onPause: boolean, onDecision: boolean, correlation: boolean }
  },
  priceAlerts: Array<{ id: string, symbol: string, condition: string, value: number, timeframe?: string }>,
  quietHours: { enabled: boolean, start: string, end: string }
}

// POST /api/settings/alerts/test
Request: { channel: "telegram" | "webhook" | "email" }

// POST /api/settings/alerts/price
Request: { symbol: string, condition: string, value: number, timeframe?: string }

// DELETE /api/settings/alerts/price/:id

// GET /api/alerts/history
Query: { limit?, level?, category?, from? }
Response: { data: AlertHistory[], total: number }
```

### 4.12 回测

```typescript
// POST /api/backtests
Request: {
  mode: "single" | "portfolio",
  // 单币种
  symbol?: string,
  // 组合
  symbolsConfig?: Array<{ symbol: string, weight: number, maxPosition: number }>,
  portfolioParams?: { totalMaxPosition: number, correlationFilter: boolean, allocation: string },
  // 通用
  startDate: string,
  endDate: string,
  initialCapital: number,
  leverage: number,
  strategyMode: string,
  params?: object
}
Response: { id: string, status: "pending" }

// GET /api/backtests
Query: { limit?, offset?, status? }
Response: { data: Backtest[], total: number }

// GET /api/backtests/:id
Response: {
  ...backtest,
  symbolResults?: Record<string, SymbolResult>,
  equityCurve: Array<{ time: string, total: number, symbols?: Record<string, number> }>
}

// GET /api/backtests/:id/trades
Query: { symbol? }
Response: { data: BacktestTrade[], total: number }

// POST /api/backtests/:id/cancel

// DELETE /api/backtests/:id

// GET /api/backtests/compare
Query: { ids: string }  // comma-separated
Response: {
  backtests: Array<BacktestWithMetrics>,
  comparison: {
    best: Record<string, string>,  // metric -> backtestId
    scores: Array<{ id: string, score: number }>
  }
}

// POST /api/backtests/compare/export
Request: { ids: string[], format: "pdf" | "csv" }
Response: { downloadUrl: string }
```

### 4.13 实时数据

```typescript
// SSE: GET /api/backtests/:id/stream
Event: "progress"
Data: {
  backtestId: string,
  status: string,
  progress: number,
  currentDate: string,
  daysProcessed: number,
  totalDays: number,
  currentEquity: number,
  currentPnl: number,
  currentPnlPct: number,
  totalTrades: number,
  winRate: number,
  equityCurve: Array<{ time: string, equity: number }>,
  latestTrades: Array<Trade>
}

// WebSocket: ws://localhost:8000/ws
// Python 端推送决策/持仓更新
Message Types:
- decision_new: 新决策
- position_update: 持仓更新
- order_filled: 订单成交
```

---

## 5. 前端页面设计

### 5.1 路由结构

```
app/routes/
├── _index.tsx                      # 重定向到 /dashboard
├── login.tsx                       # 登录页
│
├── _auth.tsx                       # 认证布局（检查登录）
├── _auth.dashboard.tsx             # Dashboard 布局壳
├── _auth.dashboard._index.tsx      # 概览页
├── _auth.dashboard.chart.tsx       # 多图表页面
├── _auth.dashboard.decisions.tsx   # 决策列表
├── _auth.dashboard.decisions.$id.tsx  # 决策详情
├── _auth.dashboard.positions.tsx   # 仓位历史
├── _auth.dashboard.analytics.tsx   # 统计分析
├── _auth.dashboard.analytics.correlation.tsx  # 相关性分析
├── _auth.dashboard.backtest.tsx    # 回测列表 + 新建
├── _auth.dashboard.backtest.$id.tsx   # 回测详情/进度
├── _auth.dashboard.backtest.compare.tsx  # 回测对比
├── _auth.dashboard.control.tsx     # 系统控制
├── _auth.dashboard.settings.tsx    # 参数配置
├── _auth.dashboard.settings.alerts.tsx  # 告警设置
├── _auth.dashboard.alerts.tsx      # 告警历史
```

### 5.2 组件结构

```
app/components/
├── layout/
│   ├── Sidebar.tsx                 # 侧边导航
│   ├── Header.tsx                  # 顶栏
│   └── ThemeProvider.tsx           # 主题
│
├── dashboard/
│   ├── AccountCard.tsx             # 账户概览卡片
│   ├── PositionCard.tsx            # 当前持仓卡片
│   ├── RecentDecisions.tsx         # 最近决策列表
│   ├── PnlChart.tsx                # 收益曲线
│   └── StatsGrid.tsx               # 统计数字网格
│
├── decisions/
│   ├── DecisionTable.tsx           # 决策列表表格
│   ├── DecisionDetail.tsx          # 决策详情面板
│   ├── LlmOutputCard.tsx           # LLM 输出展示
│   └── TechnicalCard.tsx           # 技术分析卡片
│
├── charts/
│   ├── PriceChart.tsx              # K线图（Lightweight Charts）
│   ├── EquityCurve.tsx             # 资金曲线
│   ├── MultiChart.tsx              # 多图表容器
│   └── CorrelationMatrix.tsx       # 相关性矩阵热力图
│
├── backtest/
│   ├── BacktestForm.tsx            # 新建回测表单
│   ├── BacktestProgress.tsx        # 回测进度
│   ├── BacktestResult.tsx          # 回测结果
│   └── BacktestCompare.tsx         # 回测对比
│
├── control/
│   ├── SystemStatus.tsx            # 系统状态
│   ├── SymbolControl.tsx           # 交易对控制
│   └── EmergencyClose.tsx          # 紧急平仓
│
├── settings/
│   ├── RiskSettings.tsx            # 风控参数
│   ├── StrategySettings.tsx        # 策略配置
│   └── AlertSettings.tsx           # 告警配置
│
└── common/
    ├── StatCard.tsx                # 统计卡片
    ├── DataTable.tsx               # 数据表格
    ├── LoadingSpinner.tsx          # 加载动画
    └── ConfirmDialog.tsx           # 确认对话框
```

### 5.3 页面详细设计

#### 5.3.1 概览页

```
┌────────────────────────────────────────────────────────────┐
│  Header: Logo    [BTC $98,234]  [账户: $12,345]  [●]       │
├────────┬───────────────────────────────────────────────────┤
│        │                                                   │
│  侧    │   ┌─────────────┐ ┌─────────────┐                │
│  边    │   │  账户概览   │ │  当前持仓   │                │
│  栏    │   │ 余额/保证金 │ │ 方向/盈亏   │                │
│        │   └─────────────┘ └─────────────┘                │
│  概览  │                                                   │
│  图表  │   ┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐       │
│  决策  │   │今日PnL│ │ 胜率  │ │交易数 │ │ 回撤  │       │
│  仓位  │   └───────┘ └───────┘ └───────┘ └───────┘       │
│  分析  │                                                   │
│  回测  │   ┌─────────────────────────────────────┐        │
│  控制  │   │           收益曲线 (7日/30日)        │        │
│  设置  │   └─────────────────────────────────────┘        │
│        │                                                   │
│        │   ┌─────────────────────────────────────┐        │
│        │   │          最近决策列表 (5条)          │        │
│        │   └─────────────────────────────────────┘        │
└────────┴───────────────────────────────────────────────────┘
```

#### 5.3.2 多图表页

```
┌─────────────────────────────────────────────────────────────┐
│  [+ 添加图表]  [布局: 1x1 | 2x1 | 2x2 | 3x2]  [保存布局]    │
├────────┬────────────────────────────────────────────────────┤
│        │ ┌─────────────────────┐ ┌─────────────────────┐   │
│  侧    │ │ BTC/USDT    15m  ×  │ │ ETH/USDT    15m  ×  │   │
│  边    │ │      K线图          │ │      K线图          │   │
│  栏    │ │  RSI: 67  MACD: ▲   │ │  RSI: 45  MACD: ▼   │   │
│        │ └─────────────────────┘ └─────────────────────┘   │
│        │ ┌─────────────────────┐ ┌─────────────────────┐   │
│        │ │ SOL/USDT    1h   ×  │ │ BTC/USDT    4h   ×  │   │
│        │ │      K线图          │ │      K线图          │   │
│        │ └─────────────────────┘ └─────────────────────┘   │
└────────┴────────────────────────────────────────────────────┘

功能:
- 布局切换: 1x1 / 2x1 / 2x2 / 3x2
- 独立配置: 每个图表独立选择 Symbol + 周期
- 同步十字线: 鼠标悬停时其他图表同步
- 买卖标记: 在图表上标注历史决策点
```

#### 5.3.3 决策详情页

```
┌─────────────────────────────────────────────────────────────┐
│  决策详情 #abc123                      2024-01-15 14:32:00  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 基本信息                                             │   │
│  │ 交易对: BTC/USDT    动作: OPEN_LONG    置信度: 85%  │   │
│  │ 入场价: $95,000     止损: $93,000      止盈: $99,000│   │
│  │ 杠杆: 5x            仓位: 20%                        │   │
│  │                                                     │   │
│  │ 决策理由:                                            │   │
│  │ "价格突破关键阻力位 $94,500，成交量放大确认突破..."  │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ LLM 原始输出                              [展开/收起]│   │
│  │ Provider: DeepSeek    Model: deepseek-chat          │   │
│  │ Tokens: 1,234                                       │   │
│  │ ─────────────────────────────────────────────────── │   │
│  │ 完整的 LLM 输出内容...                               │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌──────────────────────┐ ┌──────────────────────┐        │
│  │ 技术分析              │ │ 风险评估              │        │
│  │ 趋势: 看涨 (75%)      │ │ 风险等级: 中等        │        │
│  │ RSI: 67               │ │ 风险评分: 45          │        │
│  │ MACD: 上穿            │ │ 推荐杠杆: 5x          │        │
│  │ 支撑: 93000, 91500    │ │ 风险因素:             │        │
│  │ 阻力: 96000, 98000    │ │ - 接近超买区          │        │
│  └──────────────────────┘ └──────────────────────┘        │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 情感分析                                             │   │
│  │ 综合评分: 0.65 (偏多)    新闻数: 12                  │   │
│  │ 看多: 8    看空: 2    中性: 2                       │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 执行结果                                             │   │
│  │ 状态: 已平仓    盈亏: +$234.50 (+2.3%)              │   │
│  │ 持仓时长: 2小时15分                                  │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 5.4 UI 设计规范

#### 5.4.1 配色方案

```css
/* 深色主题 */
--background: #0a0a0f;
--card: #12121a;
--card-hover: #1a1a24;
--border: #2a2a3a;

--text-primary: #ffffff;
--text-secondary: #a0a0b0;
--text-muted: #606070;

--success: #22c55e;    /* 盈利/上涨 */
--danger: #ef4444;     /* 亏损/下跌 */
--warning: #f59e0b;    /* 警告 */
--info: #3b82f6;       /* 信息 */

--accent: #6366f1;     /* 主题色 */
```

#### 5.4.2 组件样式

- 卡片: 圆角 8px，边框 1px，微弱阴影
- 按钮: 圆角 6px，主要按钮使用 accent 色
- 表格: 斑马纹，hover 高亮
- 图表: 深色背景，绿涨红跌

---

## 6. WebSocket 实时数据

### 6.1 架构

```
实时 K 线:     前端直连 Binance WebSocket（延迟最低）
决策/持仓:     Python → 内置 WS Server → 前端
回测进度:      Python → Redis → SSE → 前端
```

### 6.2 前端直连 Binance

```typescript
// hooks/useBinanceKline.ts
export function useBinanceKline(symbol: string, interval: string) {
  const [klines, setKlines] = useState<Kline[]>([]);

  useEffect(() => {
    const ws = new WebSocket(
      `wss://fstream.binance.com/ws/${symbol.toLowerCase()}@kline_${interval}`
    );

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      const kline = {
        time: data.k.t / 1000,
        open: parseFloat(data.k.o),
        high: parseFloat(data.k.h),
        low: parseFloat(data.k.l),
        close: parseFloat(data.k.c),
        volume: parseFloat(data.k.v),
      };
      setKlines(prev => updateKline(prev, kline));
    };

    return () => ws.close();
  }, [symbol, interval]);

  return klines;
}
```

### 6.3 Python WS Server

```python
# ws_server.py
from fastapi import FastAPI, WebSocket
from typing import Set

app = FastAPI()
connections: Set[WebSocket] = set()

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    connections.add(ws)
    try:
        while True:
            await ws.receive_text()
    finally:
        connections.discard(ws)

async def broadcast(event_type: str, data: dict):
    message = {"type": event_type, "data": data}
    for ws in connections:
        await ws.send_json(message)
```

### 6.4 SSE 回测进度

```typescript
// app/routes/api.backtests.$id.stream.ts
import { eventStream } from "remix-utils/sse/server";

export async function loader({ request, params }: LoaderFunctionArgs) {
  return eventStream(request.signal, function setup(send) {
    const redis = new Redis();
    redis.subscribe(`backtest:${params.id}`);

    redis.on("message", (ch, message) => {
      send({ event: "progress", data: message });
    });

    return () => redis.quit();
  });
}
```

---

## 7. 认证方案

### 7.1 简单密码认证

```typescript
// 环境变量
DASHBOARD_PASSWORD=your_secure_password
SESSION_SECRET=random_secret_key

// app/services/auth.server.ts
import { createCookieSessionStorage, redirect } from "@remix-run/node";
import bcrypt from "bcryptjs";

const sessionStorage = createCookieSessionStorage({
  cookie: {
    name: "_session",
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    maxAge: 60 * 60 * 24 * 7, // 7 days
    secrets: [process.env.SESSION_SECRET!],
  },
});

export async function login(password: string) {
  const isValid = password === process.env.DASHBOARD_PASSWORD;
  if (!isValid) return null;

  const session = await sessionStorage.getSession();
  session.set("authenticated", true);
  return sessionStorage.commitSession(session);
}

export async function requireAuth(request: Request) {
  const session = await sessionStorage.getSession(request.headers.get("Cookie"));
  if (!session.get("authenticated")) {
    throw redirect("/login");
  }
}
```

### 7.2 安全措施

| 措施 | 说明 |
|------|------|
| HTTPS | 生产环境强制 |
| Session Cookie | HttpOnly, Secure, SameSite |
| 登录限流 | 5 次失败锁定 15 分钟 |
| 敏感操作确认 | 紧急平仓需再次输入密码 |

---

## 8. 部署方案

### 8.1 Docker Compose

```yaml
version: '3.8'

services:
  dashboard:
    build: ./dashboard
    ports:
      - "3000:3000"
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/trader
      - SESSION_SECRET=${SESSION_SECRET}
      - DASHBOARD_PASSWORD=${DASHBOARD_PASSWORD}
    depends_on:
      - db
      - redis

  trader:
    build: ./trader
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/trader
      - REDIS_URL=redis://redis:6379
    depends_on:
      - db
      - redis

  db:
    image: postgres:16-alpine
    volumes:
      - postgres_data:/var/lib/postgresql/data
    environment:
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
      - POSTGRES_DB=trader

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data

volumes:
  postgres_data:
  redis_data:
```

### 8.2 目录结构

```
trader/
├── src/ai_trader/          # 现有 Python 交易系统
├── dashboard/              # 新建 Remix Dashboard
│   ├── app/
│   │   ├── routes/
│   │   ├── components/
│   │   ├── services/
│   │   ├── hooks/
│   │   └── lib/
│   ├── public/
│   ├── package.json
│   ├── tailwind.config.ts
│   ├── drizzle.config.ts
│   └── Dockerfile
├── docker-compose.yml
└── docs/design/
```

---

## 9. 开发计划

### Phase 1: 基础框架 (MVP)

- [ ] 数据库设计与迁移
- [ ] Remix 项目搭建
- [ ] 简单密码认证
- [ ] Dashboard 布局
- [ ] 概览页（账户、持仓、统计）
- [ ] 决策列表与详情页

### Phase 2: 图表与分析

- [ ] K 线图表（Lightweight Charts）
- [ ] 多图表同屏
- [ ] 统计分析页
- [ ] 仓位历史页

### Phase 3: 回测系统

- [ ] 回测创建与执行
- [ ] 实时进度显示
- [ ] 回测结果展示
- [ ] 多回测对比

### Phase 4: 高级功能

- [ ] 相关性分析
- [ ] 系统控制面板
- [ ] 参数配置
- [ ] 告警系统

### Phase 5: 完善与优化

- [ ] 响应式适配
- [ ] 性能优化
- [ ] 部署文档
- [ ] 测试覆盖

---

## 10. 附录

### 10.1 参考资料

- [Remix 文档](https://remix.run/docs)
- [Drizzle ORM](https://orm.drizzle.team/)
- [shadcn/ui](https://ui.shadcn.com/)
- [TradingView Lightweight Charts](https://tradingview.github.io/lightweight-charts/)

### 10.2 设计文件

- 数据库 ER 图: 见 3.1 节
- API 接口文档: 见第 4 节
- 页面原型: 见 5.3 节
