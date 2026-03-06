# 策略锁定功能 - 任务清单

## Phase 1: 数据层 — 数据库 + Redis + 后端服务

- [x] 1.1 数据库迁移：`active_strategy` 表新增 `is_locked BOOLEAN DEFAULT FALSE`
- [x] 1.2 `strategy_service.py`：`activate_preset()` 增加 `is_locked` 参数，写入 DB 和 Redis
- [x] 1.3 `strategy_service.py`：新增 `set_strategy_lock(is_locked)` 方法
- [x] 1.4 `strategy_service.py`：`activate_preset()` 内增加锁定检查，锁定时拒绝切换
- [x] 1.5 `strategy_service.py`：`get_active_preset()` 返回值包含 `is_locked`
- [x] 1.6 `advisory/executors.py`：`StrategyExecutor.execute()` 增加锁定检查
- [x] 1.7 Phase 1 测试 ✓ 19 passed

## Phase 2: 前端 API 层

- [x] 2.1 `api.strategy-presets.activate.ts`：POST 请求增加 `is_locked` 参数，锁定时返回 423
- [x] 2.2 新增 `api.strategy-presets.lock.ts`：切换锁定状态端点
- [x] 2.3 `api.strategy-presets.ts`：返回数据包含 `is_locked` 状态
- [x] 2.4 Phase 2 测试 ✓ TypeScript typecheck passed

## Phase 3: 前端 UI

- [x] 3.1 `dashboard.strategy.tsx`：当前激活策略卡片增加锁定开关
- [x] 3.2 `dashboard.strategy.tsx`：锁定时禁用其他策略的激活按钮
- [x] 3.3 `dashboard.strategy.tsx`：激活确认对话框增加"同时锁定"checkbox
- [x] 3.4 Phase 3 测试 ✓ 19 passed + TypeScript typecheck passed
