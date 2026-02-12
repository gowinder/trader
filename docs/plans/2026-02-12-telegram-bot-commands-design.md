# Telegram Bot 交互功能设计

## 概述

在现有 Telegram 推送通知基础上，增加命令交互功能，通过 BotCommand 菜单 + Inline Keyboard 导航，部分替代 Dashboard 功能，支持在 Telegram 中查看概览、持仓、决策、LLM 调用统计、策略管理、Advisory 管理和交易控制。

## 设计决策

- **交互方式**：BotCommand 快捷入口 + Inline Keyboard 按钮导航结合
- **功能范围**：全部 Dashboard 核心功能（概览、持仓、决策、LLM、策略、Advisory、交易控制）
- **代码结构**：重构为 `telegram/` 包，拆分模块
- **数据获取**：直接读 Redis/PostgreSQL，不走 HTTP API
- **安全控制**：只允许配置的 `chat_id` 使用
- **列表展示**：摘要列表 + 点击查看详情
- **写操作**：危险操作（切换策略、开关交易）需二次确认

## 命令列表

| 命令 | 功能 | 类型 |
|------|------|------|
| `/start` | 显示主菜单（inline keyboard 导航） | 导航 |
| `/menu` | 同 `/start`，随时呼出主菜单 | 导航 |
| `/overview` | 账户概览：权益、盈亏、持仓数、今日决策数 | 查询 |
| `/positions` | 当前持仓摘要列表，点击查看详情 | 查询 |
| `/decisions` | 最近决策摘要列表，点击查看详情 | 查询 |
| `/llm` | LLM 调用统计：总调用、费用、今日费用 | 查询 |
| `/strategy` | 当前策略 + 可用预设列表，点击切换（需确认） | 查询+写 |
| `/advisory` | 待处理 Advisory 列表，可采纳/拒绝 | 查询+写 |
| `/trading` | 交易开关状态，可切换（需确认） | 查询+写 |
| `/help` | 命令帮助列表 | 导航 |

## 主菜单 Inline Keyboard 布局

```
[ 📊 概览 ]  [ 📈 持仓 ]
[ 🧠 决策 ]  [ 🤖 LLM ]
[ 📋 策略 ]  [ 💡 Advisory ]
[ ⚙️ 交易控制 ]
```

## 目录结构

```
src/ai_trader/advisory/telegram/
  __init__.py          # 导出 TelegramBot
  bot.py               # Bot 生命周期：初始化、注册 handlers、启动/停止
  notifier.py          # 从现有 telegram.py 迁移推送逻辑
  commands.py          # 命令注册：将 /xxx 映射到对应 handler
  auth.py              # chat_id 验证装饰器
  keyboards.py         # Inline keyboard 构建工具函数
  formatters.py        # 消息格式化（Markdown 转义、截断等）
  handlers/
    __init__.py
    overview.py        # /overview + 回调
    positions.py       # /positions + 详情回调
    decisions.py       # /decisions + 详情回调
    llm_usage.py       # /llm + 详情回调
    strategy.py        # /strategy + 切换 + 确认回调
    advisory.py        # /advisory + 采纳/拒绝回调（从现有迁移+增强）
    trading.py         # /trading + 开关 + 确认回调
    menu.py            # /start /menu /help
```

## 数据流

```
用户发送命令/点击按钮
  → python-telegram-bot 接收
  → auth 装饰器验证 chat_id
  → commands.py 分发到对应 handler
  → handler 直接读 Redis/PostgreSQL 获取数据
  → formatters.py 格式化消息
  → keyboards.py 构建 inline buttons
  → bot 发送/编辑消息
```

## 写操作确认流程

```
用户点击 [切换策略: 激进趋势]
  → handler 发送确认消息："确认切换到 激进趋势？"
     [✅ 确认]  [❌ 取消]
  → 用户点击确认
  → handler 写入 Redis + 发布事件
  → 更新消息为执行结果
```

## 安全控制

```python
def authorized(func):
    async def wrapper(update, context):
        if update.effective_chat.id != config.telegram_chat_id:
            return  # 静默忽略
        return await func(update, context)
    return wrapper
```

所有 command handler 和 callback handler 统一使用。

## 回调数据格式

Inline button 的 `callback_data` 限制 64 字节，统一格式：

```
{module}:{action}:{params}
```

示例：
- `pos:detail:BTCUSDT` — 查看 BTC 持仓详情
- `dec:detail:12345` — 查看决策 #12345 详情
- `str:switch:aggressive` — 切换到激进策略
- `str:confirm:aggressive` — 确认切换
- `trd:toggle:on` — 开启交易
- `trd:confirm:on` — 确认开启
- `adv:accept:123:0` — 采纳 Advisory #123 建议 0
- `menu:main` — 返回主菜单

## bot.py 生命周期

```python
class TelegramBot:
    def __init__(self, config, redis, db):
        self.app = Application.builder().token(config.telegram_bot_token).build()
        self.notifier = Notifier(self.app.bot, config)
        register_commands(self.app, config, redis, db)

    async def start(self):
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling()

    async def stop(self):
        await self.app.updater.stop()
        await self.app.stop()
```

`notifier` 属性对外暴露，供现有推送逻辑调用，保持向后兼容。

## 各 Handler 详细设计

### overview.py

- **数据源**：Redis `trading:account_state` + PostgreSQL `decisions` 表 + `daily_stats` 表
- **摘要消息**：
  ```
  📊 账户概览
  ━━━━━━━━━━━━
  💰 账户权益: 1,234.56 USDT
  📈 已实现盈亏: +56.78 USDT
  📉 未实现盈亏: -12.34 USDT
  📊 总盈亏: +44.44 USDT
  ━━━━━━━━━━━━
  📌 当前持仓: 2 个
  🧠 今日决策: 15 次
  🎯 历史胜率: 62.5%
  ```
- **按钮**：`[📈 查看持仓] [🧠 查看决策]`

### positions.py

- **数据源**：Redis `trading:account_state` 中的 positions
- **摘要列表**：
  ```
  📈 当前持仓 (2)
  ━━━━━━━━━━━━
  1. BTC/USDT 🟢多 +2.3%
  2. ETH/USDT 🔴空 -0.8%
  ```
- **详情**：点击按钮显示入场价、数量、杠杆、入场时间、未实现盈亏

### decisions.py

- **数据源**：PostgreSQL `decisions` 表
- **摘要列表**：最近 10 条
  ```
  🧠 最近决策
  ━━━━━━━━━━━━
  1. 02-12 14:30 BTC 开多 置信度:85
  2. 02-12 13:00 ETH 持有 置信度:72
  3. 02-12 12:00 BTC 平仓 置信度:90
  ```
- **详情**：点击查看入场价、止损止盈、策略、理由

### llm_usage.py

- **数据源**：PostgreSQL `llm_usage` 表
- **摘要消息**：
  ```
  🤖 LLM 调用统计
  ━━━━━━━━━━━━
  📊 总调用: 1,234 次
  📝 总 Token: 2.5M
  💰 总费用: $12.34
  💵 今日费用: $1.23
  ```
- **按钮**：`[📋 最近调用记录]` → 最近 5 条摘要，每条可点击查看详情

### strategy.py

- **数据源**：Redis `trading:strategy` + 策略预设配置
- **消息**：当前策略名 + 运行时长 + 参数摘要
- **按钮**：每个可用预设一个按钮，点击触发切换确认流程

### advisory.py

- **数据源**：PostgreSQL `advisories` + `advisory_suggestions` 表
- **摘要列表**：待处理 Advisory，显示紧急程度、触发类型、建议数
- **操作**：采纳/拒绝/确认 inline keyboard + `[🔄 立即分析]` 触发按钮

### trading.py

- **数据源**：Redis `trading:config`
- **消息**：交易开关状态 + 决策间隔
- **按钮**：`[🟢 开启交易]` / `[🔴 关闭交易]`，需二次确认

## 迁移步骤

1. 创建 `telegram/` 包，搭建骨架
2. 迁移 `telegram.py` → `notifier.py`，保持推送功能不变
3. 实现 `bot.py`，统一管理 bot 实例
4. 实现 `auth.py`、`keyboards.py`、`formatters.py` 工具模块
5. 逐个实现 handlers：menu → overview → positions → decisions → llm_usage → strategy → advisory → trading
6. 更新调用方：将 `TelegramNotifier` 导入路径更新为新包
7. 测试

## 不做的事情（YAGNI）

- 不做群聊支持，只支持私聊
- 不做多语言，固定中文
- 不做图表图片生成（纯文本+emoji）
- 不做定时报告推送
- 不做消息缓存/防抖
