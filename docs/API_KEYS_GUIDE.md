# 🔑 API Keys 完整获取指南

## 📋 所需 API 汇总

| API 服务 | 用途 | 免费额度 | 成本 | 必需性 | 状态 |
|---------|------|---------|------|--------|------|
| **OpenRouter** | LLM 模型 | 部分模型免费 | $0-$5/百万tokens | ✅ 必需 | ✅ 已配置 |
| **Binance** | 交易所（数据+交易） | 完全免费 | $0 | ✅ 必需 | ⚠️ Testnet受限 |
| **CryptoPanic** | 加密新闻情绪 | 100次/天 | $0（免费） | ⭐ 推荐 | ❌ 需获取 |
| **NewsAPI** | 通用新闻情绪 | 100次/天 | $0（免费） | ⭐ 推荐 | ❌ 需获取 |
| **Gemini** | 备用 LLM | 免费（有限制） | $0 | 🔄 可选 | 🔄 可配置 |

---

## 1️⃣ LLM API（已配置 ✅）

### OpenRouter（当前使用）

**已配置模型**：
- 主模型：`xiaomi/mimo-v2-flash:free` ✅ 完全免费
- 备用：`x-ai/grok-4.1-fast`

**免费额度**：
- ✅ Mimo V2 Flash：完全免费，无限制
- ✅ 多个免费模型可选

**无需操作** - 当前配置已优化

---

### 🆕 Gemini 2.0（推荐添加）

**优势**：
- ✅ **完全免费**（个人使用）
- ✅ **性能优异**（Gemini 2.0 Flash）
- ✅ **高速响应**（比 OpenRouter 更快）
- ✅ **慷慨限制**：
  - 免费：15 RPM, 1M TPM, 1.5K RPD
  - 无需信用卡

**获取步骤**（5分钟）：

1. **访问 Google AI Studio**：
   ```
   https://aistudio.google.com/apikey
   ```

2. **创建 API Key**：
   - 点击 "Get API Key"
   - 选择 "Create API key in new project"
   - 复制生成的 API Key

3. **配置到 .env**：
   ```bash
   # 添加到 .env 文件
   LLM_PROVIDER=gemini
   LLM_API_KEY=你的_Gemini_API_Key
   LLM_MODEL=gemini-2.0-flash-exp
   LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta
   ```

**推荐模型**：
- `gemini-2.0-flash-exp` - 最新实验版，性能最佳
- `gemini-2.0-flash-thinking-exp` - 带推理过程
- `gemini-1.5-flash` - 稳定版

**限制**：
```
免费配额（个人）：
- 15 requests/分钟
- 1,000,000 tokens/分钟
- 1,500 requests/天

足够日常使用！
```

**参考**：
- API 文档：https://ai.google.dev/gemini-api/docs
- 定价：https://ai.google.dev/pricing

---

## 2️⃣ 交易所 API

### Binance（当前使用，部分可用）

**状态**：
- ✅ 公开 API 可用（价格、K线）
- ❌ Futures Testnet 已废弃（账户、交易）

**当前配置** ✅ 无需修改

**如需完整测试，三种方案**：

#### 方案 A: Binance Demo Trading（待验证）

**URL**: https://demo-fapi.binance.com/

**特点**：
- ✅ 完全免费
- ✅ 虚拟资金
- ⚠️ API Key 获取方式待确认

**状态**：需要研究如何获取 Demo API Key

---

#### 方案 B: 真实环境小额测试（慎用）

**仅当必要时使用**：

1. **注册 Binance 账户**：
   ```
   https://www.binance.com/
   ```

2. **完成 KYC 验证**（必需）

3. **存入小额资金**：
   - 建议：$10-20 USDT
   - 仅用于测试

4. **创建 API Key**：
   - 登录 → 右上角头像 → API Management
   - 创建 API Key
   - 权限：✅ Enable Reading, ✅ Enable Futures
   - ⚠️ **不要**勾选 Enable Withdrawals

5. **严格风控配置**：
   ```bash
   # .env
   TRADING_MODE=live
   MAX_POSITION_PERCENT=1.0  # 最大1%仓位
   STOP_LOSS_PERCENT=0.5  # 0.5%止损
   MAX_DAILY_LOSS_PERCENT=1.0  # 每日1%亏损限制
   ```

⚠️ **风险**：即使小额也有亏损风险

---

### 其他交易所（可选）

#### Bybit Testnet

**URL**: https://testnet.bybit.com/

**免费额度**：
- ✅ 完全免费
- ✅ 虚拟资金测试

**获取步骤**：
1. 访问 https://testnet.bybit.com/
2. 注册 Testnet 账户
3. 登录 → API → Create API Key
4. 配置权限：Read, Trade

**配置**：
```bash
TESTNET_EXCHANGE=bybit
TESTNET_API_KEY=你的_Bybit_Testnet_Key
TESTNET_API_SECRET=你的_Bybit_Secret
```

**状态**：备用方案，Bybit Testnet 可能仍可用

---

## 3️⃣ 情绪分析 API（推荐获取）

### CryptoPanic（加密新闻）

**免费额度**：
- ✅ 100 次/天
- ✅ 完全免费

**获取步骤**（3分钟）：

1. **访问官网**：
   ```
   https://cryptopanic.com/developers/api/
   ```

2. **注册账户**：
   - 填写邮箱、密码
   - 验证邮箱

3. **获取 API Key**：
   - 登录后自动显示
   - 或访问：https://cryptopanic.com/developers/api/

4. **配置到 .env**：
   ```bash
   # 情绪分析配置
   ENABLE_SENTIMENT_ANALYSIS=true
   CRYPTOPANIC_API_KEY=你的_CryptoPanic_Key
   ```

**API 格式**：
```
示例：7a9f8b1c2d3e4f5g6h7i8j9k0l1m2n3o
长度：32个字符
```

**限制**：
- 100 requests/天
- 每个请求可获取 20-50 条新闻
- 缓存策略：15分钟 TTL（系统已配置）

**实际可用性**：
- 每15分钟刷新一次 = 每天96次请求
- **刚好在限额内** ✅

---

### NewsAPI（通用新闻）

**免费额度**：
- ✅ 100 次/天
- ✅ 完全免费（开发者计划）

**获取步骤**（3分钟）：

1. **访问官网**：
   ```
   https://newsapi.org/
   ```

2. **注册账户**：
   - 点击 "Get API Key"
   - 填写邮箱、名字
   - 验证邮箱

3. **获取 API Key**：
   - 注册完成后立即显示
   - 或访问：https://newsapi.org/account

4. **配置到 .env**：
   ```bash
   NEWSAPI_KEY=你的_NewsAPI_Key
   ```

**API 格式**：
```
示例：1a2b3c4d5e6f7g8h9i0j1k2l3m4n5o6p
长度：32个字符
```

**限制**：
```
免费计划（Developer）：
- 100 requests/天
- 仅限过去1个月的新闻
- 每次最多100条结果

足够使用！
```

**注意**：
- ⚠️ 免费版仅用于开发测试
- ⚠️ 商业使用需升级（$449/月）
- ✅ 个人交易测试完全够用

---

## 4️⃣ 配置汇总

### 最小配置（当前可用）

```bash
# ============= LLM 配置 =============
LLM_PROVIDER=openrouter
LLM_API_KEY=YOUR_OPENROUTER_KEY
LLM_MODEL=xiaomi/mimo-v2-flash:free

# ============= 交易所配置 =============
TRADING_MODE=testnet
TESTNET_EXCHANGE=binance
TESTNET_API_KEY=你的_Binance_Testnet_Key
TESTNET_API_SECRET=你的_Binance_Testnet_Secret

# ============= 情绪分析（可选）=============
ENABLE_SENTIMENT_ANALYSIS=false  # 暂时关闭
```

**可运行功能**：
- ✅ 数据获取
- ✅ 技术分析
- ✅ AI 决策
- ✅ 量化策略
- ❌ 情绪分析（未配置）

---

### 推荐配置（完整功能）

```bash
# ============= LLM 配置 =============
# 方案1: OpenRouter（当前）
LLM_PROVIDER=openrouter
LLM_API_KEY=sk-or-v1-xxx
LLM_MODEL=xiaomi/mimo-v2-flash:free

# 方案2: Gemini（推荐）
LLM_PROVIDER=gemini
LLM_API_KEY=你的_Gemini_Key
LLM_MODEL=gemini-2.0-flash-exp
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta

# ============= 交易所配置 =============
TRADING_MODE=testnet
TESTNET_EXCHANGE=binance
TESTNET_API_KEY=你的_Binance_Key
TESTNET_API_SECRET=你的_Binance_Secret

# ============= 情绪分析配置 =============
ENABLE_SENTIMENT_ANALYSIS=true  # ✅ 启用
CRYPTOPANIC_API_KEY=你的_CryptoPanic_Key
NEWSAPI_KEY=你的_NewsAPI_Key
SENTIMENT_WEIGHT=0.2
SENTIMENT_CACHE_TTL=900
SENTIMENT_MAX_REQUESTS_PER_HOUR=80
```

**完整功能**：
- ✅ 数据获取
- ✅ 技术分析
- ✅ AI 决策
- ✅ 量化策略
- ✅ 情绪分析

---

## 🎯 获取优先级

### 立即获取（5分钟）

1. **Gemini API** ⭐⭐⭐
   - 完全免费
   - 性能更好
   - 替代 OpenRouter

### 本周获取（10分钟）

2. **CryptoPanic API** ⭐⭐
   - 完全免费
   - 启用情绪分析
   - 提升决策质量

3. **NewsAPI** ⭐⭐
   - 完全免费
   - 补充新闻来源
   - 增强情绪分析

### 可选（按需）

4. **Bybit Testnet** ⭐
   - Binance 替代方案
   - 完整交易测试

5. **Binance 真实账户** ⚠️
   - 仅当必需时
   - 需要 KYC
   - 有资金风险

---

## 💰 成本分析

### 完全免费方案（推荐）

| 服务 | 月成本 | 备注 |
|------|--------|------|
| Gemini 2.0 | **$0** | 个人使用免费 |
| Binance Testnet | **$0** | 公开数据免费 |
| CryptoPanic | **$0** | 100次/天足够 |
| NewsAPI | **$0** | 100次/天足够 |
| **总计** | **$0/月** | ✅ 零成本 |

### 使用成本估算

**每日 API 调用**：
- LLM（Gemini）：~100次 × $0 = **$0**
- CryptoPanic：~96次 < 100限制 = **$0**
- NewsAPI：~96次 < 100限制 = **$0**
- Binance 公开 API：无限制 = **$0**

**月度成本**：**$0** ✅

---

## 🚀 快速开始

### 步骤 1: 获取 Gemini API（5分钟）

```bash
# 1. 访问
https://aistudio.google.com/apikey

# 2. 创建 API Key

# 3. 更新 .env
LLM_PROVIDER=gemini
LLM_API_KEY=你的_Gemini_Key
LLM_MODEL=gemini-2.0-flash-exp
```

### 步骤 2: 获取情绪分析 API（10分钟）

```bash
# 1. CryptoPanic
https://cryptopanic.com/developers/api/
# 注册 → 获取 Key → 复制

# 2. NewsAPI
https://newsapi.org/
# Get API Key → 注册 → 复制

# 3. 更新 .env
ENABLE_SENTIMENT_ANALYSIS=true
CRYPTOPANIC_API_KEY=你的_CryptoPanic_Key
NEWSAPI_KEY=你的_NewsAPI_Key
```

### 步骤 3: 测试运行

```bash
# 测试连接
source .venv/bin/activate
python -c "
import asyncio
from ai_trader.sentiment.data_sources import CryptoPanicSource

async def test():
    source = CryptoPanicSource('你的_CryptoPanic_Key')
    news = await source.fetch_news('BTC', limit=10, hours=24)
    print(f'✓ 获取到 {len(news)} 条新闻')

asyncio.run(test())
"

# 运行完整系统
python scripts/test_binance_testnet.py
```

---

## ❓ FAQ

### Q: 必须获取所有 API 吗？

**A**: 不必
- ✅ **最小**：LLM（已有）+ Binance（已有）
- ⭐ **推荐**：+ Gemini + 情绪分析
- 🔄 **完整**：+ Bybit 备用

### Q: Gemini 和 OpenRouter 选哪个？

**A**: **Gemini 更优**
- ✅ 完全免费（OpenRouter 免费模型性能一般）
- ✅ 响应更快
- ✅ 性能更好（Gemini 2.0）

### Q: 情绪分析有必要吗？

**A**: **推荐但非必需**
- ✅ 免费，零成本
- ✅ 提升决策质量（Phase 5 功能）
- ⭐ 市场极端情况预警
- 🔄 可随时启用/禁用

### Q: 免费额度够用吗？

**A**: **完全够用** ✅

每日使用：
- Gemini：~100次 < 1,500限制 ✅
- CryptoPanic：~96次 < 100限制 ✅
- NewsAPI：~96次 < 100限制 ✅

系统已优化缓存，最大化利用免费额度。

---

## 📚 参考资料

- **Gemini API**: https://ai.google.dev/
- **CryptoPanic API**: https://cryptopanic.com/developers/api/
- **NewsAPI**: https://newsapi.org/docs
- **Binance API**: https://binance-docs.github.io/apidocs/futures/en/
- **Bybit Testnet**: https://testnet.bybit.com/

---

**更新时间**: 2026-01-27
**推荐方案**: Gemini + CryptoPanic + NewsAPI = $0/月
