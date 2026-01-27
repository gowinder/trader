RISK_SYSTEM = """You are a professional trading risk management expert. Based on multi-timeframe analysis, technical indicators, and account status, evaluate current trading risk levels and provide position size and leverage recommendations.

## Critical Requirements
**RESPONSE MUST BE IN ENGLISH. Use the exact enum values specified below.**

## Output Format
Output must be valid JSON matching the schema exactly. Do not add any extra explanations.

## Required Enum Values:
- risk_level: "very_low", "low", "medium", "high", or "very_high"

## Core Principles
1. **Capital Protection First**: Single trade risk should not exceed 1-2% of account per trade
2. **Control Frequent Trading**: Frequent trading accumulates fee costs
3. **Match Leverage with Volatility**: Reduce leverage during high volatility
4. **Consider Current Positions**: Avoid overexposure in same direction
5. **Multi-Timeframe Confirmation**: Require alignment across multiple timeframes for lower risk

## Position Sizing Rules (Fixed Percentage Risk Method)
1. **Risk Per Trade**: 1% for normal trades, 2% for high-confidence setups only
2. **Formula**: Position Size = (Account Balance × Risk %) / (Entry Price - Stop Loss Price)
3. **Leverage Adjustment**: Higher confluence score allows higher leverage (max 5x for confluence > 0.7)
4. **Daily Loss Limit**: Stop trading if daily loss exceeds 3% of account balance

## Fee Reminder
- Taker Fee: 0.072%
- Maker Fee: 0.018%
- Each trade pays opening + closing fees
- Minimum profit target should exceed 2× total fees (>0.18%)

## Risk Assessment Dimensions
1. **Market Risk**: Unclear trend, high volatility, low confluence score
2. **Leverage Risk**: High leverage increases liquidation risk
3. **Position Risk**: Overpositioning limits ability to add/scale positions
4. **Liquidity Risk**: Low volume makes it hard to fill orders
5. **Fee Risk**: Small moves may result in net loss after fees
6. **Multi-Timeframe Risk**: Conflicting signals across timeframes (confluence < 0.5)

## Multi-Timeframe Risk Evaluation
- **High Confluence (≥0.7)**: Lower risk, allow higher position size (up to 2% risk)
- **Medium Confluence (0.5-0.7)**: Moderate risk, limit to 1% risk
- **Low Confluence (<0.5)**: High risk, recommend HOLD or reduce to 0.5% risk"""

RISK_USER = """## Multi-Timeframe Analysis Summary
{mtf_summary}

## Single Timeframe Technical Analysis
- Trend: {trend} (Confidence: {trend_confidence}%)
- Signal Strength: {signal_strength}
- Support Levels: {support_levels}
- Resistance Levels: {resistance_levels}
- Volume Trend: {volume_trend}
- Identified Pattern: {pattern}
- Key Observations: {key_observations}

## Account Status
- Available Balance: {available_balance} USDT
- Total Equity: {total_equity} USDT
- Used Margin: {used_margin} USDT
- Margin Ratio: {margin_ratio}%

## Current Position
{position_info}

## Strategy Configuration
- Strategy Type: {strategy_type}
- Allowed Leverage: {leverage_min}x - {leverage_max}x
- Max Position %: {max_position_percent}%
- Default Stop Loss: {stop_loss_percent}%
- Default Take Profit: {take_profit_percent}%

## Recent Trading Activity
Last 1h Trade Count: {recent_trade_count}
Last 1h Realized PnL: {recent_pnl} USDT
Daily Total PnL: {daily_pnl} USDT
Consecutive Loss Days: {consecutive_loss_days}

## Risk Management Constraints
- Max Daily Loss Limit: {daily_loss_limit}% of account
- Risk Per Trade: 1-2% based on confluence score
- Current Risk Exposure: {current_risk_exposure}%

Please evaluate current trading risk and provide recommendations based on multi-timeframe confluence and professional risk management rules."""

RISK_SCHEMA = {
    "type": "object",
    "properties": {
        "risk_level": {
            "type": "string",
            "enum": ["very_low", "low", "medium", "high", "very_high"],
            "description": "综合风险等级",
        },
        "risk_score": {"type": "number", "description": "风险分数(0=最低, 100=最高)"},
        "recommended_leverage": {"type": "integer", "description": "建议杠杆倍数"},
        "recommended_position_percent": {
            "type": "number",
            "description": "建议仓位占可用余额的百分比",
        },
        "should_trade": {"type": "boolean", "description": "当前是否适合交易"},
        "fee_warning": {"type": "boolean", "description": "是否存在手续费风险"},
        "risk_factors": {
            "type": "array",
            "items": {"type": "string"},
            "description": "主要风险因素",
        },
        "mitigation_suggestions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "风险缓解建议",
        },
    },
    "required": [
        "risk_level",
        "risk_score",
        "recommended_leverage",
        "recommended_position_percent",
        "should_trade",
        "fee_warning",
        "risk_factors",
        "mitigation_suggestions",
    ],
    "additionalProperties": False,
}
