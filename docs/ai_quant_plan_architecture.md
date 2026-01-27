# AI量化交易系统 - 系统架构

> 本文档是 [AI量化交易系统升级规划](./ai_quant_system_plan.md) 的子文档

---

## 整体架构

```mermaid
graph TB
    subgraph 外部系统
        EX1[Binance]
        EX2[Bybit]
        EX3[WEEX]
        EX4[其他交易所...]
    end

    subgraph 交易所抽象层
        CCXT[CCXT适配器]
        BASE[BaseExchange接口]
        FACTORY[交易所工厂]
    end

    subgraph 数据层
        MD[MarketDataManager<br/>市场数据管理器]
        MTF[MultiTimeframe<br/>多周期数据]
        IND[Indicators<br/>技术指标计算]
        CACHE[数据缓存]
    end

    subgraph 策略层
        PR[PatternRecognizer<br/>K线形态识别]
        MC[MarketClassifier<br/>市场状态分类]
        SS[StrategySelector<br/>策略选择器]
        subgraph 策略库
            S1[趋势跟随策略]
            S2[均值回归策略]
            S3[突破策略]
            S4[自定义策略...]
        end
    end

    subgraph AI决策层
        LLM[LLM分析器<br/>技术分析/风险评估/决策]
        QUANT[量化决策器]
        HYBRID[混合决策引擎<br/>信号融合/冲突解决]
    end

    subgraph 风控层
        PM[PositionManager<br/>仓位管理]
        RE[RuleEngine<br/>规则引擎]
        SL[止损管理]
    end

    subgraph 执行层
        OM[OrderManager<br/>订单管理器]
        EXEC[订单执行器]
    end

    subgraph 监控层
        TJ[TradeJournal<br/>交易日志]
        RPT[Reporter<br/>报告生成]
        BT[BacktestEngine<br/>回测引擎]
    end

    subgraph 调度层
        SCH[Scheduler<br/>任务调度器]
        CFG[Config<br/>配置管理]
    end

    EX1 & EX2 & EX3 & EX4 --> CCXT
    CCXT --> BASE
    BASE --> FACTORY
    FACTORY --> MD

    MD --> MTF
    MTF --> IND
    IND --> CACHE

    CACHE --> PR
    CACHE --> MC
    PR --> SS
    MC --> SS
    SS --> S1 & S2 & S3 & S4
    S1 & S2 & S3 & S4 --> QUANT

    CACHE --> LLM
    LLM --> HYBRID
    QUANT --> HYBRID

    HYBRID --> PM
    PM --> RE
    RE --> SL

    SL --> OM
    OM --> EXEC
    EXEC --> BASE

    EXEC --> TJ
    TJ --> RPT
    CACHE --> BT

    SCH --> MD
    SCH --> HYBRID
    SCH --> OM
    CFG --> SCH
```

---

## 模块依赖关系

```mermaid
graph LR
    subgraph Core
        CONFIG[config.py]
        MODELS[models/]
    end

    subgraph Exchange
        BASE_EX[exchange/base.py]
        CCXT_AD[exchange/ccxt_adapter.py]
        BINANCE[exchange/binance_adapter.py]
        ORDER[exchange/order.py]
        POS[exchange/position.py]
    end

    subgraph Data
        MARKET[data/market_data.py]
        MULTI_TF[data/multi_timeframe.py]
        INDICATORS[data/indicators.py]
    end

    subgraph Strategies
        PATTERN[strategies/pattern_recognition.py]
        CLASSIFIER[strategies/market_classifier.py]
        SELECTOR[strategies/strategy_selector.py]
        STRAT_BASE[strategies/strategy_base.py]
    end

    subgraph AI
        PROVIDERS[ai/providers/]
        CLIENT[ai/client.py]
        ANALYZER[ai/analyzer.py]
        DECISION[ai/decision.py]
    end

    subgraph Risk
        POS_MGR[risk/position_manager.py]
        RULES[rules/rule_engine.py]
    end

    subgraph Analytics
        JOURNAL[analytics/trade_journal.py]
        BACKTEST[backtest/engine.py]
    end

    CONFIG --> BASE_EX
    CONFIG --> PROVIDERS
    MODELS --> BASE_EX
    MODELS --> MARKET

    BASE_EX --> CCXT_AD
    BASE_EX --> BINANCE
    CCXT_AD --> ORDER
    CCXT_AD --> POS

    MARKET --> MULTI_TF
    MARKET --> INDICATORS
    INDICATORS --> PATTERN
    INDICATORS --> CLASSIFIER

    STRAT_BASE --> SELECTOR
    PATTERN --> SELECTOR
    CLASSIFIER --> SELECTOR

    PROVIDERS --> CLIENT
    CLIENT --> ANALYZER
    ANALYZER --> DECISION
    SELECTOR --> DECISION

    DECISION --> POS_MGR
    POS_MGR --> RULES

    DECISION --> JOURNAL
    MARKET --> BACKTEST
```

---

## 相关文档

- [主文档](./ai_quant_system_plan.md)
- [交易分析流程图](./ai_quant_plan_flow.md)
- [Phase 1: CCXT集成](./ai_quant_plan_phase1_ccxt.md)
