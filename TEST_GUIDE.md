# 测试指令手册

## 📋 测试分类

### 1. 快速集成测试（5分钟）
- Phase 2: Binance Testnet 连接和数据验证

### 2. 长期端到端测试（1-2周）
- Phase 2: Testnet 稳定性验证（1周）
- Phase 3: 仓位管理实盘验证（2周）
- Phase 4: 混合决策模式验证（1周）

---

## 一、Phase 2: Binance Testnet 快速集成测试

### 运行指令

```bash
# 1. 激活虚拟环境
source .venv/bin/activate

# 2. 运行测试
python scripts/test_binance_testnet.py
```

### 预期输出

```
============================================================
PHASE 2: BINANCE TESTNET INTEGRATION TESTS
============================================================

=== Test 1: Testnet Connection ===
✓ Connection successful
  Symbol: BTC/USDT
  Price: $95,234.50
  Bid/Ask: $95,233.00 / $95,236.00

=== Test 2: K-line Data Consistency ===
✓ Data validation passed
  Received: 100 klines
  Price range: $94,500.00 - $95,800.00

=== Test 3: Complete Trading Flow ===
Step 1: Fetching market data...
  ✓ Current price: $95,234.50
Step 2: Fetching klines for analysis...
  ✓ Received 50 klines
Step 3: Fetching account info...
  ✓ Total balance: $10,000.00
  ✓ Available: $10,000.00
Step 4: Simulating trading decision...
  ✓ Decision: LONG at $95,236.00
Step 5: Calculating order parameters...
  ✓ Size: 0.001 BTC
  ✓ Stop loss: $93,331.28
  ✓ Take profit: $98,193.28

✓ Complete trading flow validated successfully
  [Data Fetch] → [Analysis] → [Decision] → [Order Params]

============================================================
TEST SUMMARY
============================================================
✓ PASS - Testnet Connection
✓ PASS - K-line Data Consistency
✓ PASS - Complete Trading Flow

Passed: 3/3 tests

✓ All Phase 2 integration tests passed!
```

### 验证标准
- ✅ 连接 Binance Testnet 成功
- ✅ 获取实时价格数据
- ✅ 获取 100 根 K 线数据
- ✅ K 线数据 OHLCV 一致性验证
- ✅ 账户信息查询成功
- ✅ 完整交易流程模拟成功

### 故障排查

**问题1: 连接失败**
```bash
# 检查网络
ping testnet.binancefuture.com

# 检查API凭证
grep "TESTNET_API" .env

# 测试API连接
curl -H "X-MBX-APIKEY: YOUR_KEY" \
  "https://testnet.binancefuture.com/fapi/v1/ping"
```

**问题2: DNS错误**
```bash
# 检查DNS
nslookup testnet.binancefuture.com

# 使用代理（如果需要）
export https_proxy="http://your-proxy:port"
python scripts/test_binance_testnet.py
```

---

## 二、长期端到端测试

### 2.1 准备工作

```bash
# 1. 确保配置正确
cat .env | grep -E "(TRADING_MODE|TESTNET_)"

# 应输出:
# TRADING_MODE=testnet
# TESTNET_EXCHANGE=binance
# TESTNET_API_KEY=xxx
# TESTNET_API_SECRET=xxx

# 2. 创建日志目录
mkdir -p logs data/trades

# 3. 激活虚拟环境
source .venv/bin/activate
```

### 2.2 启动长期测试（使用 tmux 推荐）

#### 方式1: 使用 tmux（推荐）

```bash
# 创建新的 tmux 会话
tmux new -s trader-test

# 在 tmux 中启动测试
source .venv/bin/activate
python scripts/run_e2e_testnet.py

# 分离会话（保持后台运行）
# 按键: Ctrl+B, 然后按 D

# 重新连接查看
tmux attach -t trader-test

# 查看所有会话
tmux ls

# 停止测试: 在 tmux 中按 Ctrl+C
```

#### 方式2: 使用 nohup（后台运行）

```bash
# 启动后台测试
nohup python scripts/run_e2e_testnet.py > logs/e2e_nohup.log 2>&1 &

# 记录进程ID
echo $! > /tmp/trader_test.pid

# 查看运行状态
tail -f logs/e2e_testnet.log

# 停止测试
kill $(cat /tmp/trader_test.pid)
```

#### 方式3: 使用 screen

```bash
# 创建 screen 会话
screen -S trader-test

# 启动测试
source .venv/bin/activate
python scripts/run_e2e_testnet.py

# 分离会话: Ctrl+A, 然后按 D
# 重新连接: screen -r trader-test
```

### 2.3 监控运行状态

#### 实时日志

```bash
# 查看主日志
tail -f logs/e2e_testnet.log

# 查看决策日志
tail -f logs/e2e_testnet_decisions.log

# 查看最近20条决策
tail -20 logs/e2e_testnet_decisions.log
```

#### 统计信息

```bash
# 决策总数
grep -c "Trading Decision" logs/e2e_testnet_decisions.log

# 各类决策数量
echo "HOLD: $(grep -c "action=HOLD" logs/e2e_testnet_decisions.log)"
echo "LONG: $(grep -c "action=LONG" logs/e2e_testnet_decisions.log)"
echo "SHORT: $(grep -c "action=SHORT" logs/e2e_testnet_decisions.log)"

# Confluence 分布
grep "confluence=" logs/e2e_testnet_decisions.log | \
  awk -F'confluence=' '{print $2}' | \
  awk '{print $1}' | \
  sort | uniq -c
```

#### 进程监控

```bash
# 检查进程是否运行
ps aux | grep run_e2e_testnet

# 查看资源占用
top -p $(pgrep -f run_e2e_testnet)

# 查看网络连接
netstat -an | grep -E "(binance|443)"
```

### 2.4 测试计划

#### Week 1: Phase 2 验证（7天）
**目标**: 验证 Testnet 连接稳定性和数据质量

```bash
# 启动测试
tmux new -s phase2-test
source .venv/bin/activate
python scripts/run_e2e_testnet.py
```

**监控重点**:
- 每天检查日志 2 次
- 连接成功率 >99%
- 数据获取延迟 <500ms
- 无致命错误

**验证指标**:
```bash
# 每天执行
python scripts/check_e2e_health.py --days 1

# 输出示例:
# Day 1 Health Report:
# - Uptime: 99.8%
# - Avg Latency: 234ms
# - Errors: 0 critical, 2 warnings
# - Decisions: 142 total (HOLD: 98, LONG: 28, SHORT: 16)
```

#### Week 2-3: Phase 3 验证（14天）
**目标**: 验证仓位管理逻辑实盘表现

```bash
# 确保 Week 1 无问题后再启动
tmux new -s phase3-test
source .venv/bin/activate
python scripts/run_e2e_testnet.py --enable-position-management
```

**监控重点**:
- 仓位计算准确性
- 金字塔加仓触发正确
- 移动止损工作正常
- 每日亏损限制有效

**验证指标**:
```bash
# 每周执行
python scripts/analyze_position_management.py --week 2

# 输出示例:
# Week 2 Position Management Report:
# - Trades: 47
# - Pyramid entries: 12 (25.5%)
# - Avg position size: 0.0082 BTC
# - Max position: 0.0245 BTC
# - Daily loss limit triggered: 0 times
# - Trailing stop triggered: 23 times
```

#### Week 4: Phase 4 验证（7天）
**目标**: 验证混合决策模式（量化+AI）

```bash
# 确保 Week 2-3 无问题后再启动
tmux new -s phase4-test
source .venv/bin/activate
python scripts/run_e2e_testnet.py \
  --enable-position-management \
  --enable-quant-strategies \
  --quant-weight 0.5 \
  --ai-weight 0.5
```

**监控重点**:
- 量化信号生成正常
- AI 决策无异常
- 信号融合逻辑正确
- 实际收益符合回测预期

**验证指标**:
```bash
# 每天执行
python scripts/analyze_hybrid_performance.py --days 7

# 输出示例:
# Week 4 Hybrid Decision Report:
# - Quant signals: 234
# - AI signals: 156
# - Agreed: 89 (38.0%)
# - Conflicted: 67 (28.6%)
# - Win rate: 54.2%
# - Total return: +3.8%
# - Max drawdown: 6.7%
# - Sharpe ratio: 0.42
```

### 2.5 停止测试

#### 优雅停止（推荐）

```bash
# 方式1: 在 tmux/screen 中按 Ctrl+C

# 方式2: 发送 SIGTERM 信号
kill -SIGTERM $(pgrep -f run_e2e_testnet)

# 等待 30 秒让程序保存数据
sleep 30

# 确认进程已停止
ps aux | grep run_e2e_testnet
```

#### 强制停止（不推荐，可能丢失数据）

```bash
kill -9 $(pgrep -f run_e2e_testnet)
```

### 2.6 测试结果分析

```bash
# 生成完整报告
python scripts/generate_e2e_report.py \
  --start-date 2026-01-27 \
  --end-date 2026-02-10 \
  --output reports/e2e_phase2-4.html

# 输出文件:
# - reports/e2e_phase2-4.html  (可视化报告)
# - reports/e2e_phase2-4.json  (原始数据)
# - reports/e2e_phase2-4.csv   (交易记录)
```

---

## 三、测试文件清单

### 测试脚本
```
scripts/test_binance_testnet.py          - Phase 2 快速集成测试
scripts/run_e2e_testnet.py               - 长期端到端测试（已存在）
scripts/check_e2e_health.py              - 健康检查（需创建）
scripts/analyze_position_management.py   - 仓位管理分析（需创建）
scripts/analyze_hybrid_performance.py    - 混合决策分析（需创建）
scripts/generate_e2e_report.py           - 报告生成（需创建）
```

### 日志文件
```
logs/e2e_testnet.log               - 主日志
logs/e2e_testnet_decisions.log     - 决策日志
logs/trading.log                   - 交易系统日志
```

### 数据文件
```
data/trades/                       - 交易记录
data/cache/                        - K线数据缓存
```

---

## 四、常见问题

### Q1: 测试卡住不动了
```bash
# 检查进程状态
ps aux | grep python
top -p <PID>

# 检查网络连接
netstat -an | grep ESTABLISHED | grep 443

# 查看最新日志
tail -50 logs/e2e_testnet.log

# 重启测试
kill $(pgrep -f run_e2e_testnet)
sleep 5
python scripts/run_e2e_testnet.py
```

### Q2: 磁盘空间不足
```bash
# 检查磁盘使用
df -h

# 压缩旧日志
gzip logs/*.log.1 logs/*.log.2

# 清理缓存（谨慎！）
du -sh data/cache
# rm -rf data/cache/*  # 确认后执行
```

### Q3: API 限流
```bash
# 检查请求频率
grep "rate limit" logs/e2e_testnet.log

# 调整请求间隔（修改配置）
# 在 .env 中添加:
# ANALYSIS_INTERVAL=300  # 5分钟改为300秒

# 重启测试
```

### Q4: 内存泄漏
```bash
# 监控内存使用
watch -n 60 'ps aux | grep python | grep -v grep'

# 如果内存持续增长，定期重启
# 添加到 crontab:
0 2 * * * /path/to/restart_test.sh
```

---

## 五、最佳实践

### ✅ 推荐做法

1. **使用 tmux/screen**: 避免 SSH 断线导致测试中断
2. **定期检查**: 每天至少查看一次日志
3. **备份数据**: 每周备份 `data/trades/` 和重要日志
4. **监控资源**: 使用 `top`/`htop` 监控 CPU/内存
5. **记录问题**: 遇到异常立即记录到问题日志

### ⚠️ 注意事项

1. **仅 Testnet**: 禁止在生产环境运行
2. **资金安全**: 定期检查 Testnet 账户余额
3. **网络稳定**: 确保运行环境网络稳定
4. **日志清理**: 避免日志文件占满磁盘
5. **进程监控**: 防止进程僵死

---

## 六、快速参考卡片

```
┌──────────────────────────────────────────────────────────┐
│  🚀 快速启动                                              │
├──────────────────────────────────────────────────────────┤
│  Phase 2 测试:  python scripts/test_binance_testnet.py  │
│  长期测试:      tmux new -s test                        │
│                source .venv/bin/activate                 │
│                python scripts/run_e2e_testnet.py         │
│  分离会话:      Ctrl+B, D                               │
│  重新连接:      tmux attach -t test                     │
├──────────────────────────────────────────────────────────┤
│  📊 监控                                                 │
├──────────────────────────────────────────────────────────┤
│  实时日志:      tail -f logs/e2e_testnet.log            │
│  决策统计:      grep -c "Decision" logs/*_decisions.log │
│  进程状态:      ps aux | grep run_e2e                   │
├──────────────────────────────────────────────────────────┤
│  🛑 停止                                                 │
├──────────────────────────────────────────────────────────┤
│  优雅停止:      在 tmux 中按 Ctrl+C                     │
│  强制停止:      kill $(pgrep -f run_e2e)                │
└──────────────────────────────────────────────────────────┘
```

---

**文档版本**: v1.0
**最后更新**: 2026-01-27
**维护者**: AI Trading Team
