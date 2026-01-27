# 快速启动端到端测试

## ⚠️ 常见问题修复

### 问题 1: "Invalid Api-Key ID" 错误

**原因**: Binance Testnet API Key 可能已过期或无效

**解决方案**（5分钟）:

1. **访问新的 Binance Testnet**:
   ```
   https://testnet.binancefuture.com/
   ```

2. **用 GitHub 登录**（Testnet 使用 GitHub OAuth）

3. **生成新的 API Key**:
   - 点击右上角头像 → API Keys
   - 点击 "Create API Key"
   - 确保勾选: ✅ Enable Reading, ✅ Enable Futures
   - 复制 API Key (64位) 和 Secret (64位)
   - ⚠️ Secret 只显示一次

4. **更新 .env 文件**:
   ```bash
   TESTNET_API_KEY=你的新的64位API_KEY
   TESTNET_API_SECRET=你的新的64位SECRET
   ```

**详细指南**: `docs/BINANCE_TESTNET_SETUP.md`

---

### 问题 2: "SyntaxError" 错误

**错误命令**:
```bash
uv run python scripts/start_long_term_test.sh  # ❌ 错误
```

**正确命令**:
```bash
bash scripts/start_long_term_test.sh  # ✅ 正确
```

**原因**: `.sh` 是 bash 脚本，不能用 `python` 运行

---

## 🚀 测试步骤

### 1. 快速验证（5分钟）

**运行 Binance Testnet 集成测试**:
```bash
uv run python scripts/test_binance_testnet.py
```

**预期结果**:
```
✓ PASS - Testnet Connection
✓ PASS - K-line Data Consistency
✓ PASS - Complete Trading Flow

Passed: 3/3 tests
```

---

### 2. 长期测试（1-4周，可选）

#### 方式 A: 使用 tmux（推荐）

```bash
# 启动新会话
tmux new -s trader-test

# 运行测试
bash scripts/start_long_term_test.sh

# 退出但保持运行
# 按 Ctrl+B, 然后按 D

# 重新连接
tmux attach -t trader-test

# 停止测试
# Ctrl+C, 然后 exit
```

#### 方式 B: 后台运行

```bash
nohup bash scripts/start_long_term_test.sh > logs/e2e_test.log 2>&1 &
```

---

## 📊 监控测试

### 实时日志

```bash
# 查看实时输出
tail -f logs/e2e_test.log

# 查看最近决策
grep "Decision:" logs/e2e_test.log | tail -20

# 统计决策类型
grep -c "open_long" logs/e2e_test.log
grep -c "open_short" logs/e2e_test.log
grep -c "hold" logs/e2e_test.log
```

### 健康检查

```bash
# 检查最近1天的运行状况
uv run python scripts/check_e2e_health.py --days 1

# 检查最近7天
uv run python scripts/check_e2e_health.py --days 7
```

---

## 🔍 故障排除

### 检查配置

```bash
# 1. 确认测试模式
grep "TRADING_MODE" .env
# 应显示: TRADING_MODE=testnet

# 2. 确认交易所
grep "TESTNET_EXCHANGE" .env
# 应显示: TESTNET_EXCHANGE=binance

# 3. 验证 API Key 长度
grep "TESTNET_API_KEY" .env | awk -F= '{print length($2)}'
# 应显示: 64
```

### 快速验证 API Key

```bash
uv run python -c "
import asyncio
from dotenv import load_dotenv
load_dotenv()

from ai_trader.exchange import create_exchange_client

async def test():
    try:
        client = create_exchange_client()
        ticker = await client.get_ticker('BTC/USDT')
        print(f'✓ 连接成功！BTC/USDT: {ticker.last_price}')
        await client.close()
    except Exception as e:
        print(f'✗ 连接失败: {e}')

asyncio.run(test())
"
```

---

## 📋 测试计划建议

### 阶段 1: 快速验证（今天）
- ✅ 配置 Binance Testnet API Key
- ✅ 运行 `test_binance_testnet.py`
- ✅ 验证 3/3 测试通过

### 阶段 2: 短期测试（本周）
- ✅ 运行 24 小时
- ✅ 检查决策质量
- ✅ 验证无错误

### 阶段 3: 长期验证（1-4周）
- ✅ 持续运行
- ✅ 每天健康检查
- ✅ 观察盈亏曲线

---

## 📚 相关文档

- **Binance Testnet 配置**: `docs/BINANCE_TESTNET_SETUP.md`
- **完整测试指南**: `TEST_GUIDE.md`
- **快速开始**: `QUICK_START_TESTS.md`
- **项目完成报告**: `PROJECT_COMPLETION.md`

---

**立即开始**:

```bash
# 1. 获取 API Key
# 访问 https://testnet.binancefuture.com/

# 2. 更新 .env

# 3. 运行测试
uv run python scripts/test_binance_testnet.py

# 4. 启动长期测试（可选）
bash scripts/start_long_term_test.sh
```
