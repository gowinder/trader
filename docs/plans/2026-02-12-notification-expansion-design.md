# TG 推送扩展设计：交易/决策/回测通知与开关设置

## 概述

将现有仅支持 Advisory 的 Telegram 推送扩展为支持交易、决策、回测、Advisory 四大类通知，每个事件可独立开关，通过 Dashboard 配置，存储于 Redis。

## 通知类型与事件定义

### 交易通知（Trade）

| 事件 key | 说明 | 默认 |
|----------|------|------|
| `trade.open_long` | 开多 | 开启 |
| `trade.open_short` | 开空 | 开启 |
| `trade.close_long` | 平多 | 开启 |
| `trade.close_short` | 平空 | 开启 |
| `trade.add_reduce` | 加仓/减仓 | 开启 |
| `trade.stop_loss_take_profit` | 止损/止盈触发 | 开启 |

### 决策通知（Decision）

| 事件 key | 说明 | 默认 |
|----------|------|------|
| `decision.action` | 有实际动作的决策（开/平/加/减） | 开启 |
| `decision.hold` | 持仓不动的决策 | 关闭 |

### 回测通知（Backtest）

| 事件 key | 说明 | 默认 |
|----------|------|------|
| `backtest.completed` | 回测完成结果摘要 | 开启 |

### Advisory 通知（已有，纳入开关体系）

| 事件 key | 说明 | 默认 |
|----------|------|------|
| `advisory.suggestion` | AI 建议通知 | 开启 |

## 配置存储

Redis key: `notification:config`

```json
{
  "telegram_enabled": true,
  "trade": {
    "enabled": true,
    "open_long": true,
    "open_short": true,
    "close_long": true,
    "close_short": true,
    "add_reduce": true,
    "stop_loss_take_profit": true
  },
  "decision": {
    "enabled": true,
    "action": true,
    "hold": false
  },
  "backtest": {
    "enabled": true,
    "completed": true
  },
  "advisory": {
    "enabled": true,
    "suggestion": true
  }
}
```

- `telegram_enabled` 全局总开关，关闭后所有 TG 推送静默
- 每个类别有 `enabled` 总开关，子项只在总开关开启时生效
- 配置变更通过 Redis pubsub 热更新，事件名 `notification:config:updated`
- 复用现有 `scheduler._config_listener()` 机制

## 架构设计

### 新建 NotificationManager

```
src/ai_trader/notification/
├── __init__.py
├── manager.py      # NotificationManager 核心
└── formatter.py    # 消息格式化
```

NotificationManager 职责：
- 加载/缓存通知配置（从 Redis）
- `check_enabled(event_type)` — 检查某事件是否开启
- `notify_trade(symbol, action, order_result)` — 交易通知
- `notify_decision(symbol, decision)` — 决策通知
- `notify_backtest(task_id, result)` — 回测通知
- `notify_advisory(advisory_result)` — 封装现有逻辑
- 内部调用现有 `TelegramNotifier` 发送（保留现有发送层不变）

### 调用点植入

| 事件 | 植入位置 | 触发时机 |
|------|---------|---------|
| 交易 | `scheduler.py` → `_persist_position_change()` | 订单执行完成后 |
| 交易(止损止盈) | `scheduler.py` → `_check_stop_loss_take_profit()` | 止损/止盈触发时 |
| 决策 | `scheduler.py` → `run_cycle_for_symbol()` | 决策引擎返回结果后 |
| 回测 | `scheduler.py` → `_run_backtest_task()` | 回测任务完成后 |
| Advisory | `advisory/service.py`（现有） | 保持不变，纳入开关检查 |

### 文件变更清单

1. **新建** `src/ai_trader/notification/__init__.py`
2. **新建** `src/ai_trader/notification/manager.py` — NotificationManager
3. **新建** `src/ai_trader/notification/formatter.py` — 消息格式化
4. **修改** `src/ai_trader/scheduler.py` — 4 个调用点植入通知 + 配置监听
5. **修改** `src/ai_trader/config.py` — 添加通知配置默认值
6. **新建** `dashboard/app/routes/dashboard.notification-settings.tsx` — 设置页面
7. **修改** 后端 API — 新增 3 个端点

## 消息格式

### 交易通知

```
📈 开多 | BTCUSDT
━━━━━━━━━━━━━━━
💰 价格: 65,230.50 USDT
📊 数量: 0.05 BTC
🔧 杠杆: 10x
📐 仓位: 30%
🎯 止盈: 67,500.00
🛑 止损: 63,800.00
⏰ 2024-01-15 14:32:08
```

操作类型 emoji 映射：
- 开多 📈 / 开空 📉 / 平多 💰 / 平空 💰 / 加仓 ➕ / 减仓 ➖

### 止损止盈触发

```
🛑 止损触发 | BTCUSDT
━━━━━━━━━━━━━━━
📉 方向: 多头
💰 入场: 65,230.50
❌ 触发: 63,800.00
📊 盈亏: -2.19%
⏰ 2024-01-15 15:10:22
```

### 决策通知（有动作）

```
🧠 AI决策 | BTCUSDT
━━━━━━━━━━━━━━━
📋 动作: 开多
🎯 信心度: 85/100
💡 理由: RSI超卖反弹，MACD金叉确认
⚠️ 风险: 注意4h级别阻力位
⏰ 2024-01-15 14:30:05
```

### 决策通知（hold，简化格式）

```
🧠 AI决策 | BTCUSDT — ⏸️ 持仓不动 (信心度: 72)
```

### 回测通知

```
📊 回测完成 | BTCUSDT
━━━━━━━━━━━━━━━
📅 周期: 2024-01-01 ~ 2024-01-15
💰 总盈亏: +12.35%
🏆 胜率: 63.2%
📉 最大回撤: -5.8%
📈 夏普比率: 1.85
🔄 交易次数: 47
⏰ 完成于 2024-01-15 16:00:00
```

## Dashboard 设置页面

### 路由

`dashboard.notification-settings.tsx`，在侧边栏 Advisory Settings 下方添加入口。

### 页面结构

```
🔔 通知设置

[全局开关] Telegram 推送  ●开

━━━ 交易通知 ━━━━━━━━━━━━━━
[总开关] 交易通知  ●开
  ├ 开多          ●开
  ├ 开空          ●开
  ├ 平多          ●开
  ├ 平空          ●开
  ├ 加仓/减仓     ●开
  └ 止损/止盈触发  ●开

━━━ 决策通知 ━━━━━━━━━━━━━━
[总开关] 决策通知  ●开
  ├ 有动作的决策   ●开
  └ 持仓不动      ○关

━━━ 回测通知 ━━━━━━━━━━━━━━
[总开关] 回测通知  ●开
  └ 回测完成      ●开

━━━ Advisory 通知 ━━━━━━━━━
[总开关] Advisory 通知  ●开
  └ AI建议        ●开

         [保存设置]  [发送测试消息]
```

### 交互逻辑

- 总开关关闭时，子项全部灰化不可点击
- 全局开关关闭时，所有类别灰化
- 点"保存设置"写入 Redis 并 publish `notification:config:updated`
- "发送测试消息"按钮发一条测试 TG 消息验证连通性
- 页面加载时从后端 API 读取当前配置

### 后端 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/notification/config` | 获取通知配置 |
| PUT | `/api/notification/config` | 保存通知配置 |
| POST | `/api/notification/test` | 发送测试消息 |
