"""市场分析器"""

from ..models.market import MarketData, Kline
from ..models.decision import TechnicalAnalysisResult
from ..prompts.technical import TECHNICAL_USER, TECHNICAL_SYSTEM, TECHNICAL_SCHEMA
from .client import LLMClient
from typing import List


class MarketAnalyzer:
    """负责调用 LLM 进行技术分析"""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def _format_klines(self, klines: List[Kline]) -> str:
        """格式化K线数据为Markdown表格"""
        lines = []
        import datetime

        for k in klines:
            dt = datetime.datetime.fromtimestamp(k.timestamp / 1000).strftime(
                "%Y-%m-%d %H:%M"
            )
            lines.append(
                f"| {dt} | {k.open:.2f} | {k.high:.2f} | {k.low:.2f} | {k.close:.2f} | {k.volume:.2f} |"
            )
        return "\n".join(lines)

    async def analyze_technical(
        self, market_data: MarketData
    ) -> TechnicalAnalysisResult:
        """执行技术分析"""
        user_prompt = TECHNICAL_USER.format(
            symbol=market_data.symbol,
            current_price=market_data.current_price,
            kline_count=len(market_data.klines),
            interval=market_data.interval,
            kline_table=self._format_klines(market_data.klines[-20:]),  # Last 20 klines
            ma7=f"{market_data.indicators.ma7:.2f}",
            ma25=f"{market_data.indicators.ma25:.2f}",
            ma99=f"{market_data.indicators.ma99:.2f}",
            rsi=f"{market_data.indicators.rsi:.2f}",
            macd=f"{market_data.indicators.macd:.4f}",
            macd_signal=f"{market_data.indicators.macd_signal:.4f}",
            macd_histogram=f"{market_data.indicators.macd_histogram:.4f}",
            boll_upper=f"{market_data.indicators.boll_upper:.2f}",
            boll_middle=f"{market_data.indicators.boll_middle:.2f}",
            boll_lower=f"{market_data.indicators.boll_lower:.2f}",
            atr=f"{market_data.indicators.atr:.2f}",
            high_24h=market_data.high_24h,
            low_24h=market_data.low_24h,
            change_24h=market_data.change_24h,
            volume_24h=market_data.volume_24h,
        )

        response = await self.llm.chat(
            messages=[
                {"role": "system", "content": TECHNICAL_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            schema=TECHNICAL_SCHEMA,
            max_tokens=1500,
            temperature=0.3,
            usage_type="analysis",
        )

        # Strip debug fields injected by provider
        response.pop("_raw_content", None)
        response.pop("usage", None)

        # LLM 有时返回嵌套结构如 {"analysis": {...}}，需要展开
        if "trend" not in response and len(response) == 1:
            inner = next(iter(response.values()))
            if isinstance(inner, dict) and "trend" in inner:
                response = inner

        return TechnicalAnalysisResult(**response)
