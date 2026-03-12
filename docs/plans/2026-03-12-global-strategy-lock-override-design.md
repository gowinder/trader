# 全局策略锁定重载 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 锁定全局策略后，所有交易对统一使用全局引擎，忽略 per-symbol 配置，阻止所有修改，前端醒目提示。

**Architecture:** 后端 scheduler 增加 `_strategy_locked` 状态控制引擎选择；API 层统一锁定检查返回 HTTP 423；前端两个页面增加锁定横幅和控件禁用。

**Tech Stack:** Python (asyncio, asyncpg), TypeScript (React 19, React Router 7), Redis Pub/Sub, PostgreSQL

---

## Task 1: 后端 — scheduler.py 锁定状态 + 引擎选择

**Files:**
- Modify: `src/ai_trader/scheduler.py:121-126` (添加 `_strategy_locked` 属性)
- Modify: `src/ai_trader/scheduler.py:397-451` (`_load_active_preset` 读取锁定状态)
- Modify: `src/ai_trader/scheduler.py:2571` (引擎选择逻辑)

**Step 1: 添加 `_strategy_locked` 属性**

在 `scheduler.py` 第 121 行 `self._active_preset_name` 后添加：

```python
        self._strategy_locked: bool = False  # Global strategy lock
```

**Step 2: 在 `_load_active_preset` 中同步锁定状态**

在 `_load_active_preset` 方法中，`if preset_data:` 块内（约第 433 行后），添加锁定状态同步：

```python
        if preset_data:
            # 同步锁定状态
            self._strategy_locked = preset_data.get("is_locked", False)
            logger.info(f"Strategy lock state: {self._strategy_locked}")
```

注意：这段代码要在现有 `if preset_data:` 块的最前面，在 `preset_config = preset_data.get("config", preset_data)` 之前。

**Step 3: 修改引擎选择逻辑**

将第 2571 行：
```python
            engine = self._symbol_engines.get(symbol, self.decision_engine)
```

改为：
```python
            if self._strategy_locked:
                engine = self.decision_engine
            else:
                engine = self._symbol_engines.get(symbol, self.decision_engine)
```

**Step 4: 提交**

```bash
git add src/ai_trader/scheduler.py
git commit -m "feat: add _strategy_locked state to scheduler for global lock override"
```

---

## Task 2: 后端 — strategy_service.py 写保护

**Files:**
- Modify: `src/ai_trader/persistence/strategy_service.py:12-16` (添加异常类)
- Modify: `src/ai_trader/persistence/strategy_service.py:86-96` (添加 `is_strategy_locked` 方法)
- Modify: `src/ai_trader/persistence/strategy_service.py:186-209` (`update_preset_config` 添加锁定检查)
- Modify: `src/ai_trader/persistence/strategy_service.py:260-282` (`delete_preset` 添加锁定检查)

**Step 1: 添加异常类**

在 `strategy_service.py` 文件顶部 `import` 之后、`class StrategyPresetService` 之前添加：

```python
class StrategyLockedException(Exception):
    """Raised when a modification is attempted while strategy is locked."""
    pass
```

**Step 2: 添加 `is_strategy_locked` 方法**

在 `get_active_preset` 方法之后添加：

```python
    async def is_strategy_locked(self) -> bool:
        """Check if the current active strategy is locked."""
        row = await self.db.fetchval(
            """SELECT COALESCE(is_locked, FALSE)
            FROM active_strategy
            WHERE deactivated_at IS NULL
            ORDER BY activated_at DESC LIMIT 1"""
        )
        return bool(row)
```

**Step 3: 在 `update_preset_config` 开头添加锁定检查**

在 `update_preset_config` 方法体最前面（`preset = await self.get_preset_by_id(preset_id)` 之前）插入：

```python
        # Check global lock
        if await self.is_strategy_locked():
            raise StrategyLockedException("策略已锁定，请先解锁再修改")
```

**Step 4: 在 `delete_preset` 开头添加锁定检查**

在 `delete_preset` 方法体最前面插入相同的检查。

**Step 5: 在 `reset_preset` 开头添加锁定检查**

在 `reset_preset` 方法体最前面插入相同的检查。

**Step 6: 提交**

```bash
git add src/ai_trader/persistence/strategy_service.py
git commit -m "feat: add strategy lock write protection to strategy_service"
```

---

## Task 3: 前端 API — 6 个端点添加锁定检查

**Files:**
- Modify: `dashboard/app/routes/api.strategy-presets.update.ts`
- Modify: `dashboard/app/routes/api.strategy-presets.delete.ts`
- Modify: `dashboard/app/routes/api.strategy-presets.reset.ts`
- Modify: `dashboard/app/routes/api.strategy-presets.suggest.ts`
- Modify: `dashboard/app/routes/api.symbol-strategy-suggest.ts`
- Modify: `dashboard/app/routes/api.symbols.ts`

所有端点的锁定检查模式相同：在业务逻辑开始前查询 `active_strategy.is_locked`，如果锁定则返回 HTTP 423。

**Step 1: `api.strategy-presets.update.ts` — 在 `try` 块开头（第 28-29 行之间）添加**

```typescript
    // Check global strategy lock
    const lockCheck = await sql`
      SELECT COALESCE(is_locked, false) as is_locked
      FROM active_strategy WHERE deactivated_at IS NULL
      ORDER BY activated_at DESC LIMIT 1
    `;
    if (lockCheck.length > 0 && lockCheck[0].is_locked) {
      await sql.end();
      return Response.json({ error: "策略已锁定，请先解锁再修改" }, { status: 423 });
    }
```

**Step 2: `api.strategy-presets.delete.ts` — 在 `try` 块开头（第 21-22 行之间）添加**

```typescript
    // Check global strategy lock
    const lockCheck = await sql`
      SELECT COALESCE(is_locked, false) as is_locked
      FROM active_strategy WHERE deactivated_at IS NULL
      ORDER BY activated_at DESC LIMIT 1
    `;
    if (lockCheck.length > 0 && lockCheck[0].is_locked) {
      await sql.end();
      return Response.json({ error: "策略已锁定，请先解锁再修改" }, { status: 423 });
    }
```

**Step 3: `api.strategy-presets.reset.ts` — 在 `try` 块开头（第 110-111 行之间）添加**

同样的锁定检查代码。

**Step 4: `api.strategy-presets.suggest.ts` — 在 action 的 `try` 块开头添加**

这个端点只有 Redis，没有 sql。需要从 Redis 读取锁定状态：

```typescript
    // Check global strategy lock from Redis
    const activePreset = await client.get("strategy:active_preset");
    if (activePreset) {
      const data = JSON.parse(activePreset);
      if (data.is_locked) {
        await client.disconnect();
        return Response.json({ error: "策略已锁定，请先解锁再修改" }, { status: 423 });
      }
    }
```

**Step 5: `api.symbol-strategy-suggest.ts` — 在 action 的 `client = await getRedisClient()` 之后添加**

同样从 Redis 读取锁定状态的检查。

**Step 6: `api.symbols.ts` — 在 action 的 `try` 块内，`configured` 解析之后、业务逻辑之前添加**

```typescript
    // Check global strategy lock
    const lockCheck = await sql`
      SELECT COALESCE(is_locked, false) as is_locked
      FROM active_strategy WHERE deactivated_at IS NULL
      ORDER BY activated_at DESC LIMIT 1
    `;
    if (lockCheck.length > 0 && lockCheck[0].is_locked) {
      await sql.end();
      return Response.json({ error: "策略已锁定，请先解锁再修改" }, { status: 423 });
    }
```

**Step 7: 提交**

```bash
git add dashboard/app/routes/api.strategy-presets.update.ts \
       dashboard/app/routes/api.strategy-presets.delete.ts \
       dashboard/app/routes/api.strategy-presets.reset.ts \
       dashboard/app/routes/api.strategy-presets.suggest.ts \
       dashboard/app/routes/api.symbol-strategy-suggest.ts \
       dashboard/app/routes/api.symbols.ts
git commit -m "feat: add HTTP 423 lock guard to all strategy mutation API endpoints"
```

---

## Task 4: 前端 — 策略页面锁定横幅 + 控件禁用

**Files:**
- Modify: `dashboard/app/routes/dashboard.strategy.tsx`

**Step 1: 添加锁定横幅组件**

在 `StrategyPage` 组件的 return JSX 中，页面标题后、主内容前添加锁定横幅：

```tsx
{locked && (
  <div className="mb-4 flex items-center justify-between rounded-lg border border-yellow-500/30 bg-yellow-500/10 px-4 py-3">
    <div className="flex items-center gap-2 text-sm text-yellow-200">
      <span>🔒</span>
      <span>策略已全局锁定 — 所有交易对使用统一策略，所有修改已禁用。解锁后恢复独立配置。</span>
    </div>
    <button
      type="button"
      onClick={handleToggleLock}
      disabled={togglingLock}
      className="rounded bg-yellow-600 px-3 py-1 text-xs font-medium text-white hover:bg-yellow-500 disabled:opacity-50"
    >
      {togglingLock ? "处理中..." : "解锁"}
    </button>
  </div>
)}
```

**Step 2: 禁用所有编辑控件**

在所有修改类按钮和交互控件上添加 `disabled={locked}` 属性：
- 激活按钮（已有 `disabled={locked}`，确认保留）
- AI 建议按钮
- 编辑参数的输入框、滑块
- 重置按钮
- 删除按钮
- save-as 按钮（可选，设计文档中说保存副本不拦截，但 UI 一致性考虑也禁用）

在已有 locked 禁用逻辑的基础上扩展——找到所有 `suggesting`、编辑相关按钮，添加 `|| locked` 条件。

**Step 3: 提交**

```bash
git add dashboard/app/routes/dashboard.strategy.tsx
git commit -m "feat: add lock banner and disable controls on strategy page"
```

---

## Task 5: 前端 — Symbols 页面锁定横幅 + 控件禁用

**Files:**
- Modify: `dashboard/app/routes/dashboard.symbols.tsx`

**Step 1: 获取锁定状态**

在 `SymbolsPage` 组件中添加锁定状态：

```tsx
const [strategyLocked, setStrategyLocked] = useState(false);
```

在 `fetchData` 中从 `/api/strategy-presets` 获取锁定状态：

```tsx
const fetchData = useCallback(async () => {
  try {
    const [symbolsRes, presetsRes, strategyRes] = await Promise.all([
      fetch("/api/symbols"),
      fetch("/api/presets-list"),
      fetch("/api/strategy-presets"),
    ]);
    // ... existing parsing ...
    const strategyJson = await strategyRes.json();
    setStrategyLocked(strategyJson.isLocked === true);
  } catch {
    // use defaults
  } finally {
    setLoading(false);
  }
}, []);
```

**Step 2: 添加锁定横幅**

在页面标题后、symbols 列表前添加横幅（与策略页相同样式）：

```tsx
{strategyLocked && (
  <div className="mb-4 flex items-center justify-between rounded-lg border border-yellow-500/30 bg-yellow-500/10 px-4 py-3">
    <div className="flex items-center gap-2 text-sm text-yellow-200">
      <span>🔒</span>
      <span>策略已全局锁定 — 所有交易对使用全局策略，配置修改已禁用。</span>
    </div>
    <a href="/dashboard/strategy" className="rounded bg-yellow-600 px-3 py-1 text-xs font-medium text-white hover:bg-yellow-500">
      前往解锁
    </a>
  </div>
)}
```

**Step 3: 禁用所有编辑控件**

- 所有 `Switch` (启用/禁用交易对): `disabled={strategyLocked}`
- 预设选择 `<select>`: `disabled={strategyLocked}`
- 参数输入/滑块: `disabled={strategyLocked}`
- 保存按钮: `disabled={saving || strategyLocked}`
- AI 批量建议按钮: `disabled={batchSuggesting || strategyLocked}`
- 重置按钮: `disabled={strategyLocked}`

**Step 4: 在交易对卡片上显示"使用全局策略"标签**

锁定时，每个已启用交易对的卡片上显示标签：

```tsx
{strategyLocked && isEnabled && (
  <span className="rounded bg-yellow-500/20 px-2 py-0.5 text-[10px] text-yellow-300">
    使用全局策略
  </span>
)}
```

**Step 5: 提交**

```bash
git add dashboard/app/routes/dashboard.symbols.tsx
git commit -m "feat: add lock banner and disable controls on symbols page"
```

---

## Task 6: 集成验证

**Step 1: 验证前端构建**

```bash
cd dashboard && npm run build
```

Expected: 构建成功，无 TypeScript 错误。

**Step 2: 验证后端导入**

```bash
uv run python -c "from ai_trader.persistence.strategy_service import StrategyPresetService, StrategyLockedException; print('OK')"
```

Expected: `OK`

**Step 3: 最终提交**

如有修复，提交修复。
