# 策略卡片参数编辑与另存功能设计

日期: 2026-03-07

## 概述

为策略页面的每个策略卡片增加参数编辑、覆盖保存、另存为新卡片、重置默认值、删除自定义卡片等功能。

## 设计决策

| 决策项 | 结论 |
|--------|------|
| 可编辑范围 | 全部参数，分层展示（核心 + 高级折叠） |
| 另存命名规则 | 源名称 + 日期后缀，如 `稳健趋势-0307` |
| 自定义卡片删除 | 支持 |
| 编辑触发方式 | 卡片内直接编辑（就地编辑） |
| Reset 默认值来源 | 后端代码 `presets.py` 中的硬编码值 |

## 一、数据模型变更

### 数据库迁移

`strategy_presets` 表新增字段：

```sql
ALTER TABLE strategy_presets ADD COLUMN source_preset_id INTEGER NULL;
ALTER TABLE strategy_presets ADD COLUMN is_modified BOOLEAN DEFAULT FALSE;
```

- `source_preset_id` — 自定义卡片关联的源系统预设 ID（系统预设为 NULL）
- `is_modified` — 系统预设是否被用户修改过（用于显示 reset 按钮）

### 卡片类型区分

| 属性 | 系统预设 | 已修改的系统预设 | 用户自定义 |
|------|---------|----------------|-----------|
| `is_system` | true | true | false |
| `is_modified` | false | true | — |
| `source_preset_id` | NULL | NULL | 源预设 ID |
| 可编辑 | YES | YES | YES |
| 覆盖保存 | YES (标记 modified) | YES | YES |
| 另存为 | YES | YES | YES |
| Reset | — | YES | — |
| 删除 | — | — | YES |

### 自动命名规则

另存时 `name` 生成：`{source_name}-{MMDD}`，如已存在则追加序号 `{source_name}-{MMDD}-2`。
`display_name` 同理：`稳健趋势-0307`、`稳健趋势-0307-2`。

## 二、API 设计

### 2.1 覆盖保存 — `PUT /api/strategy-presets/:id`

```typescript
// 请求体
{ config: PresetConfig }

// 逻辑
// 系统预设：更新 config_json，设 is_modified = true
// 自定义预设：直接更新 config_json
// 如果该预设是当前激活的，同步发布 Redis 事件通知后端重载配置
```

### 2.2 另存为 — `POST /api/strategy-presets/save-as`

```typescript
// 请求体
{ sourcePresetId: number, config: PresetConfig, displayName?: string }

// 逻辑
// 自动生成 name 和 displayName（基于源预设 + 日期）
// 如果用户提供了 displayName 则使用用户的
// 插入新记录：is_system=false, source_preset_id=源ID
// 名称冲突时自动追加序号（-2、-3）
```

### 2.3 恢复默认 — `POST /api/strategy-presets/:id/reset`

```typescript
// 仅限 is_system=true && is_modified=true 的预设
// 调用后端获取 presets.py 中的默认配置
// 更新 config_json，设 is_modified = false
```

### 2.4 删除 — `DELETE /api/strategy-presets/:id`

```typescript
// 仅限 is_system=false
// 如果是当前激活策略，拒绝删除（返回 409）
```

### 2.5 获取系统默认值 — `GET /api/strategy-presets/defaults`

```typescript
// 从后端 presets.py 获取所有系统预设的默认配置
// 供 reset 功能使用
// 通过 Redis 请求后端返回，或直接 HTTP 调后端接口
```

## 三、前端交互流程

### 3.1 卡片状态机

每张卡片有三种模式：**查看态** → **编辑态** → **保存确认**

**查看态**（默认）：
- 参数以只读文本展示（同现在）
- 显示"编辑"按钮进入编辑态
- 系统已修改预设：额外显示"Reset"按钮
- 自定义预设：额外显示"删除"按钮

**编辑态**（点击"编辑"后）：
- 核心参数区域变为输入框（数值用 number input + 滑块）
- "高级参数"折叠区域可展开，内含策略列表多选、时间周期多选等
- 底部出现操作栏：`取消` | `保存` | `另存为`
- 参数有变化时才启用保存按钮（脏检测）

**保存确认**：
- 点击"保存"：系统预设弹确认"将覆盖默认配置，可通过 Reset 恢复"，自定义预设直接保存
- 点击"另存为"：弹出小输入框显示自动生成的名称（如 `稳健趋势-0307`），用户可修改，确认后创建新卡片
- 点击"取消"：丢弃修改恢复查看态

### 3.2 参数分层展示

**核心参数**（直接可见）：
- AI 权重 (`ai_weight`)
- 量化权重 (`quant_weight`)
- 止损 ATR 倍数 (`stop_loss_atr_multiplier`)
- 止盈 ATR 倍数 (`take_profit_atr_multiplier`)
- 最小交易间隔 (`min_trade_interval_seconds`)
- 最大仓位比例 (`max_position_pct`)

**高级参数**（折叠）：
- 启用策略列表 (`enabled_strategies`)
- 策略权重 (`strategy_weights`)
- 时间周期 (`timeframes`)
- 允许加仓 (`enable_pyramid`)
- 最大加仓次数 (`max_pyramid_times`)
- 启用情感分析 (`enable_sentiment`)
- 情感权重 (`sentiment_weight`)
- 最小盈利阈值 (`min_profit_threshold`)
- 仅限市价单 (`use_market_order_only`)

### 3.3 参数输入控件

| 参数类型 | 控件 |
|---------|------|
| 权重（0-1） | 滑块 + 数值输入 |
| 整数（间隔秒数） | 数值输入 |
| 浮点（ATR倍数） | 数值输入，step=0.1 |
| 百分比（仓位） | 滑块 + 数值输入 |
| 布尔（加仓/情感） | 开关 Switch |
| 策略列表 | 多选 Checkbox 组 |
| 时间周期 | 多选 Checkbox 组 |
| 策略权重 | 每个已选策略对应一个数值输入 |

## 四、错误处理与边界情况

### 验证规则

前端和后端双重验证，规则与现有 Pydantic 模型一致：
- `enabled_strategies` 至少选 1 个
- 已选策略的权重之和 > 0
- 数值范围遵循 Pydantic Field 约束（如 `min_trade_interval_seconds >= 60`）
- 前端输入时实时校验，不合法的字段标红并禁用保存按钮

### 边界情况

| 场景 | 处理 |
|------|------|
| 删除当前激活的自定义策略 | 拒绝，提示先切换到其他策略 |
| 编辑当前激活的策略并保存 | 允许，保存后发 Redis 事件通知后端热重载配置 |
| 另存名称冲突 | 自动追加序号（-2、-3） |
| 多端同时编辑同一卡片 | 后写入覆盖（乐观并发，不做锁） |
| Reset 系统预设 | 从后端代码获取默认值覆盖，清除 is_modified 标记 |
| 自定义卡片的源预设被删除 | 不影响，source_preset_id 仅用于命名参考 |

### 数据迁移

现有 7 个系统预设无需改动，新增的 `is_modified` 默认 false，`source_preset_id` 默认 NULL，完全向后兼容。

## 五、实施阶段

### Phase 1: 数据层
- 数据库迁移（新增 `source_preset_id`、`is_modified` 字段）
- 后端新增获取系统默认配置的接口

### Phase 2: API 层
- 实现 PUT 覆盖保存接口
- 实现 POST 另存为接口
- 实现 POST reset 接口
- 实现 DELETE 删除接口
- 实现 GET defaults 接口

### Phase 3: 前端编辑态
- 卡片编辑态 UI（核心参数输入 + 高级参数折叠）
- 脏检测逻辑
- 参数实时校验

### Phase 4: 前端保存流程
- 覆盖保存 + 确认弹窗
- 另存为 + 自动命名 + 名称编辑
- Reset 按钮
- 删除按钮 + 确认
- 保存后刷新卡片列表
