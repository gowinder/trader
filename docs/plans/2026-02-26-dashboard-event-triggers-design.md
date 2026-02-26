# Dashboard 事件触发管理页面设计

## 概述

为事件驱动 LLM 触发机制提供 Dashboard 管理界面，包含三个功能：
1. 事件触发记录查看
2. 事件开关/阈值配置编辑
3. 策略-事件映射展示

## 页面结构

- **路由**：`dashboard/app/routes/dashboard.event-triggers.tsx`
- **API 路由**：
  - `api.event-triggers.logs.ts` — 查询触发记录
  - `api.event-triggers.config.ts` — 读写事件配置
  - `api.event-triggers.mapping.ts` — 读取策略-事件映射
- **布局**：单页 + 3 个 Tabs（触发记录 / 事件配置 / 策略映射）
- **侧边栏**：`navItems` 组，Decisions 之后，图标 `Zap`

## 数据库表

**`event_trigger_logs`**（Drizzle schema）：

| 字段 | 类型 | 说明 |
|------|------|------|
| id | serial | PRIMARY KEY |
| symbol | varchar(20) | 交易对 |
| event_type | varchar(50) | 事件类型 |
| severity | varchar(10) | high/medium/low |
| description | text | 事件描述 |
| key_data | jsonb | 关键数据 |
| triggered_at | timestamp | 事件触发时间 |
| created_at | timestamp | 默认 now() |

**索引**：`(symbol, triggered_at)` 复合索引

**Python 端写入**：`EventDetector.scan()` 检测到事件后 INSERT。

## Tab 1：触发记录

**筛选栏**：币种 / 事件类型 / 严重程度 / 时间范围（默认过去 24h）

**表格列**：时间 | 币种 | 事件类型 | 严重程度 | 描述 | 关键数据

- 严重程度彩色标签：high=红 / medium=黄 / low=绿
- 关键数据：tooltip 或可展开 JSON
- 分页：每页 20 条，时间倒序
- API：`GET /api/event-triggers/logs?symbol=&type=&severity=&from=&to=&page=1&limit=20`

## Tab 2：事件配置

**全局配置区**：
- 事件触发总开关 (Switch)
- 扫描间隔秒数 (Input)
- 全局冷却秒数 (Input)
- 单事件冷却秒数 (Input)
- 触发后重置定时器 (Switch)

**事件卡片**（7 个，网格 2~3 列）：

| 事件 | 开关 | 参数 |
|------|------|------|
| Price Surge | Switch | ATR 倍数, 回看秒数 |
| Volume Spike | Switch | 成交量倍数 |
| RSI Extreme | Switch | 上阈值, 下阈值 |
| MACD Cross | Switch | 无 |
| Bollinger Break | Switch | 无 |
| Market State Change | Switch | 无 |
| Position PnL | Switch | 止盈阈值(%), 止损阈值(%) |

- 即时生效：修改后立即写入 Redis `trading:event_trigger_config`
- pubsub 通知：`trading:event_trigger_config:updated`
- 输入框 debounce 500ms

## Tab 3：策略-事件映射

只读矩阵表格，展示 `STRATEGY_EVENT_DEFAULTS`：

| 策略 \ 事件 | Price Surge | Volume Spike | RSI Extreme | MACD Cross | Bollinger Break | Market State | Position PnL |
|-------------|:-----------:|:------------:|:-----------:|:----------:|:---------------:|:------------:|:------------:|
| trend_following | ✓ | | | ✓ | | ✓ | ✓ |
| mean_reversion | ✓ | | ✓ | | ✓ | ✓ | ✓ |
| breakout | ✓ | ✓ | | | ✓ | ✓ | ✓ |

- 表格上方说明文字："映射关系由代码定义，展示各策略关注的事件类型"
- API：`GET /api/event-triggers/mapping` 返回 JSON
