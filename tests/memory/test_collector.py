# tests/memory/test_collector.py
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from ai_trader.memory.collector import TradeMemoryCollector
from ai_trader.memory.models import TradeMemoryEntry


class TestTradeMemoryCollector:
    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        db.fetchval = AsyncMock(return_value=1)
        return db

    @pytest.fixture
    def collector(self, mock_db):
        return TradeMemoryCollector(mock_db)

    @pytest.mark.asyncio
    async def test_collect_trade(self, collector):
        # 模拟交易数据
        position = MagicMock()
        position.symbol = "BTCUSDT"
        position.side = "long"
        position.entry_price = 50000.0
        position.size = 0.1

        result = MagicMock()
        result.exit_price = 52000.0
        result.pnl = 200.0
        result.pnl_percent = 4.0

        decision = MagicMock()
        decision.action = "close_long"
        decision.confidence = 80.0
        decision.leverage = 5
        decision.reasoning = "止盈"

        technical = MagicMock()
        technical.trend = "bullish"
        technical.trend_confidence = 0.8
        technical.signal_strength = 0.7

        market_state = "strong_trend"

        entry = await collector.collect(
            position=position,
            result=result,
            decision=decision,
            technical=technical,
            market_state=market_state,
        )

        assert entry.symbol == "BTCUSDT"
        assert entry.pnl_percent == 4.0
        assert entry.is_winner is True

    @pytest.mark.asyncio
    async def test_get_recent_memories(self, collector, mock_db):
        mock_db.fetch = AsyncMock(return_value=[
            {
                "trade_id": "t1",
                "timestamp": datetime.now(),
                "symbol": "BTCUSDT",
                "action": "close_long",
                "confidence": 75.0,
                "leverage": 5.0,
                "reasoning": "test",
                "market_state": "trending",
                "timeframe_alignment": "{}",
                "technical_snapshot": "{}",
                "patterns_detected": "[]",
                "entry_price": 50000.0,
                "exit_price": 51000.0,
                "pnl_percent": 2.0,
                "max_adverse_excursion": 0.5,
                "max_favorable_excursion": 2.5,
                "holding_duration": None,
                "hour_of_day": 14,
                "day_of_week": 2,
                "consecutive_losses": 0,
                "is_winner": True,
            }
        ])

        memories = await collector.get_recent(limit=10)
        assert len(memories) == 1
        assert memories[0].trade_id == "t1"

    @pytest.mark.asyncio
    async def test_consecutive_losses_tracking(self, collector):
        """测试连亏计数"""
        position = MagicMock()
        position.symbol = "BTCUSDT"
        position.entry_price = 50000.0

        decision = MagicMock()
        decision.action = "close_long"
        decision.confidence = 80.0
        decision.leverage = 5
        decision.reasoning = "test"

        technical = MagicMock()
        technical.trend = "bullish"
        technical.trend_confidence = 0.8
        technical.signal_strength = 0.7

        # 第一笔亏损
        result1 = MagicMock()
        result1.exit_price = 49000.0
        result1.pnl = -100.0
        result1.pnl_percent = -2.0

        entry1 = await collector.collect(
            position=position,
            result=result1,
            decision=decision,
            technical=technical,
            market_state="ranging",
        )
        assert entry1.consecutive_losses == 1

        # 第二笔亏损
        result2 = MagicMock()
        result2.exit_price = 48000.0
        result2.pnl = -200.0
        result2.pnl_percent = -4.0

        entry2 = await collector.collect(
            position=position,
            result=result2,
            decision=decision,
            technical=technical,
            market_state="ranging",
        )
        assert entry2.consecutive_losses == 2

        # 盈利后重置
        result3 = MagicMock()
        result3.exit_price = 52000.0
        result3.pnl = 200.0
        result3.pnl_percent = 4.0

        entry3 = await collector.collect(
            position=position,
            result=result3,
            decision=decision,
            technical=technical,
            market_state="trending",
        )
        assert entry3.consecutive_losses == 0

    @pytest.mark.asyncio
    async def test_get_count_since_last_reflection(self, collector, mock_db):
        """测试获取自上次复盘以来的交易数"""
        mock_db.fetchval = AsyncMock(return_value=5)

        count = await collector.get_count_since_last_reflection()
        assert count == 5
