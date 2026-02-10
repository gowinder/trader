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
    ) -> str:
        recent_trades = await self._get_recent_trades(limit=20)
        trades_text = self._format_trades(recent_trades)
        positions_text = self._format_positions(positions)
        market_text = self._format_market_data(market_data)
        sentiment_text = self._format_sentiment(sentiment)
        config_text = self._format_config(current_config)
        account_text = self._format_account(account_summary)

        from .prompts import ADVISORY_USER
        return ADVISORY_USER.format(
            trigger_reason=trigger_reason,
            trade_count=len(recent_trades),
            recent_trades=trades_text,
            positions=positions_text,
            market_data=market_text,
            sentiment=sentiment_text,
            current_config=config_text,
            account_summary=account_text,
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
        lines = [f"- {k}: {v}" for k, v in config.items()]
        return "\n".join(lines) if lines else "无配置信息"

    def _format_account(self, account: Optional[Dict]) -> str:
        if not account:
            return "无账户信息"
        return (
            f"总权益: {account.get('total_equity', '?')} USDT, "
            f"可用余额: {account.get('available_balance', '?')} USDT, "
            f"已用保证金: {account.get('margin_used', '?')} USDT"
        )
