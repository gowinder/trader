# tests/optimization/test_shadow_runner.py
import pytest
from unittest.mock import AsyncMock
from ai_trader.optimization.shadow_runner import ShadowRunner


class TestShadowRunner:
    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        db.fetchval = AsyncMock(return_value="run_001")
        return db

    @pytest.fixture
    def runner(self, mock_db):
        return ShadowRunner(mock_db)

    @pytest.mark.asyncio
    async def test_start_shadow_run(self, runner):
        current = {"confidence_threshold": 60.0}
        candidate = {"confidence_threshold": 70.0}

        run_id = await runner.start(current, candidate)

        assert run_id is not None
        assert runner.is_running

    @pytest.mark.asyncio
    async def test_record_results(self, runner):
        await runner.start({"a": 1}, {"a": 2})

        # 记录实盘结果
        runner.record_current_result(is_winner=True, pnl=0.02)
        runner.record_current_result(is_winner=False, pnl=-0.01)

        # 记录影子结果
        runner.record_candidate_result(is_winner=True, pnl=0.025)
        runner.record_candidate_result(is_winner=True, pnl=0.015)

        stats = runner.get_stats()

        assert stats["current_trades"] == 2
        assert stats["candidate_trades"] == 2
        assert stats["candidate_win_rate"] == 1.0

    @pytest.mark.asyncio
    async def test_evaluate_should_switch(self, runner):
        await runner.start({"a": 1}, {"a": 2})

        # 模拟影子胜率更高
        for _ in range(5):
            runner.record_current_result(is_winner=True, pnl=0.01)
            runner.record_current_result(is_winner=False, pnl=-0.01)

        for _ in range(10):
            runner.record_candidate_result(is_winner=True, pnl=0.02)

        result = runner.evaluate()

        assert result["should_switch"] is True
