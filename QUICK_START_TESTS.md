# 🚀 测试快速启动指南

## 📋 一、快速集成测试（5分钟）

### Phase 2: Binance Testnet 测试

```bash
# 激活虚拟环境
source .venv/bin/activate

# 运行测试
python scripts/test_binance_testnet.py
```

**预期结果**: 3/3 测试通过 ✅

---

## 🏃 二、长期端到端测试（1-2周）

### 方式1: 使用启动脚本（推荐）

```bash
# 使用 tmux 保持后台运行
tmux new -s trader-test

# 运行启动脚本
./scripts/start_long_term_test.sh

# 分离会话: Ctrl+B, 然后按 D
# 重新连接: tmux attach -t trader-test
```

### 方式2: 直接运行

```bash
# 使用 tmux
tmux new -s trader-test
source .venv/bin/activate
python scripts/run_e2e_testnet.py

# 分离: Ctrl+B, D
# 重新连接: tmux attach -t trader-test
```

### 方式3: 后台运行

```bash
# 使用 nohup
nohup python scripts/run_e2e_testnet.py > logs/e2e_nohup.log 2>&1 &

# 查看日志
tail -f logs/e2e_testnet.log
```

---

## 📊 三、监控测试运行

### 查看实时日志

```bash
# 主日志
tail -f logs/e2e_testnet.log

# 决策日志
tail -f logs/e2e_testnet_decisions.log
```

### 健康检查

```bash
# 检查最近1天的运行状态
python scripts/check_e2e_health.py --days 1

# 检查最近7天
python scripts/check_e2e_health.py --days 7
```

### 决策统计

```bash
# 总决策数
grep -c "Trading Decision" logs/e2e_testnet_decisions.log

# 各类决策分布
echo "HOLD: $(grep -c "action=HOLD" logs/e2e_testnet_decisions.log)"
echo "LONG: $(grep -c "action=LONG" logs/e2e_testnet_decisions.log)"
echo "SHORT: $(grep -c "action=SHORT" logs/e2e_testnet_decisions.log)"
```

### 进程监控

```bash
# 检查进程是否运行
ps aux | grep run_e2e_testnet

# 查看资源占用
top -p $(pgrep -f run_e2e_testnet)
```

---

## 🛑 四、停止测试

### 优雅停止（推荐）

```bash
# 方式1: 在 tmux 中按 Ctrl+C

# 方式2: 发送 SIGTERM
kill -SIGTERM $(pgrep -f run_e2e_testnet)
```

### 强制停止

```bash
kill -9 $(pgrep -f run_e2e_testnet)
```

---

## 📅 五、测试时间表

| 阶段 | 时长 | 目标 | 命令 |
|------|------|------|------|
| **Phase 2 验证** | 7天 | Testnet稳定性 | `./scripts/start_long_term_test.sh` |
| **Phase 3 验证** | 14天 | 仓位管理 | 同上（Week 1完成后） |
| **Phase 4 验证** | 7天 | 混合决策 | 同上（Week 2-3完成后） |

**建议**: 按顺序执行，确保每个阶段无问题后再进行下一阶段

---

## ⚠️ 六、注意事项

### 必须满足
- ✅ 配置为 Testnet 模式 (`TRADING_MODE=testnet`)
- ✅ 配置 Testnet API 凭证
- ✅ 网络连接稳定
- ✅ 使用 tmux/screen 保持后台运行

### 定期检查
- 📅 每天至少查看日志 1 次
- 📊 每周运行健康检查 1 次
- 💾 每周备份交易数据
- 🔍 监控磁盘空间（日志文件）

---

## 📚 七、完整文档

详细文档请查看:
- 📖 [TEST_GUIDE.md](TEST_GUIDE.md) - 完整测试指南
- 📋 [START_E2E.md](START_E2E.md) - 端到端测试说明

---

## 🆘 八、常见问题

### Q: 测试卡住不动
```bash
# 检查进程状态
ps aux | grep python
tail -50 logs/e2e_testnet.log

# 重启
kill $(pgrep -f run_e2e_testnet)
./scripts/start_long_term_test.sh
```

### Q: API 连接失败
```bash
# 测试网络
ping testnet.binancefuture.com

# 检查配置
cat .env | grep TESTNET

# 检查代理（如需要）
echo $https_proxy
```

### Q: 磁盘空间不足
```bash
# 检查空间
df -h

# 压缩旧日志
gzip logs/*.log.1

# 清理缓存（谨慎）
du -sh data/cache
```

---

## 🎯 九、快速参考

```bash
# 【启动测试】
tmux new -s test
./scripts/start_long_term_test.sh

# 【监控】
tail -f logs/e2e_testnet.log        # 实时日志
python scripts/check_e2e_health.py  # 健康检查

# 【停止】
Ctrl+C                              # 优雅停止

# 【重新连接】
tmux attach -t test
```

---

**更新时间**: 2026-01-27
**状态**: ✅ 测试脚本就绪
