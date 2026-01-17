"""运行报告生成器 - 每轮生成 Markdown 报告"""

from datetime import datetime
from pathlib import Path
from typing import Optional, List
from .models.decision import TradingDecision, TechnicalAnalysisResult
from .models.market import MarketData
from .models.order import Position


class Reporter:
    """报告生成器"""

    def __init__(self, output_dir: str = "run_output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        market_data: MarketData,
        tech_analysis: TechnicalAnalysisResult,
        decision: TradingDecision,
        position_before: Optional[Position],
        position_after: Optional[Position],
        pnl: float = 0.0,
    ) -> Path:
        """生成运行报告"""
        now = datetime.now()
        action_name = self._action_to_chinese(decision.action)
        # Handle pnl logic
        pnl_str = f"+{pnl:.2f}%" if pnl >= 0 else f"{pnl:.2f}%"

        # Filename: timestamp_action(Chinese)_pnl.md
        filename = f"{now.strftime('%Y%m%d_%H%M%S')}_{action_name}_{pnl_str}.md"
        filepath = self.output_dir / filename

        content = f"""# 交易运行报告

**时间**: {now.strftime("%Y-%m-%d %H:%M:%S")}  
**交易对**: {market_data.symbol}  
**操作**: {action_name}  
**PnL**: {pnl_str}

---

## 1. 市场数据摘要

| 指标 | 数值 |
|------|------|
| 当前价格 | {market_data.current_price:.4f} |
| MA7 | {market_data.indicators.ma7:.4f} |
| MA25 | {market_data.indicators.ma25:.4f} |
| RSI(14) | {market_data.indicators.rsi:.2f} |
| MACD | {market_data.indicators.macd:.4f} |

---

## 2. AI 技术分析

- **趋势**: {tech_analysis.trend} (置信度: {tech_analysis.trend_confidence}%)
- **信号强度**: {tech_analysis.signal_strength}
- **支撑位**: {tech_analysis.support_levels}
- **阻力位**: {tech_analysis.resistance_levels}
- **关键观察**:
{self._format_list(tech_analysis.key_observations)}

---

## 3. 交易决策

- **操作**: {decision.action}
- **置信度**: {decision.confidence}%
- **杠杆**: {decision.leverage}x
- **仓位比例**: {decision.position_size_percent}%
- **止损价**: {decision.stop_loss_price}
- **止盈价**: {decision.take_profit_price}
- **订单类型**: {decision.order_type}
- **理由**: {decision.reasoning}

---

## 4. 持仓变化

### 变化前
{self._format_position(position_before)}

### 变化后
{self._format_position(position_after)}

---

## 5. 账户 PnL

**本轮盈亏**: {pnl_str}
"""
        filepath.write_text(content, encoding="utf-8")
        return filepath

    def _action_to_chinese(self, action: str) -> str:
        mapping = {
            "open_long": "买入开多",
            "open_short": "卖出开空",
            "close_long": "平多",
            "close_short": "平空",
            "add_long": "加多仓",
            "add_short": "加空仓",
            "reduce_long": "减多仓",
            "reduce_short": "减空仓",
            "hold": "持仓观望",
        }
        return mapping.get(action, action)

    def _format_position(self, pos: Optional[Position]) -> str:
        if not pos:
            return "无持仓"
        return f"- 方向: {'多' if pos.side == 'long' else '空'}\n- 数量: {pos.size}\n- 开仓价: {pos.entry_price}\n- 未实现盈亏: {pos.unrealized_pnl}"

    def _format_list(self, items: List[str]) -> str:
        return "\n".join(f"  - {item}" for item in items)
