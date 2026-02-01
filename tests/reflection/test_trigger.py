# tests/reflection/test_trigger.py
"""复盘触发器测试"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from ai_trader.reflection.trigger import ReflectionTrigger


class TestReflectionTrigger:
    @pytest.fixture
    def mock_collector(self):
        collector = AsyncMock()
        return collector

    @pytest.fixture
    def mock_engine(self):
        engine = AsyncMock()
        engine.run_reflection = AsyncMock(return_value={"summary": "test"})
        return engine

    @pytest.fixture
    def trigger(self, mock_collector, mock_engine):
        return ReflectionTrigger(
            collector=mock_collector,
            engine=mock_engine,
            threshold=10,
        )

    @pytest.mark.asyncio
    async def test_no_trigger_below_threshold(self, trigger, mock_collector):
        mock_collector.get_count_since_last_reflection = AsyncMock(return_value=5)

        result = await trigger.check_and_run()

        assert result is None

    @pytest.mark.asyncio
    async def test_trigger_at_threshold(self, trigger, mock_collector, mock_engine):
        mock_collector.get_count_since_last_reflection = AsyncMock(return_value=10)
        mock_collector.get_recent = AsyncMock(return_value=[MagicMock()] * 10)

        result = await trigger.check_and_run()

        assert result is not None
        mock_engine.run_reflection.assert_called_once()

    @pytest.mark.asyncio
    async def test_trigger_above_threshold(self, trigger, mock_collector, mock_engine):
        mock_collector.get_count_since_last_reflection = AsyncMock(return_value=15)
        mock_collector.get_recent = AsyncMock(return_value=[MagicMock()] * 15)

        result = await trigger.check_and_run()

        assert result is not None
        mock_engine.run_reflection.assert_called_once()
        # 验证获取正确数量的交易
        mock_collector.get_recent.assert_called_once_with(limit=15)

    @pytest.mark.asyncio
    async def test_trigger_passes_memories_to_engine(
        self, trigger, mock_collector, mock_engine
    ):
        memories = [MagicMock() for _ in range(10)]
        mock_collector.get_count_since_last_reflection = AsyncMock(return_value=10)
        mock_collector.get_recent = AsyncMock(return_value=memories)

        await trigger.check_and_run()

        mock_engine.run_reflection.assert_called_once_with(memories)
