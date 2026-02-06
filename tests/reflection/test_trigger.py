# tests/reflection/test_trigger.py
"""复盘触发器测试"""

import asyncio
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

        started = await trigger.check_and_run()

        assert started is False
        assert not trigger.is_running

    @pytest.mark.asyncio
    async def test_trigger_at_threshold(self, trigger, mock_collector, mock_engine):
        mock_collector.get_count_since_last_reflection = AsyncMock(return_value=10)
        mock_collector.get_recent = AsyncMock(return_value=[MagicMock()] * 10)

        started = await trigger.check_and_run()

        assert started is True
        # 等待后台任务完成
        await trigger.wait_for_completion(timeout=1.0)
        mock_engine.run_reflection.assert_called_once()

    @pytest.mark.asyncio
    async def test_trigger_above_threshold(self, trigger, mock_collector, mock_engine):
        mock_collector.get_count_since_last_reflection = AsyncMock(return_value=15)
        mock_collector.get_recent = AsyncMock(return_value=[MagicMock()] * 15)

        started = await trigger.check_and_run()

        assert started is True
        await trigger.wait_for_completion(timeout=1.0)
        mock_engine.run_reflection.assert_called_once()
        mock_collector.get_recent.assert_called_once_with(limit=15)

    @pytest.mark.asyncio
    async def test_trigger_passes_memories_to_engine(
        self, trigger, mock_collector, mock_engine
    ):
        memories = [MagicMock() for _ in range(10)]
        mock_collector.get_count_since_last_reflection = AsyncMock(return_value=10)
        mock_collector.get_recent = AsyncMock(return_value=memories)

        await trigger.check_and_run()
        await trigger.wait_for_completion(timeout=1.0)

        mock_engine.run_reflection.assert_called_once_with(memories)

    @pytest.mark.asyncio
    async def test_skip_if_already_running(self, trigger, mock_collector, mock_engine):
        """测试：如果已有任务运行中，跳过本次触发"""
        mock_collector.get_count_since_last_reflection = AsyncMock(return_value=10)
        mock_collector.get_recent = AsyncMock(return_value=[MagicMock()] * 10)
        # 让 engine 执行慢一点
        mock_engine.run_reflection = AsyncMock(
            side_effect=lambda x: asyncio.sleep(0.1)
        )

        # 第一次触发
        started1 = await trigger.check_and_run()
        assert started1 is True
        assert trigger.is_running

        # 第二次触发应该跳过
        started2 = await trigger.check_and_run()
        assert started2 is False

        await trigger.wait_for_completion(timeout=1.0)

    @pytest.mark.asyncio
    async def test_is_running_property(self, trigger, mock_collector, mock_engine):
        """测试 is_running 属性"""
        assert not trigger.is_running

        mock_collector.get_count_since_last_reflection = AsyncMock(return_value=10)
        mock_collector.get_recent = AsyncMock(return_value=[MagicMock()] * 10)
        mock_engine.run_reflection = AsyncMock(
            side_effect=lambda x: asyncio.sleep(0.1)
        )

        await trigger.check_and_run()
        assert trigger.is_running

        await trigger.wait_for_completion(timeout=1.0)
        assert not trigger.is_running
