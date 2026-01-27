# Binance Testnet API 配置指南

## 问题诊断

当前错误：`Invalid Api-Key ID`

这通常意味着：
1. API Key 不是来自正确的 Binance Testnet
2. API Key 已过期或被删除
3. API Key 格式不正确

---

## 正确获取 Binance Testnet API Key

### Step 1: 访问 Binance Testnet

**官方 Testnet 地址**：
- **Futures Testnet**: https://testnet.binancefuture.com/

⚠️ **注意**：不要使用旧的 testnet.binance.vision（已废弃）

### Step 2: 注册/登录 Testnet 账户

1. 访问 https://testnet.binancefuture.com/
2. 使用 GitHub 账号登录（Binance Testnet 使用 GitHub OAuth）
3. 首次登录会自动创建账户并获得测试资金（10,000 USDT）

### Step 3: 生成 API Key

1. 登录后，点击右上角头像
2. 选择 **API Keys** 或 **API Management**
3. 点击 **Create API Key**
4. 系统会生成：
   - **API Key**: 64个字符的字符串
   - **Secret Key**: 64个字符的字符串
5. **立即保存**（Secret Key 只显示一次）

### Step 4: 配置权限（重要）

确保 API Key 具有以下权限：
- ✅ **Enable Reading** (读取权限)
- ✅ **Enable Futures** (合约交易权限)
- ❌ **Enable Withdrawals** (不需要，测试环境无法提现)

### Step 5: 更新 .env 文件

将生成的 API Key 复制到 `.env` 文件：

```bash
# Binance Testnet API 凭证
TESTNET_API_KEY=你的_64位_API_KEY
TESTNET_API_SECRET=你的_64位_SECRET_KEY
```

**格式检查**：
- API Key 和 Secret 都应该是 **64个字符**
- 只包含大小写字母和数字
- 示例格式：`qGPEKpQMPw7LRCMrnF2qUL1POswj4FMT837LwaBAvjZw2144VjkJxL7BinUwW47c`

---

## 常见问题

### Q1: 找不到 API Management 菜单？

**解决方案**：
- 确认访问的是 https://testnet.binancefuture.com/（不是主网）
- 确认已用 GitHub 登录
- 刷新页面或清除浏览器缓存

### Q2: API Key 显示 "Invalid Api-Key ID"？

**可能原因**：
1. ❌ 使用了旧 testnet 的 API Key
2. ❌ API Key 被删除或过期
3. ❌ 复制时多了空格或换行符

**解决方案**：
- 删除旧 API Key
- 重新生成新的 API Key
- 仔细复制粘贴，避免多余字符

### Q3: 测试账户余额不足？

**解决方案**：
- Testnet 会定期重置账户余额为 10,000 USDT
- 如果余额不足，可以在网站上申请充值
- 或者删除当前账户，重新用 GitHub 登录（会重新获得测试资金）

### Q4: 如何验证 API Key 是否正确？

运行测试脚本：
```bash
# 方法1：快速验证（仅连接测试）
uv run python -c "
import asyncio
from ai_trader.exchange import create_exchange_client

async def test():
    client = create_exchange_client()
    ticker = await client.get_ticker('BTC/USDT')
    print(f'BTC/USDT 价格: {ticker.last_price}')
    await client.close()

asyncio.run(test())
"

# 方法2：完整测试
uv run python scripts/test_binance_testnet.py
```

---

## Binance Testnet 特性

### 优势
- ✅ **完全免费**：无需真实资金
- ✅ **真实环境**：与主网 API 完全一致
- ✅ **10,000 USDT**：每个账户初始测试资金
- ✅ **支持合约**：USDT-M Futures 完整支持
- ✅ **GitHub 登录**：无需 KYC

### 限制
- ⚠️ 测试数据可能与主网略有延迟（1-5秒）
- ⚠️ 订单簿深度可能较浅
- ⚠️ 定期重置（通常每月1次）
- ⚠️ API Rate Limit 较严格（每分钟 1200 请求）

---

## 快速验证清单

配置完成后，检查以下项目：

- [ ] 访问的是 https://testnet.binancefuture.com/（不是主网）
- [ ] API Key 长度为 64 个字符
- [ ] Secret Key 长度为 64 个字符
- [ ] .env 文件中 `TRADING_MODE=testnet`
- [ ] .env 文件中 `TESTNET_EXCHANGE=binance`
- [ ] API Key 权限包含 "Enable Reading" 和 "Enable Futures"
- [ ] 没有多余的空格或换行符

---

## 参考资料

- **Binance Futures Testnet**: https://testnet.binancefuture.com/
- **API 文档**: https://binance-docs.github.io/apidocs/futures/en/
- **CCXT Binance 文档**: https://docs.ccxt.com/#/exchanges/binance

---

**配置完成后，运行测试**：
```bash
uv run python scripts/test_binance_testnet.py
```

如果仍然报错，请检查：
1. .env 文件是否正确保存
2. 是否重启了终端（使环境变量生效）
3. API Key 是否在 Binance Testnet 网站上显示为 "Active"
