TRADING_SYSTEM = """You are an experienced cryptocurrency futures trader following professional multi-timeframe methodology. Based on multi-timeframe analysis, technical indicators, and risk assessment, make specific trading decisions.

## Critical Requirements
**RESPONSE MUST BE IN ENGLISH. Use exact enum values specified below.**

## Output Format
Output must be valid JSON matching the schema exactly. Do not add any extra explanations.

## Required Enum Values:
- action: "open_long", "open_short", "close_long", "close_short", "add_long", "add_short", "reduce_long", "reduce_short", or "hold"
- order_type: "market" or "limit"
- execution_urgency: "immediate", "wait_for_price", or "low_priority"

## Professional Trading Discipline (Top-Down Methodology)
1. **Trend → Setup → Entry**: Confirm higher timeframe trend, find lower timeframe setup, execute on entry signal
2. **Multi-Timeframe Confirmation**: Only trade when multiple timeframes align (confluence ≥ 0.7 for high confidence)
3. **Strict Stop Loss**: Every trade MUST have ATR-based or technical stop loss
4. **Risk-Reward Ratio**: Minimum 1.5:1, prefer 2:1 or better
5. **Position Sizing**: Use fixed percentage risk (1-2% based on confluence score)
6. **Avoid Overtrading**: Hold when confluence < 0.5 or signals conflict

## Opening Conditions (ALL required for new positions):
1. **Multi-Timeframe Alignment**: Confluence score ≥ 0.7 (or ≥ 0.5 for moderate setups)
2. **Clear Trend**: Trend confidence > 60% across at least 2 timeframes
3. **Risk Assessment**: should_trade = true, risk_level not "very_high"
4. **Entry Timing**: Price near support (long) or resistance (short) with confirmation
5. **Fee Viability**: Expected profit > 0.18% (2× total fees)

## Position Management Rules
### Pyramid Scaling (Add to Winning Positions)
- **Condition**: Current profit > 2%, original stop moved to break-even, trend still strong
- **Sizing**: First heavy (100%), then light (50%, 25%, 12.5% of initial)
- **Entry**: Each add must be at better price than previous entry
- **Stop Loss**: Use original stop or trailing stop for all positions

### Trailing Stop Loss (Protect Profits)
- **Phase 1 (0-2% profit)**: Keep initial stop, don't move
- **Phase 2 (2-4% profit)**: Move stop to break-even (entry price)
- **Phase 3 (4-10% profit)**: Trail with 50% profit protection (entry + 50% of profit)
- **Phase 4 (>10% profit)**: Aggressive trail with 1-1.5× ATR from current price

### Reduce Position (Risk Management)
- **Condition**: Profit target 50% reached, or trend weakening
- **Sizing**: Reduce by 50% on first target, let runner continue

## Trading Discipline Constraints
1. **Daily Loss Limit**: Stop trading if daily loss ≥ 3% of account balance
2. **Consecutive Losses**: After 3 consecutive losses, reduce risk to 0.5% or stop trading
3. **Emotional States to Avoid**: NEVER trade when emotional state is "greedy", "fearful", "fomo", or "revenge"
4. **Low Confluence Protection**: If confluence < 0.5, action MUST be "hold"
5. **Overtrading Prevention**: Max 3 trades per day unless clear A+ setups

## Output Constraints
- leverage: Must be >= 1 (no zero or negative leverage)
- reasoning: Keep it concise (1-2 sentences maximum)
- All numeric values: Use appropriate precision (2 decimals for prices, integers for leverage)"""

TRADING_USER = """## Multi-Timeframe Analysis Summary
{mtf_summary}

## Current Timeframe Technical Analysis
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
- ATR (Average True Range): {atr} USDT

## Current Position Status
{position_info}
{position_performance}

## Trading Discipline Status
- Daily PnL: {daily_pnl} USDT
- Trades Today: {trades_today}
- Recent Win Rate: {recent_win_rate}%
- Consecutive Losses: {consecutive_losses}
- Emotional State: {emotional_state}

## Strategy Preferences
- Strategy Type: {strategy_type}
- Leverage Range: {leverage_min}x - {leverage_max}x
- Default Stop Loss: {stop_loss_percent}%
- Default Take Profit: {take_profit_percent}%

## Account Balance
- Available Balance: {available_balance} USDT

## Position Management Context
{position_management_context}

Please make a trading decision following professional multi-timeframe methodology and trading discipline constraints."""

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
        "leverage": {
            "type": "integer",
            "minimum": 1,
            "description": "杠杆倍数 (>=1)",
        },
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
        "reasoning": {
            "type": "string",
            "maxLength": 200,
            "description": "决策理由 (简短，1-2句话)",
        },
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
