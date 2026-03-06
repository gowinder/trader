# 策略锁定功能设计

## 概述

在策略页面增加"锁定"开关。锁定后，LLM Advisory 和事件驱动触发的策略切换将被阻止，当前策略保持不变。Advisory 建议仍然正常生成和显示，但无法执行策略切换类建议，用户需手动解锁后才能执行。

## 数据层

### 数据库

`active_strategy` 表新增字段：

```sql
ALTER TABLE active_strategy ADD COLUMN is_locked BOOLEAN DEFAULT FALSE;
```

- 锁定状态跟随激活记录，切换新策略时自动重置为 `FALSE`
- 只有当前活跃记录（`deactivated_at IS NULL`）的 `is_locked` 有意义

### Redis

`strategy:active_preset` 的 JSON 值中增加 `is_locked` 字段：

```json
{
  "preset_id": 3,
  "preset_name": "mild_scalping",
  "is_locked": true
}
```

## 后端改动

### strategy_service.py

1. **`activate_preset(preset_id, is_locked=False)`**
   - 激活前检查当前策略是否锁定，锁定则拒绝切换，返回错误
   - 激活时可通过参数同时设置锁定状态
   - 写入 `active_strategy` 记录时包含 `is_locked` 字段
   - 更新 Redis 时包含 `is_locked`

2. **新增 `set_strategy_lock(is_locked: bool)`**
   - 更新当前活跃记录的 `is_locked` 字段
   - 同步更新 Redis
   - 发布 `strategy:preset:updated` 事件

### advisory/executors.py — StrategyExecutor

`execute()` 方法增加锁定检查：

```python
async def execute(self, suggestion, context):
    # 检查策略锁定
    active = await self.strategy_service.get_active_preset()
    if active and active.get("is_locked"):
        return {
            "success": False,
            "error": "strategy_locked",
            "message": "当前策略已锁定，无法自动切换"
        }
    # 继续原有执行逻辑...
```

## 前端改动

### API 端点

1. **`api.strategy-presets.activate.ts`** — POST 请求增加 `is_locked` 参数
   - 后端兜底：锁定时返回 `423 Locked`

2. **新增 `api.strategy-presets.lock.ts`** — 切换锁定状态
   - `POST /api/strategy-presets/lock`
   - 请求体：`{ is_locked: boolean }`
   - 返回：更新后的激活策略信息

3. **`api.strategy-presets.ts`** — 列表/详情返回数据包含 `is_locked` 状态

### dashboard.strategy.tsx

1. **当前激活策略卡片**
   - 增加锁定开关（Switch/Toggle），带锁图标
   - 锁定时有视觉标识（锁图标高亮、边框颜色变化）

2. **其他策略卡片**
   - 锁定时"激活"按钮禁用，hover 提示"当前策略已锁定，请先解锁"

3. **激活确认对话框**
   - 增加"同时锁定此策略"checkbox

## 拦截点汇总

| 位置 | 检查方式 | 锁定时行为 |
|------|---------|-----------|
| `StrategyExecutor.execute()` | 读取 Redis/DB | 返回失败，记录原因 |
| `api.strategy-presets.activate.ts` | 查询 DB | 返回 423 Locked |
| `dashboard.strategy.tsx` | 前端状态 | 禁用激活按钮 |

## 不做的事

- 不加过期时间，纯手动控制
- 不加独立锁定表，直接用 `active_strategy.is_locked` 字段
- 不阻止 Advisory 建议的生成和显示，只阻止执行
- 不影响用户手动解锁后的正常操作流程
