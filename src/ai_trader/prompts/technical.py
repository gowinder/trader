TECHNICAL_SYSTEM = """You are a professional cryptocurrency technical analyst. Your task is to analyze K-line data and technical indicators, providing objective technical analysis results.

## Critical Requirements
**RESPONSE MUST BE IN ENGLISH. Use the exact enum values specified below.**

## Output Format
Output must be valid JSON matching the schema exactly. Do not add any extra explanations.

## Required Enum Values (MUST USE EXACTLY):
- trend: "strong_bullish", "bullish", "neutral", "bearish", or "strong_bearish"
- volume_trend: "increasing", "stable", or "decreasing"
- signal_strength: "strong_buy", "buy", "neutral", "sell", or "strong_sell"

## Analysis Guidelines
1. Identify current trend (strong_bullish/bullish/neutral/bearish/strong_bearish)
2. Find key support and resistance levels based on recent highs/lows and moving averages
3. Analyze volume trend (increasing/stable/decreasing)
4. Identify candlestick patterns
5. Evaluate comprehensive signal strength

## Analysis Principles
- Objective analysis based on data
- RSI overbought(>70)/oversold(<30) requires caution
- MACD golden/dead cross needs trend confirmation
- Bollinger Band contraction indicates potential breakout but direction is uncertain"""

TECHNICAL_USER = """## Trading Pair
{symbol}

## Current Price
{current_price} USDT

## K-line Data (Last {kline_count} {interval} candles)
| Time | Open | High | Low | Close | Volume |
|------|------|------|-----|-------|--------|
{kline_table}

## Technical Indicators
- MA7 (7-period): {ma7}
- MA25 (25-period): {ma25}
- MA99 (99-period): {ma99}
- RSI(14): {rsi}
- MACD: {macd}
- MACD Signal: {macd_signal}
- MACD Histogram: {macd_histogram}
- Bollinger Upper: {boll_upper}
- Bollinger Middle: {boll_middle}
- Bollinger Lower: {boll_lower}
- ATR(14): {atr}

## 24h Market Overview
- 24h High: {high_24h}
- 24h Low: {low_24h}
- 24h Change: {change_24h}%
- 24h Volume: {volume_24h}

Please analyze the data above and provide your technical analysis result in JSON format."""

TECHNICAL_SCHEMA = {
    "type": "object",
    "properties": {
        "trend": {
            "type": "string",
            "enum": [
                "strong_bullish",
                "bullish",
                "neutral",
                "bearish",
                "strong_bearish",
            ],
            "description": "当前趋势判断",
        },
        "trend_confidence": {
            "type": "number",
            "description": "趋势判断的置信度(0-100)",
        },
        "support_levels": {
            "type": "array",
            "items": {"type": "number"},
            "description": "支撑位列表",
        },
        "resistance_levels": {
            "type": "array",
            "items": {"type": "number"},
            "description": "阻力位列表",
        },
        "volume_trend": {
            "type": "string",
            "enum": ["increasing", "stable", "decreasing"],
            "description": "成交量趋势",
        },
        "pattern": {"type": "string", "description": "识别到的K线形态"},
        "signal_strength": {
            "type": "string",
            "enum": ["strong_buy", "buy", "neutral", "sell", "strong_sell"],
            "description": "综合交易信号强度",
        },
        "key_observations": {
            "type": "array",
            "items": {"type": "string"},
            "description": "关键观察点",
        },
    },
    "required": [
        "trend",
        "trend_confidence",
        "support_levels",
        "resistance_levels",
        "volume_trend",
        "pattern",
        "signal_strength",
        "key_observations",
    ],
    "additionalProperties": False,
}
