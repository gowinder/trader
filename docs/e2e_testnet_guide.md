# 端到端 Testnet 测试指南

## 概述

端到端测试系统会在 Binance Testnet 上持续运行，执行完整的交易流程：

1. **多时间框架分析**（15m, 1h, 4h, 1d）
2. **技术分析**（MA、RSI、ATR、支撑阻力）
3. **Confluence Score 计算**
4. **交易决策**（基于专业规则）
5. **日志记录**

## 快速开始

### 方式 1：前台运行（推荐用于测试）

```bash
python scripts/run_e2e_testnet.py
```

- 按 `Ctrl+C` 停止
- 实时查看输出
- 适合短期测试和调试

### 方式 2：后台运行（使用 tmux）

```bash
# 启动新的 tmux 会话
tmux new -s trading

# 在 tmux 中运行
python -u scripts/run_e2e_testnet.py

# 分离会话（保持运行）：按 Ctrl+B 然后按 D
```

**重新连接**:
```bash
tmux attach -t trading
```

**停止**:
```bash
# 连接到会话
tmux attach -t trading

# 按 Ctrl+C 停止脚本

# 退出 tmux
exit
```

### 方式 3：后台运行（使用 screen）

```bash
# 启动新的 screen 会话
screen -S trading

# 在 screen 中运行
python -u scripts/run_e2e_testnet.py

# 分离会话：按 Ctrl+A 然后按 D
```

**重新连接**:
```bash
screen -r trading
```

**停止**:
```bash
# 连接到会话
screen -r trading

# 按 Ctrl+C 停止

# 退出 screen
exit
```

### 方式 4：后台运行（使用 nohup）

```bash
# 启动
nohup python -u scripts/run_e2e_testnet.py > logs/e2e_testnet.log 2>&1 &

# 保存 PID
echo $! > logs/e2e_testnet.pid

# 查看日志
tail -f logs/e2e_testnet.log

# 停止
kill $(cat logs/e2e_testnet.pid)
rm logs/e2e_testnet.pid
```

## 运行参数

### 主要配置（在脚本中修改）

```python
SYMBOL = "BTCUSDT"                # 交易对
TIMEFRAMES = ["15m", "1h", "4h", "1d"]  # 时间框架
CHECK_INTERVAL = 300              # 检查间隔（秒），默认5分钟
MAX_DAILY_TRADES = 3              # 每日最大交易次数
RISK_PER_TRADE = 0.01             # 默认风险（1%）
HIGH_CONFIDENCE_RISK = 0.02       # 高置信度风险（2%）
```

### 快速调整检查间隔

```bash
# 1分钟检查一次（快速测试）
python scripts/run_e2e_testnet.py  # 修改 CHECK_INTERVAL = 60

# 15分钟检查一次（日常运行）
python scripts/run_e2e_testnet.py  # 修改 CHECK_INTERVAL = 900
```

## 系统输出示例

```
================================================================================
📊 Iteration #1 - 2026-01-27 10:53:34
================================================================================
💰 Account Balance: 5000.00 USDT
📈 Trades Today: 0/3
💵 Daily P&L: +0.00 USDT

📊 Fetching multi-timeframe data...
   ✅  15m:    UPTREND (RSI: 60.1)
   ✅   1h:   SIDEWAYS (RSI: 62.8)
   ✅   4h:   SIDEWAYS (RSI: 45.2)
   ✅   1d:  DOWNTREND (RSI: 29.6)

🎯 Multi-Timeframe Analysis:
   Overall Trend: SIDEWAYS
   Confluence Score: 25.00%

💡 Trading Decision: HOLD
   Reason: Low confluence (25.00%) - conflicting timeframe signals

⏱️  Next check in 300s (5.0 minutes)...
```

## 日志文件

### 主日志
- **位置**: `logs/e2e_testnet.log`
- **内容**: 系统运行日志、迭代记录
- **查看**: `tail -f logs/e2e_testnet.log`

### 决策日志
- **位置**: `logs/e2e_testnet_decisions.log`
- **内容**: 详细的交易决策记录
- **查看**: `tail -f logs/e2e_testnet_decisions.log`

## 交易规则

### 开仓条件（ALL required）

1. **Multi-Timeframe Alignment**:
   - Confluence Score ≥ 50%（中等设置）
   - Confluence Score ≥ 70%（高置信度设置）

2. **明确趋势**:
   - Overall Trend = UPTREND 或 DOWNTREND
   - SIDEWAYS 市场 = HOLD

3. **每日限制**:
   - 最多 3 笔交易/天
   - 每日亏损限制：3% 账户余额

4. **入场时机**:
   - LONG: 价格接近支撑位（< 2% 偏离）
   - SHORT: 价格接近阻力位（< 2% 偏离）

### 仓位管理

**固定比例风险法**:
```
Position Size = (账户余额 × 风险%) / (入场价 - 止损价)
```

**风险比例**:
- 普通设置（Confluence 50-70%）: **1%**
- 高置信度（Confluence ≥ 70%）: **2%**

**止损设置**:
- LONG: `max(支撑位, 入场价 - 2×ATR)`
- SHORT: `min(阻力位, 入场价 + 2×ATR)`

**止盈设置**:
- 最小风险回报比：**2:1**
- TP1 = 入场价 ± (止损距离 × 2)

### 决策逻辑示例

| Confluence | Trend | 决策 | 原因 |
|-----------|-------|------|------|
| 25% | SIDEWAYS | HOLD | 低 Confluence，多空分歧 |
| 50% | SIDEWAYS | HOLD | 无明确方向 |
| 50% | UPTREND | HOLD | 价格距离支撑 > 2% |
| 75% | UPTREND | **OPEN_LONG** | 高 Confluence，价格接近支撑 |
| 75% | DOWNTREND | **OPEN_SHORT** | 高 Confluence，价格接近阻力 |

## 监控和管理

### 实时监控

```bash
# 查看实时日志
tail -f logs/e2e_testnet.log

# 同时查看两个日志
tail -f logs/e2e_testnet.log logs/e2e_testnet_decisions.log
```

### 系统状态

```bash
# 检查进程是否运行
ps aux | grep run_e2e_testnet

# 查看日志文件大小
ls -lh logs/

# 统计决策次数
grep -c "Trading Decision" logs/e2e_testnet_decisions.log
```

### 紧急停止

```bash
# 找到进程
ps aux | grep run_e2e_testnet.py

# 杀掉进程
kill <PID>

# 强制杀掉
kill -9 <PID>
```

## 故障排查

### 问题 1: 脚本不输出任何内容

**原因**: Python 输出缓冲

**解决**: 使用 `-u` 选项
```bash
python -u scripts/run_e2e_testnet.py
```

### 问题 2: API 连接失败

**原因**: API Key 无效或过期

**解决**:
1. 访问 https://testnet.binancefuture.com/
2. 重新生成 API Key
3. 更新 `.env` 文件

### 问题 3: 进程意外停止

**原因**: 可能是网络错误或异常

**解决**:
1. 检查日志文件 `logs/e2e_testnet.log`
2. 查找错误信息
3. 重新启动系统

## 性能优化

### 调整检查间隔

**快速测试**（1分钟）:
```python
CHECK_INTERVAL = 60
```

**正常运行**（5分钟）:
```python
CHECK_INTERVAL = 300  # 默认
```

**保守运行**（15分钟）:
```python
CHECK_INTERVAL = 900
```

### 减少 API 调用

**减少时间框架**:
```python
TIMEFRAMES = ["1h", "4h"]  # 只用2个时间框架
```

## 长期运行建议

### 使用 tmux（推荐）

**优点**:
- 会话持久化
- 可以随时重新连接
- 稳定可靠

**示例**:
```bash
# 启动
tmux new -s trading
python -u scripts/run_e2e_testnet.py

# 分离：Ctrl+B, D

# 重新连接
tmux attach -t trading
```

### 定期检查

**建议检查频率**: 每天1-2次

**检查项目**:
1. 进程是否运行
2. 日志文件大小（避免过大）
3. 账户余额变化
4. 决策记录

**自动化检查脚本**:
```bash
#!/bin/bash
# check_trading.sh

if ps aux | grep -q "run_e2e_testnet.py"; then
    echo "✅ Trading system is running"
    echo "Decisions today: $(grep -c "Trading Decision" logs/e2e_testnet_decisions.log)"
    tail -5 logs/e2e_testnet.log
else
    echo "❌ Trading system is NOT running"
fi
```

## 数据分析

### 统计决策

```bash
# 总决策次数
grep -c "Trading Decision" logs/e2e_testnet_decisions.log

# HOLD 决策次数
grep -c "Action: HOLD" logs/e2e_testnet_decisions.log

# OPEN_LONG 决策次数
grep -c "Action: OPEN_LONG" logs/e2e_testnet_decisions.log

# OPEN_SHORT 决策次数
grep -c "Action: OPEN_SHORT" logs/e2e_testnet_decisions.log
```

### 查看特定决策

```bash
# 查看所有 OPEN_LONG 决策
grep -A 10 "Action: OPEN_LONG" logs/e2e_testnet_decisions.log

# 查看高 Confluence 决策（≥70%）
grep -B 5 "Confluence Score: [0-9]*[.][7-9]" logs/e2e_testnet_decisions.log
```

## 安全提示

1. ✅ **仅在 Testnet 运行** - 这是测试系统
2. ✅ **不执行实际订单** - 当前版本只记录决策
3. ✅ **API Key 权限** - 只需要 Reading 权限
4. ⚠️ **不要在生产环境运行** - 未经充分测试

## 下一步计划

### Phase 3 完成项
- [x] 多时间框架分析
- [x] Confluence Score 计算
- [x] 交易决策逻辑
- [x] 日志记录
- [x] 端到端测试系统

### 待实现功能
- [ ] 实际订单执行（需要 Trading 权限）
- [ ] 仓位管理（追踪、加仓、减仓）
- [ ] 移动止损自动调整
- [ ] 交易日志集成
- [ ] 性能报告生成
- [ ] Email/Telegram 通知

## 参考资料

- **项目文档**: `docs/ai_quant_system_plan.todo.md`
- **Phase 3 总结**: `docs/phase3_completion_summary.md`
- **集成测试**: `scripts/test_phase3_integration.py`
- **API 文档**: https://testnet.binancefuture.com/

---

**最后更新**: 2026-01-27
**状态**: ✅ 运行正常
**下次验证**: Phase 3 E2E 测试（建议运行 2 周）
