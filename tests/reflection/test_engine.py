# tests/reflection/test_engine.py
"""复盘引擎测试"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from ai_trader.reflection.engine import ReflectionEngine
from ai_trader.memory.models import TradeMemoryEntry


class TestReflectionEngine:
    @pytest.fixture
    def mock_llm(self):
        llm = AsyncMock()
        llm.generate = AsyncMock(
            return_value="""{
            "summary": "整体表现良好，趋势市胜率较高",
            "insights": [
                {"dimension": "市况", "finding": "趋势市胜率70%", "confidence": 0.8}
            ],
            "candidate_rules": [
                {
                    "condition": {"market_state": "ranging"},
                    "recommendation": {"confidence_threshold": "+10"},
                    "reasoning": "震荡市需提高门槛"
                }
            ],
            "parameter_suggestions": {
                "confidence_threshold": {"new_value": 70, "reasoning": "提升整体胜率"}
            }
        }"""
        )
        return llm

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        db.fetchval = AsyncMock(return_value="reflection_001")
        return db

    @pytest.fixture
    def engine(self, mock_llm, mock_db):
        return ReflectionEngine(llm_client=mock_llm, db=mock_db)

    @pytest.fixture
    def sample_memories(self):
        return [
            TradeMemoryEntry(
                trade_id=f"t{i}",
                timestamp=datetime.now(),
                symbol="BTCUSDT",
                action="close_long",
                confidence=75.0,
                leverage=5.0,
                reasoning="test",
                market_state="strong_trend",
                entry_price=50000.0,
                exit_price=51000.0,
                pnl_percent=2.0,
                is_winner=True,
            )
            for i in range(10)
        ]

    @pytest.mark.asyncio
    async def test_run_reflection(self, engine, sample_memories):
        result = await engine.run_reflection(sample_memories)

        assert "summary" in result
        assert "insights" in result
        assert "candidate_rules" in result
        assert "reflection_id" in result
        assert "trades_analyzed" in result
        assert result["trades_analyzed"] == 10

    @pytest.mark.asyncio
    async def test_run_reflection_calls_llm(self, engine, mock_llm, sample_memories):
        await engine.run_reflection(sample_memories)

        mock_llm.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_reflection_saves_to_db(self, engine, mock_db, sample_memories):
        await engine.run_reflection(sample_memories)

        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        # 验证 SQL 包含 reflection_logs
        assert "reflection_logs" in call_args[0][0]

    def test_parse_llm_response_valid_json(self, engine):
        response = """{
            "summary": "test",
            "insights": [],
            "candidate_rules": [],
            "parameter_suggestions": {}
        }"""

        result = engine._parse_response(response)

        assert result["summary"] == "test"
        assert result["insights"] == []
        assert result["candidate_rules"] == []
        assert result["parameter_suggestions"] == {}

    def test_parse_llm_response_with_code_block(self, engine):
        response = """```json
{
    "summary": "test with code block",
    "insights": [],
    "candidate_rules": [],
    "parameter_suggestions": {}
}
```"""

        result = engine._parse_response(response)

        assert result["summary"] == "test with code block"

    def test_parse_llm_response_invalid_json(self, engine):
        response = "invalid json response"

        result = engine._parse_response(response)

        assert result["summary"] == "解析失败"
        assert result["insights"] == []
        assert result["candidate_rules"] == []
        assert result["parameter_suggestions"] == {}

    def test_build_prompt(self, engine, sample_memories):
        prompt = engine._build_prompt(sample_memories)

        assert "10" in prompt  # 交易数量
        assert "BTCUSDT" in prompt  # 交易对
        assert "strong_trend" in prompt  # 市场状态


class TestReflectionEngineWithRegistry:
    @pytest.fixture
    def mock_registry(self):
        registry = MagicMock()
        registry.to_dict.return_value = {"confidence_threshold": 60.0}
        return registry

    @pytest.fixture
    def engine_with_registry(self, mock_registry):
        mock_llm = AsyncMock()
        mock_llm.generate = AsyncMock(
            return_value='{"summary": "test", "insights": [], "candidate_rules": [], "parameter_suggestions": {}}'
        )
        mock_db = AsyncMock()
        return ReflectionEngine(
            llm_client=mock_llm, db=mock_db, parameter_registry=mock_registry
        )

    def test_build_prompt_includes_parameters(
        self, engine_with_registry, mock_registry
    ):
        memories = [
            TradeMemoryEntry(
                trade_id="t1",
                timestamp=datetime.now(),
                symbol="BTCUSDT",
                action="close_long",
                confidence=75.0,
                leverage=5.0,
                reasoning="test",
                market_state="strong_trend",
                entry_price=50000.0,
            )
        ]

        prompt = engine_with_registry._build_prompt(memories)

        assert "confidence_threshold" in prompt
        mock_registry.to_dict.assert_called_once()
