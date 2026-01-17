TRADING_SYSTEM = """You are an experienced cryptocurrency futures trader. Based on technical analysis and risk assessment results, make specific trading decisions.

## Critical Requirements
**RESPONSE MUST BE IN ENGLISH. Use the exact enum values specified below.**

## Output Format
Output must be valid JSON matching the schema exactly. Do not add any extra explanations.

## Required Enum Values:
- action: "open_long", "open_short", "close_long", "close_short", "add_long", "add_short", "reduce_long", "reduce_short", or "hold"
- order_type: "market" or "limit"
- execution_urgency: "immediate", "wait_for_price", or "low_priority"

## Decision Principles
1. **Trade with Trend**: Only open positions when trend is clear
2. **Strict Stop Loss**: Every trade must have a stop loss
3. **Reasonable Take Profit**: Consider resistance levels and risk-reward ratio
4. **Avoid Overtrading**: Hold when no clear signal
5. **Consider Fees**: Small moves are not worth trading

## Opening Conditions (at least 2 required):
- Clear trend (confidence > 60%)
- Signal strength is buy/strong_buy or sell/strong_sell
- Risk assessment shows should_trade = true
- Price is near key support/resistance levels"""

TRADING_USER = """## Technical Analysis Summary
- Trend: {trend} (Confidence: {trend_confidence}%)
- Signal Strength: {signal_strength}
- Support Levels: {support_levels}
- Resistance Levels: {resistance_levels}
- Volume Trend: {volume_trend}
- Identified Pattern: {pattern}
- Key Observations: {key_observations}

## Risk Assessment Summary
- Risk Level: {risk_level} (Score: {risk_score}/100)
- Recommended Leverage: {recommended_leverage}x
- Recommended Position: {recommended_position_percent}%
- Should Trade: {should_trade}
- Fee Warning: {fee_warning}
- Risk Factors: {risk_factors}
- Mitigation Suggestions: {mitigation_suggestions}

## Current Market State
- Current Price: {current_price} USDT
- 24h Change: {change_24h}%

## Current Position
{position_info}

## Strategy Preferences
- Strategy Type: {strategy_type}
- Leverage Range: {leverage_min}x - {leverage_max}x
- Default Stop Loss: {stop_loss_percent}%
- Default Take Profit: {take_profit_percent}%

## Account Balance
- Available Balance: {available_balance} USDT

Please make a trading decision."""

TRADING_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": [
                "open_long",
                "open_short",
                "close_long",
                "close_short",
                "add_long",
                "add_short",
                "reduce_long",
                "reduce_short",
                "hold",
            ],
            "description": "交易操作类型",
        },
        "confidence": {"type": "number", "description": "决策置信度(0-100)"},
        "leverage": {"type": "integer", "description": "使用的杠杆倍数"},
        "position_size_percent": {
            "type": "number",
            "description": "仓位占可用余额的百分比",
        },
        "entry_price": {"type": "number", "description": "建议入场价格"},
        "stop_loss_price": {"type": "number", "description": "止损价格"},
        "take_profit_price": {"type": "number", "description": "止盈价格"},
        "order_type": {
            "type": "string",
            "enum": ["market", "limit"],
            "description": "订单类型",
        },
        "reasoning": {"type": "string", "description": "决策理由"},
        "execution_urgency": {
            "type": "string",
            "enum": ["immediate", "wait_for_price", "low_priority"],
            "description": "执行紧迫程度",
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
        "execution_urgency",
    ],
    "additionalProperties": False,
}
