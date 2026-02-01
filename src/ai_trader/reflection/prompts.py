# src/ai_trader/reflection/prompts.py
"""复盘 Prompt 模板"""

REFLECTION_PROMPT = """你是交易策略分析师。分析以下 {n} 笔交易记录，从多个维度总结经验。

## 交易数据
{trade_data_json}

## 当前参数
{current_parameters}

## 分析维度要求

1. **绩效总览**：胜率、平均盈亏、最大回撤
2. **市况表现**：趋势市 vs 震荡市 vs 突破市的表现差异
3. **信号质量**：哪些技术信号组合更可靠，哪些容易误判
4. **时段分析**：不同时段的交易效果
5. **心理因素**：连亏后的决策质量是否下降

## 输出格式（严格 JSON）
{{
  "summary": "整体表现概述（1-2句话）",
  "insights": [
    {{"dimension": "维度名称", "finding": "发现内容", "confidence": 0.0-1.0}}
  ],
  "candidate_rules": [
    {{
      "condition": {{"market_state": "...", "indicator": "..."}},
      "recommendation": {{"param": "...", "adjustment": "..."}},
      "reasoning": "规则理由"
    }}
  ],
  "parameter_suggestions": {{
    "param_name": {{"new_value": 数值, "reasoning": "调整理由"}}
  }}
}}

只输出 JSON，不要其他内容。
"""
