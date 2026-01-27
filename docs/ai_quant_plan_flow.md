# AI量化交易系统 - 交易分析流程图

> 本文档是 [AI量化交易系统升级规划](./ai_quant_system_plan.md) 的子文档

---

## 完整交易周期

```mermaid
flowchart TB
    START([开始交易周期]) --> FETCH_DATA

    subgraph 数据采集
        FETCH_DATA[获取市场数据]
        FETCH_DATA --> KLINES[获取多周期K线<br/>15m/1H/4H/1D]
        FETCH_DATA --> TICKER[获取实时价格]
        FETCH_DATA --> ACCOUNT[获取账户信息]
        FETCH_DATA --> POSITIONS[获取持仓信息]
    end

    KLINES & TICKER --> CALC_IND[计算技术指标<br/>MA/RSI/MACD/布林带/ATR]

    subgraph 量化分析
        CALC_IND --> PATTERN_DETECT[K线形态识别]
        CALC_IND --> MARKET_CLASS[市场状态分类]
        PATTERN_DETECT --> SELECT_STRAT[策略选择]
        MARKET_CLASS --> SELECT_STRAT
        SELECT_STRAT --> GEN_SIGNAL[生成量化信号]
    end

    subgraph AI分析
        CALC_IND --> TECH_ANALYSIS[LLM技术分析]
        TECH_ANALYSIS --> RISK_ASSESS[LLM风险评估]
        ACCOUNT & POSITIONS --> RISK_ASSESS
        RISK_ASSESS --> LLM_DECISION[LLM交易决策]
    end

    GEN_SIGNAL --> HYBRID[混合决策引擎]
    LLM_DECISION --> HYBRID

    HYBRID --> CONFLICT{信号冲突?}
    CONFLICT -->|是| RESOLVE[冲突解决]
    CONFLICT -->|否| ENHANCE[信号增强]
    RESOLVE --> FINAL_DEC[最终决策]
    ENHANCE --> FINAL_DEC

    FINAL_DEC --> SHOULD_TRADE{是否交易?}
    SHOULD_TRADE -->|否| LOG_HOLD[记录观望]
    SHOULD_TRADE -->|是| RISK_CHECK

    subgraph 风控检查
        RISK_CHECK[风控规则检查]
        RISK_CHECK --> MAX_LOSS{超过每日最大亏损?}
        MAX_LOSS -->|是| BLOCK[阻止交易]
        MAX_LOSS -->|否| POS_SIZE[计算仓位大小]
        POS_SIZE --> LEVERAGE[设置杠杆]
    end

    LEVERAGE --> EXECUTE

    subgraph 订单执行
        EXECUTE[创建订单]
        EXECUTE --> SET_SL[设置止损]
        SET_SL --> SET_TP[设置止盈]
        SET_TP --> SUBMIT[提交订单]
    end

    SUBMIT --> SUCCESS{执行成功?}
    SUCCESS -->|是| LOG_TRADE[记录交易]
    SUCCESS -->|否| RETRY{重试?}
    RETRY -->|是| EXECUTE
    RETRY -->|否| LOG_ERROR[记录错误]

    LOG_HOLD & LOG_TRADE & LOG_ERROR & BLOCK --> REPORT[生成报告]
    REPORT --> WAIT[等待下一周期]
    WAIT --> END([结束])

    style HYBRID fill:#f9f,stroke:#333
    style RISK_CHECK fill:#ff9,stroke:#333
    style EXECUTE fill:#9f9,stroke:#333
```

---

## 混合决策详细流程

```mermaid
flowchart LR
    subgraph 输入
        QUANT_SIG[量化信号<br/>action + confidence]
        LLM_SIG[LLM信号<br/>action + confidence + reasoning]
        MARKET_STATE[市场状态<br/>趋势/震荡/突破]
        PATTERNS[识别的形态]
    end

    QUANT_SIG & LLM_SIG --> COMPARE{信号一致?}

    COMPARE -->|是| BOOST[提高置信度 +20%]
    COMPARE -->|否| STATE_CHECK{检查市场状态}

    STATE_CHECK -->|强趋势| QUANT_PRIO[量化优先]
    STATE_CHECK -->|震荡/复杂| LLM_PRIO[LLM优先]
    STATE_CHECK -->|突破| PATTERN_CHECK{形态确认?}

    PATTERN_CHECK -->|是| QUANT_PRIO
    PATTERN_CHECK -->|否| HOLD[观望]

    BOOST --> WEIGHT[应用权重<br/>QUANT:LLM:SENTIMENT]
    QUANT_PRIO --> WEIGHT
    LLM_PRIO --> WEIGHT

    WEIGHT --> SENTIMENT{情绪分析<br/>开启?}
    SENTIMENT -->|是| SENTIMENT_ADJ[情绪调节<br/>一致性/背离/风险]
    SENTIMENT -->|否| FINAL[最终决策]
    SENTIMENT_ADJ --> FINAL
    HOLD --> FINAL

    subgraph 输出
        FINAL --> ACTION[action: open_long/short/hold/...]
        FINAL --> CONF[confidence: 0-1]
        FINAL --> REASON[reasoning: 决策理由]
        FINAL --> SOURCE[source: quant/llm/hybrid]
    end
```

---

## 时序图

### 主交易循环时序

```mermaid
sequenceDiagram
    autonumber
    participant SCH as Scheduler
    participant EX as Exchange
    participant MD as MarketData
    participant IND as Indicators
    participant QS as QuantStrategy
    participant LLM as LLMAnalyzer
    participant HD as HybridDecision
    participant PM as PositionManager
    participant OM as OrderManager
    participant TJ as TradeJournal

    loop 每个交易周期
        SCH->>EX: get_klines(symbol, intervals)
        EX-->>SCH: klines_data
        SCH->>EX: get_ticker(symbol)
        EX-->>SCH: ticker_data
        SCH->>EX: get_account()
        EX-->>SCH: account_info
        SCH->>EX: get_positions(symbol)
        EX-->>SCH: positions

        SCH->>MD: aggregate_data(klines, ticker)
        MD->>IND: calculate_indicators(klines)
        IND-->>MD: indicators
        MD-->>SCH: market_data

        par 量化分析
            SCH->>QS: analyze(market_data)
            QS->>QS: detect_patterns()
            QS->>QS: classify_market()
            QS->>QS: select_strategy()
            QS-->>SCH: quant_signal
        and LLM分析
            SCH->>LLM: analyze_technical(market_data)
            LLM-->>SCH: tech_result
            SCH->>LLM: assess_risk(tech_result, account)
            LLM-->>SCH: risk_result
            SCH->>LLM: make_decision(tech, risk, positions)
            LLM-->>SCH: llm_signal
        end

        SCH->>HD: hybrid_decide(quant_signal, llm_signal)
        HD->>HD: resolve_conflicts()
        HD->>HD: apply_weights()
        HD-->>SCH: final_decision

        alt 需要交易
            SCH->>PM: calculate_position(decision, account)
            PM->>PM: apply_risk_rules()
            PM-->>SCH: position_size, leverage

            SCH->>OM: execute_order(decision, size)
            OM->>EX: set_leverage(symbol, leverage)
            EX-->>OM: ok
            OM->>EX: create_order(...)
            EX-->>OM: order_result
            OM-->>SCH: execution_result

            SCH->>TJ: log_trade(decision, result)
        else 观望
            SCH->>TJ: log_hold(decision)
        end

        SCH->>SCH: wait(interval)
    end
```

### 交易所切换时序

```mermaid
sequenceDiagram
    autonumber
    participant APP as Application
    participant CFG as Config
    participant FAC as ExchangeFactory
    participant CCXT as CCXTAdapter
    participant BIN as BinanceAdapter
    participant WEEX as WeexClient

    APP->>CFG: load_config()
    CFG-->>APP: config

    APP->>FAC: create_exchange_client()

    alt config.trading_mode == "testnet"
        FAC->>FAC: check testnet_exchange
        alt testnet_exchange == "binance"
            FAC->>BIN: new BinanceAdapter(testnet=True)
            BIN->>CCXT: init ccxt.binance(testnet_urls)
            CCXT-->>BIN: ccxt_client
            BIN-->>FAC: binance_adapter
        end
    else config.trading_mode == "live"
        alt exchange_type == "weex"
            alt use_ccxt == true
                FAC->>CCXT: new CCXTAdapter("weex")
                CCXT-->>FAC: ccxt_adapter
            else use_ccxt == false
                FAC->>WEEX: new WeexClient()
                WEEX-->>FAC: weex_client
            end
        else exchange_type == "binance"
            FAC->>BIN: new BinanceAdapter(testnet=False)
            BIN-->>FAC: binance_adapter
        end
    end

    FAC-->>APP: exchange_client
    APP->>APP: start_trading(exchange_client)
```

### 混合决策时序

```mermaid
sequenceDiagram
    autonumber
    participant DE as DecisionEngine
    participant PR as PatternRecognizer
    participant MC as MarketClassifier
    participant SS as StrategySelector
    participant LLM as LLMProvider
    participant HY as HybridDecision

    DE->>PR: detect_all(klines)
    PR-->>DE: patterns[]

    DE->>MC: classify(market_data)
    MC-->>DE: market_state

    DE->>SS: select_strategy(market_state)
    SS-->>DE: selected_strategies[]

    loop 每个选中策略
        DE->>SS: strategy.generate_signal(market_data)
        SS-->>DE: signal
    end
    DE->>SS: rank_strategies(signals)
    SS-->>DE: quant_decision

    DE->>LLM: analyze_technical(market_data)
    LLM-->>DE: tech_analysis

    DE->>LLM: assess_risk(tech_analysis, account)
    LLM-->>DE: risk_assessment

    DE->>LLM: make_decision(tech, risk, positions)
    LLM-->>DE: llm_decision

    DE->>HY: hybrid_decision(quant, llm, patterns, state)

    alt quant.action == llm.action
        HY->>HY: boost_confidence(+0.2)
        HY-->>DE: decision(action, high_confidence, "双重确认")
    else market_state == STRONG_TREND
        HY->>HY: prefer_quant()
        HY-->>DE: decision(quant.action, quant.confidence, "趋势明确-量化优先")
    else market_state == RANGE_BOUND
        HY->>HY: prefer_llm()
        HY-->>DE: decision(llm.action, llm.confidence, "震荡市-LLM判断")
    else 信号冲突
        HY->>HY: conservative_hold()
        HY-->>DE: decision("hold", 0, "信号冲突-观望")
    end
```

---

## 相关文档

- [主文档](./ai_quant_system_plan.md)
- [系统架构](./ai_quant_plan_architecture.md)
- [Phase 4: 量化策略模型集成](./ai_quant_plan_phase4_quant.md)
