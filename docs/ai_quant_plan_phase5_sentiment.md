# AI量化交易系统 - Phase 5: 情绪分析集成

> 本文档是 [AI量化交易系统升级规划](./ai_quant_system_plan.md) 的子文档

**预计时间**: 5天

---

## 目标

引入实时社交媒体/新闻情绪分析，作为决策参考因素。

---

## 关键任务

### 5.1 数据源接入

**文件**: `src/ai_trader/sentiment/data_sources.py`

数据源选择：
1. **RapidAPI Twitter Search** - 社交媒体情绪
2. **CryptoPanic** - 加密货币新闻聚合
3. **Fear & Greed Index** - 市场恐惧贪婪指数（备选）

```python
class SocialDataSource(ABC):
    @abstractmethod
    async def fetch_posts(self, symbol: str, limit: int) -> List[SocialPost]:
        pass

class TwitterSource(SocialDataSource):
    def __init__(self, rapidapi_key: str):
        self.api_key = rapidapi_key
        self.base_url = "https://twitter-api45.p.rapidapi.com/search.php"

    async def fetch_posts(self, symbol: str, limit: int = 50) -> List[SocialPost]:
        # 搜索关键词: $BTC, #Bitcoin, Bitcoin等
        ...

class CryptoPanicSource(SocialDataSource):
    async def fetch_posts(self, symbol: str, limit: int = 20) -> List[SocialPost]:
        # 获取最新加密货币新闻
        ...
```

---

### 5.2 情绪分析器

**文件**: `src/ai_trader/sentiment/analyzer.py`

```python
class SentimentAnalyzer:
    def __init__(self, llm_client: AIClient):
        self.llm = llm_client
        self.sources: List[SocialDataSource] = []

    async def analyze_sentiment(self, symbol: str) -> SentimentResult:
        # 1. 从多个数据源获取帖子/新闻
        posts = await self._fetch_all_sources(symbol)

        # 2. 调用LLM分析情绪
        prompt = self._build_sentiment_prompt(posts)
        response = await self.llm.analyze(prompt)

        # 3. 返回结构化结果
        return SentimentResult(
            overall_sentiment=response.sentiment,  # bullish/bearish/neutral
            confidence=response.confidence,        # 0-1
            key_topics=response.topics,            # 热点话题
            risk_events=response.risks,            # 风险事件
            sample_posts=posts[:5]                 # 样本
        )
```

情绪分析Prompt模板：
```python
SENTIMENT_PROMPT = """
分析以下关于{symbol}的社交媒体帖子和新闻：

{posts_content}

请分析：
1. 整体市场情绪（看涨/看跌/中性）
2. 情绪强度（0-100）
3. 主要讨论话题
4. 是否有重大风险事件（黑天鹅、监管、黑客等）
5. 情绪是否与价格走势背离（可能的反转信号）

以JSON格式返回结果。
"""
```

---

### 5.3 集成到混合决策引擎

**文件**: `src/ai_trader/ai/decision.py`（增强）

```python
class HybridDecisionEngine:
    async def analyze_and_decide(self, market_data, account, positions):
        # 1. 量化分析
        quant_signal = await self._quant_analyze(market_data)

        # 2. LLM分析
        llm_signal = await self._llm_analyze(market_data, account, positions)

        # 3. 情绪分析（新增）
        sentiment = await self._sentiment_analyze(market_data.symbol)

        # 4. 混合决策（加入情绪权重）
        final_decision = self._hybrid_decision(
            quant_signal,
            llm_signal,
            sentiment  # 情绪作为调节因素
        )
        return final_decision

    def _hybrid_decision(self, quant, llm, sentiment):
        # 情绪调节规则：
        # 1. 极端恐慌(sentiment<20) + 量化看多 → 可能是底部，增加做多信心
        # 2. 极端贪婪(sentiment>80) + 量化看空 → 可能是顶部，增加做空信心
        # 3. 有重大风险事件 → 降低仓位或暂停交易
        # 4. 情绪与技术面背离 → 发出预警
        ...
```

---

### 5.4 情绪缓存与限流

**文件**: `src/ai_trader/sentiment/cache.py`

```python
class SentimentCache:
    def __init__(self, ttl_minutes: int = 15):
        self.cache: Dict[str, SentimentResult] = {}
        self.ttl = ttl_minutes

    async def get_or_fetch(self, symbol: str, analyzer: SentimentAnalyzer) -> SentimentResult:
        if self._is_valid(symbol):
            return self.cache[symbol]
        result = await analyzer.analyze_sentiment(symbol)
        self.cache[symbol] = result
        return result
```

**限流策略**：
- Twitter API: 每15分钟50次请求
- CryptoPanic: 每分钟10次请求
- 情绪分析缓存15分钟（可配置）

---

### 5.5 配置与测试

**文件**: `src/ai_trader/config.py`

```python
# 情绪分析配置
sentiment_enabled: bool = False  # 默认关闭，开启需配置API Key
sentiment_weight: float = 0.15  # 在最终决策中的权重（开启时生效）
sentiment_cache_ttl: int = 15   # 缓存有效期（分钟）
rapidapi_twitter_key: str = ""
cryptopanic_api_key: str = ""
```

---

## 情绪信号权重分配

| 决策因素 | 默认权重 | 说明 |
|----------|----------|------|
| 量化信号 | 50% | K线形态、技术指标 |
| LLM分析 | 35% | 技术分析+风险评估 |
| 情绪分析 | 15% | 社交媒体/新闻情绪 |

**情绪调节规则**：
- 情绪与技术面一致 → 权重正常
- 情绪与技术面背离 → 降低置信度，发出预警
- 检测到重大风险事件 → 强制观望或减仓

---

## 依赖变更

```toml
[dependencies]
aiohttp = ">=3.9.0"  # 异步HTTP请求（如果尚未添加）
```

---

## 验证方法

1. 单元测试情绪分析逻辑
2. 验证API限流正常工作
3. Testnet对比测试（有/无情绪分析）
4. 回测验证情绪信号有效性

---

## 风险控制

- API不可用 → 优雅降级，不影响核心交易
- 情绪噪声大 → 只在置信度高时使用
- 成本控制 → 限制API调用频率

---

## 相关文档

- [主文档](./ai_quant_system_plan.md)
- [Phase 4: 量化策略模型集成](./ai_quant_plan_phase4_quant.md)
- [配置文件变更](./ai_quant_plan_config.md)
