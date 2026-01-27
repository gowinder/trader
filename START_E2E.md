# 🚀 启动端到端测试系统

## 快速启动（推荐）

在新的终端窗口中运行：

```bash
cd /Users/gowinder/code/gowinder/trader
tmux new -s trading
python -u scripts/run_e2e_testnet.py
```

**分离会话（保持后台运行）**: 按 `Ctrl+B` 然后按 `D`

**重新连接查看**: `tmux attach -t trading`

---

## 系统将会做什么

✅ 每 5 分钟执行一次完整分析循环：
1. 获取 4 个时间框架数据（15m, 1h, 4h, 1d）
2. 计算技术指标（MA, RSI, ATR）
3. 计算 Confluence Score
4. 做出交易决策（遵循 Phase 3 规则）
5. 记录详细日志

✅ 交易规则：
- Confluence < 50% → HOLD
- Confluence ≥ 50% + 明确趋势 → 考虑交易
- 每日最多 3 笔交易
- 每日亏损限制 3%

✅ 日志位置：
- 主日志: `logs/e2e_testnet.log`
- 决策日志: `logs/e2e_testnet_decisions.log`

---

## 监控命令（另一个终端窗口）

```bash
# 查看实时日志
tail -f logs/e2e_testnet.log

# 查看决策统计
grep -c "Trading Decision" logs/e2e_testnet_decisions.log

# 查看最新决策
tail -20 logs/e2e_testnet_decisions.log
```

---

**系统将持续运行直到您按 Ctrl+C 停止**

建议运行时间：2 周（收集足够的决策数据用于分析）
