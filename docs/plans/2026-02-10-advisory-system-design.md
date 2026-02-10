# AI Advisory System Design

## Overview

Independent AI advisory service that proactively monitors trading history, market conditions, and portfolio status, then generates actionable suggestions for user approval.

## Architecture

```
┌─────────────────────────────────────┐
│           Advisory Service           │
├─────────────────────────────────────┤
│  Trigger Manager                     │
│  ├─ ScheduledTrigger (定时轮询)       │
│  └─ EventTrigger (事件驱动)           │
│      ├─ PriceVolatilityDetector      │
│      ├─ ConsecutiveLossDetector      │
│      ├─ UnrealizedPnLDetector        │
│      └─ SentimentShiftDetector       │
│                                      │
│  Advisory LLM Client                 │
│  (独立 provider/model 配置)           │
│                                      │
│  Advice Generator                    │
│  ├─ 收集上下文(历史、行情、仓位、情绪) │
│  ├─ 构建 Prompt → 调用 LLM           │
│  └─ 生成结构化建议                    │
│                                      │
│  Notification Dispatcher             │
│  ├─ Dashboard (WebSocket 推送)       │
│  └─ Telegram Bot (Inline Keyboard)   │
│                                      │
│  Execution Engine                    │
│  ├─ ConfigExecutor (参数调整)         │
│  ├─ TradeExecutor (仓位操作)          │
│  └─ SymbolExecutor (交易对增减)       │
└─────────────────────────────────────┘
```

## Trigger System

### Scheduled Trigger
- Default interval configurable (5min - 4h), integrated into existing `scheduler.py`

### Event Triggers

| Trigger | Default Threshold | Description |
|---------|-------------------|-------------|
| PriceVolatility | 5% / 5min | Rapid price movement |
| ConsecutiveLoss | 3 trades | Consecutive losing trades |
| UnrealizedPnL | -5% | Unrealized position loss |
| SentimentShift | EXTREME level | Sudden sentiment change to extreme fear/greed |

### Anti-duplicate
- Per-trigger cooldown period (default 30min)
- Independent cooldown per trigger type

### Configuration
- All thresholds configurable via Dashboard → Redis (hot reload)
- Each trigger has independent on/off switch + threshold + cooldown

## Advisory LLM Configuration

Independent from trading AI providers:

```
ADVISORY_LLM_PROVIDER=openrouter
ADVISORY_LLM_MODEL=deepseek/deepseek-chat-v3-0324
ADVISORY_LLM_API_KEY=xxx
ADVISORY_LLM_BASE_URL=https://openrouter.ai/api/v1
```

Single provider + model, no priority scheduling needed.

## Context Collection

When triggered, the system collects:
- Recent N trade records (PnL, decision reasoning, technical snapshots)
- All current position states (unrealized PnL, leverage, hold duration)
- Real-time market data (prices, indicators, multi-timeframe trends)
- Sentiment analysis results
- Current strategy configuration (weights, stop-loss/take-profit, leverage range)
- Trigger reason (what event/schedule triggered this check)

## LLM Structured Output

```python
AdvisoryResult:
  urgency: "high" | "medium" | "low"
  suggestions: List[Suggestion]
  market_summary: str

Suggestion:
  type: "param_adjust" | "position_action" | "symbol_change"
  target: str          # e.g. "BTC/USDT" or "global"
  action: str          # e.g. "reduce_leverage", "close_position", "add_symbol"
  detail: dict         # specific params
  reasoning: str       # Chinese reasoning
  risk_note: str       # Risk warning
```

## Database Schema

### Table: `advisories`

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| trigger_type | str | "scheduled" / "price_volatility" / "consecutive_loss" etc. |
| trigger_detail | JSON | Trigger context data |
| urgency | str | high / medium / low |
| market_summary | str | Market overview |
| status | str | pending / resolved |
| llm_provider | str | Provider used |
| llm_model | str | Model used |
| tokens_used | int | Token consumption |
| created_at | timestamp | Generation time |
| resolved_at | timestamp | User action time |

### Table: `advisory_suggestions`

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| advisory_id | UUID | FK to advisories |
| type | str | param_adjust / position_action / symbol_change |
| target | str | Symbol or "global" |
| action | str | Specific action |
| detail | JSON | Parameter details |
| reasoning | str | Chinese reasoning |
| risk_note | str | Risk warning |
| status | str | pending → accepted/rejected → confirmed → executed/failed |

### Status Flow

```
pending → accepted (user adopts) → confirmed (second confirm) → executed
pending → rejected (user ignores/rejects)
confirmed → failed (execution error)
```

Each suggestion has independent status; user can selectively adopt within same advisory batch.

## Notification System

### Dashboard
- WebSocket real-time push for new advisories
- Notification card popup with urgency level + summary
- Advisory list page for details and operations
- Unresolved advisory count badge in top navigation

### Telegram Bot
- Inline Keyboard buttons per suggestion: ✅ Adopt / ❌ Reject
- After adopt: ⚠️ Confirm Execute? / ↩️ Cancel (second confirmation)
- Execution result reply
- Security: only respond to configured `TELEGRAM_CHAT_ID`
- Operation timeout: 2h after generation, must use Dashboard
- Configurable push level filter (e.g. only push high urgency)
- Silent period support (e.g. no push at night)

Configuration:
```
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_CHAT_ID=xxx
```

## Execution Engine

| Suggestion Type | Executor | Operation |
|-----------------|----------|-----------|
| param_adjust | ConfigExecutor | Modify Redis config (stop-loss, leverage, weights), immediate effect |
| position_action | TradeExecutor | Call Exchange adapter for close/reduce/add position |
| symbol_change | SymbolExecutor | Modify TRADING_SYMBOLS config, trigger scheduler reload |

### Execution Flow

```
confirmed → validate parameters
         → execute operation
         → success → status = executed, record result
         → failure → status = failed, record error
         → notify user (Dashboard + Telegram)
```

### Safety Measures
- Parameter hard limits (leverage cannot exceed `leverage_max`)
- Position existence check before trade operations
- All executions logged + database audit trail
- Parameter changes can be rolled back; failed trade operations marked as failed

## Dashboard UI

### Advisory List Page (`dashboard.advisory.tsx`)
- Reverse chronological advisory cards
- Each card: urgency tag (color coded), trigger reason, market summary, time
- Expand for suggestion details + action buttons
- Filters: urgency / status / trigger_type / time range
- Per-suggestion: Adopt → Confirm popup → Execute / Reject (optional reason)

### Advisory Settings Page (`dashboard.advisory-settings.tsx`)
- Scheduled interval slider (5min - 4h)
- Trigger list: each trigger row with toggle + threshold input + cooldown
- Telegram config section: Bot Token, Chat ID, push level, silent period
- Advisory LLM config section: Provider dropdown, Model input, API Key, Base URL
- All changes save to Redis, immediate effect

## Out of Scope (YAGNI)
- Multi-user permission system
- Advisory accuracy tracking / historical analysis
- Notification channels beyond Telegram (email, WeChat etc.)
