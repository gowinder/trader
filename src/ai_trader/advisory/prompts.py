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

STRATEGY_SUGGEST_SYSTEM = """You are a senior AI trading advisor specializing in strategy selection.
Your task is to analyze current market conditions and recommend the most suitable strategy preset.

## Available Strategy Presets
{presets_description}

## Output Rules
- Output valid JSON matching the schema exactly
- recommended_preset: Must be one of the preset names listed above
- reason: Must be in Chinese (中文), 200 characters or less, explain why this preset fits current conditions
- market_state: Your assessment of current market state (e.g., STRONG_TREND, WEAK_TREND, RANGE_BOUND, SIDEWAYS, BREAKOUT)
- current_strategy_analysis: Must be in Chinese (中文), 150 characters or less, evaluate how well the current active strategy fits the current market
- current_strategy_score: 1-10 integer, how well the current strategy matches market conditions (10=perfect fit)
- Be specific about which market signals led to your recommendation"""

STRATEGY_SUGGEST_SCHEMA = {
    "type": "object",
    "properties": {
        "recommended_preset": {
            "type": "string",
            "description": "Recommended preset name (e.g., steady_trend, aggressive_trend, etc.)",
        },
        "reason": {
            "type": "string",
            "description": "Recommendation reason in Chinese, 200 chars or less",
        },
        "market_state": {
            "type": "string",
            "enum": ["STRONG_TREND", "WEAK_TREND", "RANGE_BOUND", "SIDEWAYS", "BREAKOUT"],
            "description": "Current market state assessment",
        },
        "current_strategy_analysis": {
            "type": "string",
            "description": "Analysis of how well the current active strategy fits market conditions, in Chinese, 150 chars or less",
        },
        "current_strategy_score": {
            "type": "integer",
            "minimum": 1,
            "maximum": 10,
            "description": "Current strategy fit score (1=poor fit, 10=perfect fit)",
        },
    },
    "required": ["recommended_preset", "reason", "market_state", "current_strategy_analysis", "current_strategy_score"],
    "additionalProperties": False,
}

SYMBOL_STRATEGY_SUGGEST_SYSTEM = """You are a senior AI trading advisor specializing in per-symbol strategy selection.
Your task is to analyze market conditions for EACH given symbol individually and recommend the most suitable strategy preset for each one.

## Available Strategy Presets
{presets_description}

## Symbols to Analyze
{symbols_list}

## Output Rules
- Output valid JSON matching the schema exactly
- suggestions: An array of per-symbol recommendations
- Each item must include: symbol, recommended_preset, reason, market_state
- recommended_preset: Must be one of the preset names listed above
- reason: Must be in Chinese (中文), 100 characters or less per symbol
- market_state: Per-symbol market state (STRONG_TREND, WEAK_TREND, RANGE_BOUND, SIDEWAYS, BREAKOUT)
- Consider each symbol's unique market characteristics: volatility, trend, volume
- Different symbols may warrant different strategies"""

SYMBOL_STRATEGY_SUGGEST_SCHEMA = {
    "type": "object",
    "properties": {
        "suggestions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Trading symbol"},
                    "recommended_preset": {"type": "string", "description": "Recommended preset name"},
                    "reason": {"type": "string", "description": "Reason in Chinese, 100 chars or less"},
                    "market_state": {
                        "type": "string",
                        "enum": ["STRONG_TREND", "WEAK_TREND", "RANGE_BOUND", "SIDEWAYS", "BREAKOUT"],
                    },
                },
                "required": ["symbol", "recommended_preset", "reason", "market_state"],
            },
        },
    },
    "required": ["suggestions"],
    "additionalProperties": False,
}

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
