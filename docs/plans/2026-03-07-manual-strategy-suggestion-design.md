# 手动策略建议功能设计

## 概述

在策略页面（dashboard.strategy.tsx）策略卡片列表上方，新增「获取策略建议」按钮。点击后调用 LLM，基于当前所有可用信息，推荐最适合的策略预设。只是建议，不自动切换，但提供快捷切换按钮。

## 后端

### API 端点

`POST /api/strategy-presets/suggest`

- 无请求参数
- 返回：`{ recommended_preset: str, reason: str, market_state: str }`

### 实现

复用 `AdvisoryEngine`，新增 `suggest_strategy()` 方法：

1. 使用 `AdvisoryContextBuilder` 收集当前上下文（市场数据、持仓、账户、技术指标等）
2. 加载 7 个策略预设的描述（从 `presets.py`）
3. 使用专门的策略推荐 prompt 调用 LLM
4. 解析 LLM 返回的 JSON 结果
5. 不执行切换，不保存 advisory 记录

### Prompt 要点

- 输入：当前市场状态、技术指标、持仓信息、账户数据、7 个预设的描述和适用场景
- 输出 JSON：recommended_preset（预设 ID）、reason（推荐理由）、market_state（市场状态判断）
- 要求 LLM 结合当前市场环境分析哪个预设最合适

### 新增文件

- `dashboard/app/routes/api.strategy-presets.suggest.ts` - API 路由

### 修改文件

- `src/ai_trader/advisory/engine.py` - 新增 `suggest_strategy()` 方法

## 前端

### UI 位置

`dashboard/app/routes/dashboard.strategy.tsx`，策略卡片列表上方。

### 组件

1. **「获取策略建议」按钮**
   - 点击后显示 loading 状态
   - 再次点击可刷新建议

2. **建议结果卡片**（内嵌展开）
   - 推荐策略名称（高亮）
   - 当前市场状态标签
   - 推荐理由（LLM 生成文字）
   - 「切换到此策略」按钮 - 复用已有的策略激活 API (`api.strategy-presets.activate.ts`)
   - 「关闭」按钮 - 收起卡片

### 交互流程

1. 用户点击「获取策略建议」
2. 按钮进入 loading 状态
3. 调用 `POST /api/strategy-presets/suggest`
4. 返回后展开建议卡片
5. 用户可选择「切换到此策略」或「关闭」
6. 切换操作复用已有的激活流程（含锁定检查）

## 实施阶段

### Phase 1: 后端 - suggest_strategy 方法
- 在 `AdvisoryEngine` 中新增 `suggest_strategy()` 方法
- 编写策略推荐专用 prompt
- 单元测试

### Phase 2: 后端 - API 路由
- 新增 `api.strategy-presets.suggest.ts`
- 调用后端 `suggest_strategy()`
- 返回 JSON 结果

### Phase 3: 前端 - UI 组件
- 在策略页面添加按钮和建议卡片
- 调用 API 并展示结果
- 实现「切换到此策略」功能（复用激活 API）
