# AI量化交易系统 - 配置文件变更

> 本文档是 [AI量化交易系统升级规划](./ai_quant_system_plan.md) 的子文档

---

## 最终 `.env` 配置

```bash
# ============= 运行模式 =============
TRADING_MODE=testnet  # testnet / live
EXCHANGE_TYPE=binance  # weex / binance / bybit
USE_CCXT=true

# ============= Testnet配置 =============
TESTNET_EXCHANGE=binance
TESTNET_API_KEY=your_testnet_key
TESTNET_API_SECRET=your_testnet_secret

# ============= WEEX配置（实盘） =============
WEEX_API_KEY=...
WEEX_API_SECRET=...
WEEX_PASSPHRASE=...

# ============= 决策模式 =============
DECISION_MODE=hybrid  # quant_only / llm_only / hybrid
# 默认权重: 量化50% + LLM35% + 情绪15% = 100%
# 情绪关闭时自动归一化: 量化50/(50+35)=58.8%, LLM35/(50+35)=41.2%
QUANT_WEIGHT=0.50
LLM_WEIGHT=0.35
SENTIMENT_WEIGHT=0.15

# ============= 策略选择 =============
ENABLED_STRATEGIES=trend_following,mean_reversion,breakout

# ============= 情绪分析 =============
# 情绪分析默认关闭，开启需配置API Key
SENTIMENT_ENABLED=false
SENTIMENT_CACHE_TTL=15
RAPIDAPI_TWITTER_KEY=your_rapidapi_key
CRYPTOPANIC_API_KEY=your_cryptopanic_key
```

---

## 实施时间线

| Phase | 任务 | 时间 | 依赖 |
|-------|------|------|------|
| Phase 1 | CCXT集成 | 7天 | - |
| Phase 2 | Testnet接入 | 8天 | Phase 1 |
| Phase 3 | 交易员流程 | 11天 | Phase 2 |
| Phase 4 | 量化策略 | 16天 | Phase 3 |
| Phase 5 | 情绪分析 | 5天 | Phase 4 |
| **总计** | | **47天** | |

**并行优化**: Phase 2的调研任务可与Phase 3的调研任务并行，可节省3-5天。Phase 5可与Phase 4后期并行，可节省2天。

---

## 关键文件清单

### Phase 1（必须）
- `src/ai_trader/exchange/base.py` - 交易所抽象基类
- `src/ai_trader/exchange/ccxt_adapter.py` - CCXT适配器
- `src/ai_trader/config.py` - 配置升级

### Phase 2（必须）
- `src/ai_trader/exchange/binance_adapter.py` - Binance支持
- `docs/testnet_research.md` - Testnet调研文档

### Phase 3（重要）
- `src/ai_trader/data/multi_timeframe.py` - 多周期分析
- `src/ai_trader/risk/position_manager.py` - 仓位管理
- `src/ai_trader/analytics/trade_journal.py` - 交易日志

### Phase 4（核心）
- `src/ai_trader/strategies/pattern_recognition.py` - K线形态识别
- `src/ai_trader/strategies/market_classifier.py` - 市场状态分类
- `src/ai_trader/strategies/strategy_selector.py` - 策略选择器
- `src/ai_trader/ai/decision.py` - 混合决策引擎（重构）
- `src/ai_trader/backtest/engine.py` - 回测框架

### Phase 5（增强）
- `src/ai_trader/sentiment/data_sources.py` - 社交媒体数据源
- `src/ai_trader/sentiment/analyzer.py` - 情绪分析器
- `src/ai_trader/sentiment/cache.py` - 情绪缓存

---

## 风险总览

### 技术风险
1. **CCXT对WEEX支持不足** → 保留原生实现fallback
2. **Testnet数据质量差** → 优先选Binance等大厂
3. **LLM成本增加** → 混合决策后可降低LLM调用频率
4. **情绪API不稳定** → 优雅降级，缓存机制

### 业务风险
1. **策略实盘失效** → 小仓位试错，严格止损
2. **过度交易** → 加入冷却时间（如15分钟内不重复交易）
3. **黑天鹅事件** → 紧急停机机制

### 实施风险
1. **时间超期** → 预留20%缓冲时间
2. **技术债务** → 每个Phase后代码重构
3. **文档缺失** → 每个模块强制docstring

---

## 验证计划

### Phase 1验证
- [ ] 所有现有单元测试通过
- [ ] CCXT模式与原生WEEX行为一致（K线、订单）
- [ ] 延迟增加<100ms

### Phase 2验证
- [ ] Binance Testnet完整交易流程成功
- [ ] Testnet K线数据与live一致
- [ ] 账户资金隔离确认

### Phase 3验证
- [ ] 多时间框架数据获取正常
- [ ] 仓位管理逻辑回测验证
- [ ] 交易日志完整记录

### Phase 4验证
- [ ] K线形态识别准确率>70%（人工标注数据集）
- [ ] 市场状态分类准确率>75%
- [ ] 混合决策模式Testnet运行7天无异常
- [ ] 回测胜率>55%，盈亏比>1:1.5

### Phase 5验证
- [ ] Twitter/CryptoPanic API正常工作
- [ ] 情绪缓存机制正常
- [ ] 情绪信号与市场走势相关性验证
- [ ] 有/无情绪分析对比测试

---

## 成功标准

1. **Phase 1**: 成功切换到CCXT，保持现有功能不变
2. **Phase 2**: 在Binance Testnet成功运行1周，无资金风险
3. **Phase 3**: 实现多时间框架分析和仓位管理，回测改善>10%
4. **Phase 4**: 混合决策模式在Testnet胜率>55%，准备上实盘
5. **Phase 5**: 情绪分析稳定运行，对极端市况有预警能力

---

## 推荐实施路径（基于最佳实践）

### 1. CCXT集成策略
**推荐方案**: **先调研CCXT对WEEX支持再决定**

理由：
- WEEX是较小众的交易所，CCXT可能不在官方支持列表
- 调研1-2天可避免后续返工
- 如CCXT不支持，可考虑：
  - 为CCXT贡献WEEX插件
  - 保留自定义实现 + 用CCXT接入其他交易所（如Binance）

### 2. Testnet优先级
**推荐方案**: **优先Binance Testnet，后续再考虑Bybit**

理由：
- Binance文档最完善，社区支持最好
- 单一Testnet足够验证系统功能
- 降低Phase 2工作量（8天 → 6天）

### 3. 混合决策模式
**推荐方案**: **可配置权重（默认量化为主）**

理由：
- 初期量化权重0.7，LLM权重0.3（情绪关闭时）
- 根据Testnet表现动态调整
- 极端情况：可完全切换到纯量化或纯LLM模式

配置示例（情绪关闭）：
```bash
DECISION_MODE=hybrid
QUANT_WEIGHT=0.7
LLM_WEIGHT=0.3
SENTIMENT_ENABLED=false  # 情绪关闭，权重自动归一化为 70%/30%

# 冲突解决规则
CONFLICT_RESOLUTION=quant_priority_on_trend  # 趋势明确时量化优先
```

配置示例（情绪开启）：
```bash
DECISION_MODE=hybrid
QUANT_WEIGHT=0.55
LLM_WEIGHT=0.30
SENTIMENT_WEIGHT=0.15
SENTIMENT_ENABLED=true  # 总和=1.0，无需归一化
```

### 4. 实施节奏
**推荐方案**: **严格按Phase顺序（小幅并行优化）**

时间表：
- Phase 1: 7天（Day 1-7）
  - Day 1-2: CCXT对WEEX支持调研
  - Day 3-7: 实施集成
- Phase 2: 6天（Day 8-13）
  - Day 8-9: Binance Testnet调研与接入
  - Day 10-13: 测试验证
- Phase 3: 11天（Day 14-24）
  - Day 14-16: 交易员流程调研（可与Phase 2并行）
  - Day 17-24: 实施
- Phase 4: 16天（Day 25-40）

**总计**: 40天（优化2天）

---

## 第一步：立即行动清单

如果您确认规划，可以立即开始：

### Week 1 (Day 1-7): CCXT调研与集成

**Day 1-2: 调研任务**
```bash
# 1. 检查CCXT是否支持WEEX
pip install ccxt
python -c "import ccxt; print('weex' in ccxt.exchanges)"

# 2. 如果不支持，查看CCXT支持的交易所列表
python -c "import ccxt; print([e for e in ccxt.exchanges if 'binance' in e or 'okx' in e or 'bybit' in e])"

# 3. 测试Binance接口
python <<EOF
import ccxt
exchange = ccxt.binance()
ticker = exchange.fetch_ticker('BTC/USDT')
print(ticker)
EOF
```

**输出决策文档**: `docs/ccxt_weex_research.md`

**Day 3-7: 根据调研结果实施**
- 如CCXT支持WEEX → 直接实施方案A
- 如不支持 → 实施方案B（自定义WEEX + CCXT其他交易所）

---

## 关键决策点记录

| 决策点 | 推荐方案 | 备选方案 | 选择理由 |
|--------|----------|----------|----------|
| CCXT集成 | 先调研再决定 | 直接使用CCXT | WEEX支持不确定 |
| Testnet | Binance优先 | Binance+Bybit | 降低复杂度 |
| 混合决策 | 可配置权重 | 固定权重 | 灵活性更高 |
| 实施节奏 | 严格按Phase | 大幅并行 | 保证稳定性 |

---

## 相关文档

- [主文档](./ai_quant_system_plan.md)
- [Phase 1: CCXT集成](./ai_quant_plan_phase1_ccxt.md)
- [Phase 5: 情绪分析集成](./ai_quant_plan_phase5_sentiment.md)
