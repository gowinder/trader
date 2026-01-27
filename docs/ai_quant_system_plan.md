# AI量化交易系统升级规划

## 项目概述

将现有的纯LLM驱动的AI交易系统升级为**混合量化交易系统**，集成：
1. CCXT统一交易所接口（支持多平台）
2. 模拟交易环境（Testnet）
3. 专业交易员流程（多时间框架、仓位管理、风控体系）
4. 传统量化策略（K线形态识别、市场状态分类、多策略并行）
5. 情绪分析（社交媒体/新闻情绪作为决策参考）

---

## 相关文档

### 知识文档
- [交易知识文档](./trading_knowledge.md) - K线形态、技术指标、风控体系等专业知识

### 架构与流程
- [系统架构](./ai_quant_plan_architecture.md) - 整体架构图、模块依赖关系
- [交易分析流程图](./ai_quant_plan_flow.md) - 完整交易周期、混合决策流程、时序图

### 实施阶段
- [Phase 1: CCXT集成](./ai_quant_plan_phase1_ccxt.md) - 交易所抽象层、CCXT适配器（7天）
- [Phase 2: 模拟交易环境](./ai_quant_plan_phase2_testnet.md) - Binance Testnet接入（8天）
- [Phase 3: 专业交易员流程](./ai_quant_plan_phase3_trading.md) - 多时间框架、仓位管理（11天）
- [Phase 4: 量化策略模型集成](./ai_quant_plan_phase4_quant.md) - K线形态、市场分类、混合决策（16天）
- [Phase 5: 情绪分析集成](./ai_quant_plan_phase5_sentiment.md) - 社交媒体情绪分析（5天）

### 配置与实施
- [配置文件变更](./ai_quant_plan_config.md) - 环境配置、时间线、风险控制、验证计划

---

## 实施时间线概览

| Phase | 任务 | 时间 | 依赖 |
|-------|------|------|------|
| Phase 1 | CCXT集成 | 7天 | - |
| Phase 2 | Testnet接入 | 8天 | Phase 1 |
| Phase 3 | 交易员流程 | 11天 | Phase 2 |
| Phase 4 | 量化策略 | 16天 | Phase 3 |
| Phase 5 | 情绪分析 | 5天 | Phase 4 |
| **总计** | | **47天** | |

---

## 关键文件清单

### Phase 1（必须）
- `src/ai_trader/exchange/base.py` - 交易所抽象基类
- `src/ai_trader/exchange/ccxt_adapter.py` - CCXT适配器
- `src/ai_trader/config.py` - 配置升级

### Phase 2（必须）
- `src/ai_trader/exchange/binance_adapter.py` - Binance支持

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

---

## 成功标准

1. **Phase 1**: 成功切换到CCXT，保持现有功能不变
2. **Phase 2**: 在Binance Testnet成功运行1周，无资金风险
3. **Phase 3**: 实现多时间框架分析和仓位管理，回测改善>10%
4. **Phase 4**: 混合决策模式在Testnet胜率>55%，准备上实盘
5. **Phase 5**: 情绪分析稳定运行，对极端市况有预警能力

---

## 快速开始

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

**Day 3-7: 根据调研结果实施**
- 如CCXT支持WEEX → 直接实施
- 如不支持 → 保留自定义WEEX + 用CCXT接入其他交易所

---

## 关键决策点

| 决策点 | 推荐方案 | 备选方案 | 选择理由 |
|--------|----------|----------|----------|
| CCXT集成 | 先调研再决定 | 直接使用CCXT | WEEX支持不确定 |
| Testnet | Binance优先 | Binance+Bybit | 降低复杂度 |
| 混合决策 | 可配置权重 | 固定权重 | 灵活性更高 |
| 实施节奏 | 严格按Phase | 大幅并行 | 保证稳定性 |
