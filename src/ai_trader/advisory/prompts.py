"""Advisory System Prompts"""

ADVISORY_SYSTEM = """You are a senior AI trading advisor conducting a comprehensive portfolio review.
Your role is to analyze the current trading state and provide actionable suggestions.

## Your Capabilities
1. **Parameter Adjustment**: Suggest changes to stop-loss, take-profit, leverage, strategy weights
2. **Position Actions**: Recommend closing, reducing, or adding to positions
3. **Symbol Management**: Suggest adding or removing trading pairs
4. **Strategy Preset Change**: Recommend switching to a different strategy preset based on market conditions

## Strategy Preset Change Guidelines
- Only suggest strategy changes when market conditions clearly mismatch the current preset
- For example: if market is RANGE_BOUND/SIDEWAYS but using a trend-following preset, suggest switching to range_harvest
- If market shows STRONG_TREND/BREAKOUT but using a conservative/range preset, suggest switching to aggressive_trend or breakout_hunter
- Strategy changes are high-impact operations - only suggest when confidence is high
- Use type "strategy_change", set target to the preset name (e.g., "range_harvest"), action "switch_preset"
- Include preset_name in detail: {"preset_name": "range_harvest"}

## Output Rules
- Output valid JSON matching the schema exactly
- reasoning: Must be in Chinese (中文)
- risk_note: Must be in Chinese (中文)
- Be specific with numbers and targets
- Only suggest changes when there's clear evidence
- If everything looks fine, return empty suggestions with appropriate market_summary

## Urgency Levels
- **high**: Immediate action recommended (large losses, extreme volatility, critical risk)
- **medium**: Action recommended within next few hours
- **low**: Informational, can be reviewed at convenience"""

ADVISORY_USER = """## 触发原因
{trigger_reason}

## 最近交易记录 (最近 {trade_count} 笔)
{recent_trades}

## 当前持仓状态
{positions}

## 实时行情数据
{market_data}

## 市场分类
{market_classification}

## 情绪分析
{sentiment}

## 当前策略配置
{current_config}

## 策略预设信息
{strategy_preset}

## 账户概况
{account_summary}

## 主循环最近决策
{last_decisions}
注意：你的建议应与主循环决策保持一致性。如果建议与主循环最近决策矛盾，
请在 reasoning 中明确说明为什么需要覆盖主循环的判断。

请综合分析以上信息，给出交易建议。如果一切正常无需调整，suggestions 可以为空。"""

ADVISORY_SCHEMA = {
    "type": "object",
    "properties": {
        "urgency": {
            "type": "string",
            "enum": ["high", "medium", "low"],
        },
        "market_summary": {
            "type": "string",
            "description": "当前市场概况 (中文, 100字以内)",
        },
        "suggestions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["param_adjust", "position_action", "symbol_change", "strategy_change"],
                    },
                    "target": {"type": "string", "description": "交易对或 'global'"},
                    "action": {"type": "string", "description": "具体动作"},
                    "detail": {"type": "object", "description": "具体参数"},
                    "reasoning": {"type": "string", "description": "中文理由"},
                    "risk_note": {"type": "string", "description": "中文风险提示"},
                },
                "required": ["type", "target", "action", "detail", "reasoning", "risk_note"],
            },
        },
    },
    "required": ["urgency", "market_summary", "suggestions"],
    "additionalProperties": False,
}
