"""交易记忆收集器"""

import json
from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import uuid4

import logging

from .models import TradeMemoryEntry

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..persistence.database import DatabaseManager


class TradeMemoryCollector:
    """收集交易数据到短期记忆"""

    def __init__(self, db: "DatabaseManager"):
        self.db = db
        self._consecutive_losses = 0

    async def collect(
        self,
        position,
        result,
        decision,
        technical,
        market_state: str,
        patterns: Optional[list[str]] = None,
    ) -> TradeMemoryEntry:
        """收集单笔交易到记忆

        Args:
            position: 仓位信息
            result: 交易结果
            decision: 决策信息
            technical: 技术分析结果
            market_state: 市场状态
            patterns: 识别到的形态

        Returns:
            TradeMemoryEntry
        """
        now = datetime.now()
        is_winner = result.pnl > 0 if result else None

        # 更新连亏计数
        if is_winner is False:
            self._consecutive_losses += 1
        elif is_winner is True:
            self._consecutive_losses = 0

        entry = TradeMemoryEntry(
            trade_id=f"trade_{uuid4().hex[:8]}",
            timestamp=now,
            symbol=position.symbol,
            action=decision.action,
            confidence=decision.confidence,
            leverage=float(decision.leverage),
            reasoning=decision.reasoning,
            market_state=market_state,
            technical_snapshot={
                "trend": technical.trend if technical else None,
                "trend_confidence": getattr(technical, "trend_confidence", None)
                if technical
                else None,
                "signal_strength": getattr(technical, "signal_strength", None)
                if technical
                else None,
            },
            patterns_detected=patterns or [],
            entry_price=position.entry_price,
            exit_price=result.exit_price if result else None,
            pnl_percent=result.pnl_percent if result else None,
            hour_of_day=now.hour,
            day_of_week=now.weekday(),
            consecutive_losses=self._consecutive_losses,
            is_winner=is_winner,
        )

        # 持久化到数据库
        await self._save_to_db(entry)

        logger.info(f"交易记忆已收集: {entry.trade_id}, winner={is_winner}")
        return entry

    async def _save_to_db(self, entry: TradeMemoryEntry) -> None:
        """保存到数据库"""
        await self.db.execute(
            """
            INSERT INTO trade_memory (
                trade_id, timestamp, symbol, action, confidence, leverage, reasoning,
                market_state, timeframe_alignment, technical_snapshot, patterns_detected,
                entry_price, exit_price, pnl_percent, max_adverse_excursion,
                max_favorable_excursion, holding_duration, hour_of_day, day_of_week,
                consecutive_losses, is_winner
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21
            )
            """,
            entry.trade_id,
            entry.timestamp,
            entry.symbol,
            entry.action,
            entry.confidence,
            entry.leverage,
            entry.reasoning,
            entry.market_state,
            json.dumps(entry.timeframe_alignment),
            json.dumps(entry.technical_snapshot),
            json.dumps(entry.patterns_detected),
            entry.entry_price,
            entry.exit_price,
            entry.pnl_percent,
            entry.max_adverse_excursion,
            entry.max_favorable_excursion,
            str(entry.holding_duration) if entry.holding_duration else None,
            entry.hour_of_day,
            entry.day_of_week,
            entry.consecutive_losses,
            entry.is_winner,
        )

    async def get_recent(self, limit: int = 100) -> list[TradeMemoryEntry]:
        """获取最近的记忆"""
        rows = await self.db.fetch(
            """
            SELECT * FROM trade_memory
            ORDER BY timestamp DESC
            LIMIT $1
            """,
            limit,
        )
        return [self._row_to_entry(row) for row in rows]

    async def get_count_since_last_reflection(self) -> int:
        """获取自上次复盘以来的交易数"""
        result = await self.db.fetchval(
            """
            SELECT COUNT(*) FROM trade_memory
            WHERE timestamp > COALESCE(
                (SELECT MAX(triggered_at) FROM reflection_logs),
                '1970-01-01'::timestamp
            )
            """
        )
        return result or 0

    def _row_to_entry(self, row) -> TradeMemoryEntry:
        """数据库行转换为 Entry"""
        return TradeMemoryEntry(
            trade_id=row["trade_id"],
            timestamp=row["timestamp"],
            symbol=row["symbol"],
            action=row["action"],
            confidence=row["confidence"],
            leverage=row["leverage"],
            reasoning=row["reasoning"] or "",
            market_state=row["market_state"] or "",
            timeframe_alignment=json.loads(row["timeframe_alignment"] or "{}"),
            technical_snapshot=json.loads(row["technical_snapshot"] or "{}"),
            patterns_detected=json.loads(row["patterns_detected"] or "[]"),
            entry_price=row["entry_price"] or 0.0,
            exit_price=row["exit_price"],
            pnl_percent=row["pnl_percent"],
            max_adverse_excursion=row["max_adverse_excursion"] or 0.0,
            max_favorable_excursion=row["max_favorable_excursion"] or 0.0,
            hour_of_day=row["hour_of_day"] or 0,
            day_of_week=row["day_of_week"] or 0,
            consecutive_losses=row["consecutive_losses"] or 0,
            is_winner=row["is_winner"],
        )
