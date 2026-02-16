"""Advisory 上下文构建"""

from typing import Optional, List, Dict, Any

from ..persistence.database import DatabaseManager
from ..utils.logger import logger


class AdvisoryContextBuilder:
    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db

    async def build(
        self,
        symbols: List[str],
        positions: List[Dict],
        market_data: Dict[str, Dict],
        sentiment: Optional[Dict],
        trigger_reason: str,
        current_config: Dict[str, Any],
        account_summary: Optional[Dict] = None,
        strategy_preset_info: Optional[Dict] = None,
        market_classifications: Optional[Dict] = None,
    ) -> str:
        recent_trades = await self._get_recent_trades(limit=20)
        trades_text = self._format_trades(recent_trades)
        positions_text = self._format_positions(positions)
        market_text = self._format_market_data(market_data)
        sentiment_text = self._format_sentiment(sentiment)
        config_text = self._format_config(current_config)
        account_text = self._format_account(account_summary)
        strategy_text = self._format_strategy_preset(strategy_preset_info)
        market_class_text = self._format_market_classifications(market_classifications)
        last_decisions_text = await self._get_last_decisions(symbols)

        from .prompts import ADVISORY_USER
        return ADVISORY_USER.format(
            trigger_reason=trigger_reason,
            trade_count=len(recent_trades),
            recent_trades=trades_text,
            positions=positions_text,
            market_data=market_text,
            market_classification=market_class_text,
            sentiment=sentiment_text,
            current_config=config_text,
            strategy_preset=strategy_text,
            account_summary=account_text,
            last_decisions=last_decisions_text,
        )

    async def _get_recent_trades(self, limit: int = 20) -> List[Dict]:
        if not self.db:
            return []
        try:
            rows = await self.db.pool.fetch(
                """
                SELECT ph.symbol, d.action,
                       ph.realized_pnl, ph.pnl_percent,
                       ph.entry_price, ph.exit_price,
                       ph.entry_time, ph.exit_time, ph.leverage
                FROM position_history ph
                LEFT JOIN decisions d ON d.id = ph.entry_decision_id
                WHERE ph.status = 'closed'
                ORDER BY ph.exit_time DESC
                LIMIT $1
                """,
                limit,
            )
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"Failed to get recent trades: {e}")
            return []

    def _format_trades(self, trades: List[Dict]) -> str:
        if not trades:
            return "无近期交易记录"
        lines = []
        total_pnl = 0
        wins = 0
        for t in trades:
            pnl = float(t.get("realized_pnl", 0) or 0)
            total_pnl += pnl
            if pnl > 0:
                wins += 1
            lines.append(
                f"- {t.get('symbol', '?')}: {t.get('action', '?')}, "
                f"PnL: {pnl:+.2f} USDT ({float(t.get('pnl_percent', 0) or 0):+.2f}%), "
                f"杠杆: {t.get('leverage', '?')}x"
            )
        win_rate = (wins / len(trades) * 100) if trades else 0
        summary = f"总计 {len(trades)} 笔, 总PnL: {total_pnl:+.2f} USDT, 胜率: {win_rate:.0f}%\n"
        return summary + "\n".join(lines)

    def _format_positions(self, positions: List[Dict]) -> str:
        if not positions:
            return "当前无持仓"
        lines = []
        for p in positions:
            lines.append(
                f"- {p.get('symbol', '?')}: {p.get('side', '?')}, "
                f"入场价: {p.get('entry_price', '?')}, "
                f"浮动PnL: {p.get('unrealized_pnl', '?')} USDT, "
                f"ROI: {p.get('roi', '?')}%, "
                f"杠杆: {p.get('leverage', '?')}x"
            )
        return "\n".join(lines)

    def _format_market_data(self, market_data: Dict[str, Dict]) -> str:
        if not market_data:
            return "无行情数据"
        lines = []
        for symbol, data in market_data.items():
            lines.append(
                f"- {symbol}: 价格 {data.get('current_price', '?')} USDT, "
                f"24h变化: {data.get('change_24h', '?')}%"
            )
        return "\n".join(lines)

    def _format_sentiment(self, sentiment: Optional[Dict]) -> str:
        if not sentiment:
            return "情绪分析未启用"
        return (
            f"情绪评分: {sentiment.get('score', '?')}, "
            f"置信度: {sentiment.get('confidence', '?')}, "
            f"极度恐惧: {sentiment.get('extreme_fear', False)}, "
            f"极度贪婪: {sentiment.get('extreme_greed', False)}"
        )

    def _format_config(self, config: Dict[str, Any]) -> str:
        lines = [f"- {k}: {v}" for k, v in config.items() if not k.startswith("_")]
        return "\n".join(lines) if lines else "无配置信息"

    def _format_strategy_preset(self, info: Optional[Dict]) -> str:
        if not info:
            return "策略预设信息不可用"
        lines = []
        active = info.get("active_preset")
        if active:
            lines.append(f"当前激活预设: {active.get('display_name', '?')} ({active.get('name', '?')})")
            lines.append(f"  风险等级: {active.get('risk_level', '?')}")
            lines.append(f"  说明: {active.get('description', '?')}")
        else:
            lines.append("当前激活预设: 无")
        lines.append("")
        lines.append("所有可选预设:")
        for p in info.get("all_presets", []):
            marker = " [当前]" if active and p.get("name") == active.get("name") else ""
            lines.append(
                f"  - {p['name']} ({p.get('display_name', '?')}): "
                f"{p.get('description', '?')} | 风险: {p.get('risk_level', '?')}{marker}"
            )
        return "\n".join(lines)

    def _format_market_classifications(self, classifications: Optional[Dict]) -> str:
        if not classifications:
            return "市场分类信息不可用"
        lines = []
        trend_map = {1: "上涨", -1: "下跌", 0: "中性"}
        for symbol, cls_data in classifications.items():
            state = cls_data.get("state", "unknown")
            confidence = cls_data.get("confidence", 0)
            adx = cls_data.get("adx_value", 0)
            volatility = cls_data.get("volatility", 0)
            trend = cls_data.get("trend_direction", 0)
            trend_str = trend_map.get(trend, "未知")
            lines.append(
                f"- {symbol}: {state} (置信度: {confidence:.0%}), "
                f"ADX: {adx:.1f}, 波动率: {volatility:.2f}%, 趋势: {trend_str}"
            )
        return "\n".join(lines) if lines else "无数据"

    def _format_account(self, account: Optional[Dict]) -> str:
        if not account:
            return "无账户信息"
        return (
            f"总权益: {account.get('total_equity', '?')} USDT, "
            f"可用余额: {account.get('available_balance', '?')} USDT, "
            f"已用保证金: {account.get('margin_used', '?')} USDT"
        )

    async def _get_last_decisions(self, symbols: List[str]) -> str:
        """获取各交易对主循环最近决策，供 advisory 感知"""
        if not self.db or not symbols:
            return "无主循环决策数据"
        lines = []
        for symbol in symbols:
            try:
                row = await self.db.fetchrow(
                    """
                    SELECT action, confidence, reasoning, created_at
                    FROM decisions
                    WHERE symbol = $1
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    symbol,
                )
                if row:
                    r = dict(row)
                    lines.append(
                        f"- {symbol}: {r.get('action', '?')} "
                        f"(置信度: {r.get('confidence', '?')}), "
                        f"理由: {r.get('reasoning', '?')}, "
                        f"时间: {r.get('created_at', '?')}"
                    )
            except Exception as e:
                logger.warning(f"Failed to get last decision for {symbol}: {e}")
        return "\n".join(lines) if lines else "无主循环决策数据"
