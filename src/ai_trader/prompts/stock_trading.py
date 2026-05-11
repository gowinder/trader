"""Stock trading prompts for tokenized stock spot trading (long-only)."""

STOCK_SYSTEM_PROMPT = """You are a professional US stock quantitative trader. Your task is to analyze technical indicators and price movements for tokenized stocks, and provide clear trading decisions.

## Critical Requirements
**RESPONSE MUST BE IN ENGLISH. Use exact enum values specified below.**

## Output Format
Output must be valid JSON matching the schema exactly. Do not add any extra explanations.

## Required Enum Values:
- action: "open_long", "close_long", "add_long", "reduce_long", or "hold"
- order_type: "market" or "limit"
- execution_urgency: "immediate", "wait_for_price", or "low_priority"

## Stock Trading Rules (Long-Only, Spot)
1. **No Leverage**: This is spot trading. Leverage is always 1x.
2. **No Short Selling**: You can only buy (open_long) or sell existing positions (close_long). Never short sell.
3. **Trend Analysis**: Focus on MA crossovers, MACD, RSI, and volume confirmation.
4. **Position Sizing**: Use fixed percentage risk (1-5% based on confidence).
5. **Strict Stop Loss**: Every trade MUST have a stop loss (5-10% based on volatility).
6. **Risk-Reward**: Minimum 1.5:1, prefer 2:1 or better.

## Opening Conditions (ALL required for new positions):
1. **Clear Trend**: Upward trend confirmed by at least 2 indicators
2. **Volume Confirmation**: Volume above 20-day average
3. **Risk Assessment**: risk_level not "very_high"
4. **Fundamental Alignment**: Sector/market sentiment supports the move

## Position Management
- **Pyramid Scaling**: Add to winning positions (profit > 3%, max 3 adds)
- **Trailing Stop**: Move stop to break-even at 2% profit, trail at 5%+
- **Partial Close**: Reduce by 50% at first profit target

## Trading Discipline
1. **Daily Loss Limit**: Stop trading if daily loss >= 3%
2. **Max Position**: No more than 20% of portfolio in single stock
3. **Emotional Check**: Never trade when emotional state is "greedy", "fearful", or "fomo"

## Output Constraints
- leverage: Must be 1 (spot trading, no leverage)
- reasoning: Keep it concise (1-2 sentences, in English)
- reasoning_zh: Chinese translation of reasoning (1-2 sentences)
- All numeric values: Use appropriate precision (2 decimals for prices)"""

STOCK_USER_PROMPT_TEMPLATE = """## Stock Technical Analysis
- Symbol: {symbol}
- Trend: {trend} (Confidence: {trend_confidence}%)
- Signal Strength: {signal_strength}
- Support Levels: {support_levels}
- Resistance Levels: {resistance_levels}
- Volume Trend: {volume_trend}
- Identified Pattern: {pattern}
- Key Observations: {key_observations}

## Risk Assessment
- Risk Level: {risk_level} (Score: {risk_score}/100)
- Recommended Position: {recommended_position_percent}%
- Should Trade: {should_trade}
- Risk Factors: {risk_factors}

## Current Market State
- Current Price: {current_price} USD
- 24h Change: {change_24h}%
- ATR: {atr} USD

## Current Position
{position_info}

## Account Balance
- Available Balance: {available_balance} USD

## Trading Discipline
- Daily PnL: {daily_pnl} USD
- Trades Today: {trades_today}

Please make a long-only spot trading decision."""

STOCK_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": [
                "open_long",
                "close_long",
                "add_long",
                "reduce_long",
                "hold",
            ],
            "description": "Trading action (long-only)",
        },
        "confidence": {"type": "number", "description": "Decision confidence (0-100)"},
        "leverage": {
            "type": "integer",
            "minimum": 1,
            "maximum": 1,
            "description": "Leverage (always 1 for spot)",
        },
        "position_size_percent": {
            "type": "number",
            "description": "Position size as % of available balance",
        },
        "entry_price": {"type": "number", "description": "Suggested entry price"},
        "stop_loss_price": {"type": "number", "description": "Stop loss price"},
        "take_profit_price": {"type": "number", "description": "Take profit price"},
        "order_type": {
            "type": "string",
            "enum": ["market", "limit"],
            "description": "Order type",
        },
        "reasoning": {
            "type": "string",
            "maxLength": 200,
            "description": "Decision reasoning (1-2 sentences, English)",
        },
        "reasoning_zh": {
            "type": "string",
            "maxLength": 200,
            "description": "Decision reasoning in Chinese",
        },
        "execution_urgency": {
            "type": "string",
            "enum": ["immediate", "wait_for_price", "low_priority"],
            "description": "Execution urgency",
        },
    },
    "required": [
        "action",
        "confidence",
        "leverage",
        "position_size_percent",
        "entry_price",
        "stop_loss_price",
        "take_profit_price",
        "order_type",
        "reasoning",
        "reasoning_zh",
        "execution_urgency",
    ],
    "additionalProperties": False,
}
