"""测试 Advisory 策略预设切换建议功能"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from ai_trader.models.advisory import (
    Suggestion, SuggestionType, SuggestionStatus, AdvisoryResult, Urgency,
)
from ai_trader.advisory.executors import StrategyExecutor, ExecutionResult
from ai_trader.advisory.context import AdvisoryContextBuilder
from ai_trader.advisory.engine import AdvisoryEngine
from ai_trader.models.advisory import TriggerType


# ========== Model Tests ==========

class TestStrategyChangeModel:
    def test_suggestion_type_strategy_change_exists(self):
        assert SuggestionType.STRATEGY_CHANGE == "strategy_change"

    def test_strategy_change_suggestion_model(self):
        s = Suggestion(
            type=SuggestionType.STRATEGY_CHANGE,
            target="range_harvest",
            action="switch_preset",
            detail={"preset_name": "range_harvest"},
            reasoning="市场处于震荡状态，当前趋势策略不适配",
            risk_note="切换策略后可能错过潜在趋势行情",
        )
        assert s.type == SuggestionType.STRATEGY_CHANGE
        assert s.status == SuggestionStatus.PENDING
        assert s.detail["preset_name"] == "range_harvest"

    def test_advisory_result_with_strategy_change(self):
        s = Suggestion(
            type=SuggestionType.STRATEGY_CHANGE,
            target="aggressive_trend",
            action="switch_preset",
            detail={"preset_name": "aggressive_trend"},
            reasoning="强趋势行情，建议切换到激进趋势策略",
            risk_note="激进策略风险较高",
        )
        result = AdvisoryResult(
            urgency=Urgency.MEDIUM,
            suggestions=[s],
            market_summary="BTC 出现强劲上涨趋势",
        )
        assert len(result.suggestions) == 1
        assert result.suggestions[0].type == SuggestionType.STRATEGY_CHANGE


# ========== StrategyExecutor Tests ==========

class TestStrategyExecutor:
    def _make_presets(self):
        return [
            {"id": 1, "name": "steady_trend", "display_name": "稳健趋势",
             "config_json": '{"enabled_strategies": ["trend_following"]}'},
            {"id": 2, "name": "range_harvest", "display_name": "震荡收割",
             "config_json": '{"enabled_strategies": ["mean_reversion"]}'},
            {"id": 3, "name": "aggressive_trend", "display_name": "激进趋势",
             "config_json": '{"enabled_strategies": ["trend_following", "breakout"]}'},
        ]

    @pytest.mark.asyncio
    async def test_switch_preset_success(self):
        presets = self._make_presets()
        mock_service = AsyncMock()
        mock_service.get_all_presets = AsyncMock(return_value=presets)
        mock_service.get_active_preset = AsyncMock(return_value=presets[0])  # 当前是 steady_trend
        mock_service.activate_preset = AsyncMock(return_value=True)
        mock_redis = AsyncMock()

        executor = StrategyExecutor(mock_service, mock_redis)
        result = await executor.execute("switch_preset", "range_harvest", {"preset_name": "range_harvest"})

        assert result.success is True
        assert "震荡收割" in result.message
        mock_service.activate_preset.assert_called_once_with(2)
        mock_redis.set.assert_called_once()
        mock_redis.publish.assert_called_once()
        # 验证 publish 使用正确的事件名
        publish_args = mock_redis.publish.call_args
        assert publish_args[0][0] == "strategy:preset:updated"

    @pytest.mark.asyncio
    async def test_switch_preset_not_found(self):
        presets = self._make_presets()
        mock_service = AsyncMock()
        mock_service.get_all_presets = AsyncMock(return_value=presets)
        mock_service.get_active_preset = AsyncMock(return_value=None)
        mock_redis = AsyncMock()

        executor = StrategyExecutor(mock_service, mock_redis)
        result = await executor.execute("switch_preset", "nonexistent", {"preset_name": "nonexistent"})

        assert result.success is False
        assert "未找到" in result.message

    @pytest.mark.asyncio
    async def test_switch_preset_already_active(self):
        presets = self._make_presets()
        mock_service = AsyncMock()
        mock_service.get_all_presets = AsyncMock(return_value=presets)
        mock_service.get_active_preset = AsyncMock(return_value=presets[0])  # 当前是 steady_trend
        mock_redis = AsyncMock()

        executor = StrategyExecutor(mock_service, mock_redis)
        result = await executor.execute("switch_preset", "steady_trend", {"preset_name": "steady_trend"})

        assert result.success is False
        assert "无需切换" in result.message
        mock_service.activate_preset.assert_not_called()

    @pytest.mark.asyncio
    async def test_switch_preset_activate_fails(self):
        presets = self._make_presets()
        mock_service = AsyncMock()
        mock_service.get_all_presets = AsyncMock(return_value=presets)
        mock_service.get_active_preset = AsyncMock(return_value=presets[0])
        mock_service.activate_preset = AsyncMock(return_value=False)
        mock_redis = AsyncMock()

        executor = StrategyExecutor(mock_service, mock_redis)
        result = await executor.execute("switch_preset", "range_harvest", {"preset_name": "range_harvest"})

        assert result.success is False
        assert "切换失败" in result.message

    @pytest.mark.asyncio
    async def test_no_change_action(self):
        mock_service = AsyncMock()
        mock_service.get_active_preset = AsyncMock(return_value=None)
        mock_redis = AsyncMock()
        executor = StrategyExecutor(mock_service, mock_redis)
        result = await executor.execute("no_change", "global", {})

        assert result.success is True
        assert "保持不变" in result.message

    @pytest.mark.asyncio
    async def test_unknown_action(self):
        mock_service = AsyncMock()
        mock_service.get_active_preset = AsyncMock(return_value=None)
        mock_redis = AsyncMock()
        executor = StrategyExecutor(mock_service, mock_redis)
        result = await executor.execute("unknown_action", "global", {})

        assert result.success is False
        assert "未知" in result.message

    @pytest.mark.asyncio
    async def test_target_fallback_to_preset_name(self):
        """当 detail 没有 preset_name 时使用 target"""
        presets = self._make_presets()
        mock_service = AsyncMock()
        mock_service.get_all_presets = AsyncMock(return_value=presets)
        mock_service.get_active_preset = AsyncMock(return_value=presets[0])
        mock_service.activate_preset = AsyncMock(return_value=True)
        mock_redis = AsyncMock()

        executor = StrategyExecutor(mock_service, mock_redis)
        result = await executor.execute("switch_preset", "range_harvest", {})

        assert result.success is True

    @pytest.mark.asyncio
    async def test_switch_preset_no_redis(self):
        """没有 Redis 时只做 PG 写入"""
        presets = self._make_presets()
        mock_service = AsyncMock()
        mock_service.get_all_presets = AsyncMock(return_value=presets)
        mock_service.get_active_preset = AsyncMock(return_value=presets[0])
        mock_service.activate_preset = AsyncMock(return_value=True)

        executor = StrategyExecutor(mock_service, None)
        result = await executor.execute("switch_preset", "range_harvest", {"preset_name": "range_harvest"})

        assert result.success is True

    @pytest.mark.asyncio
    async def test_change_preset_action_alias(self):
        """验证 change_preset action 别名"""
        presets = self._make_presets()
        mock_service = AsyncMock()
        mock_service.get_all_presets = AsyncMock(return_value=presets)
        mock_service.get_active_preset = AsyncMock(return_value=presets[0])
        mock_service.activate_preset = AsyncMock(return_value=True)
        mock_redis = AsyncMock()

        executor = StrategyExecutor(mock_service, mock_redis)
        result = await executor.execute("change_preset", "range_harvest", {"preset_name": "range_harvest"})

        assert result.success is True


# ========== Context Builder Tests ==========

class TestContextBuilderStrategyPreset:
    @pytest.mark.asyncio
    async def test_context_includes_strategy_preset_info(self):
        builder = AdvisoryContextBuilder(db=None)
        context = await builder.build(
            symbols=["BTC/USDT:USDT"],
            positions=[],
            market_data={"BTC/USDT:USDT": {"current_price": 50000, "change_24h": -1.5}},
            sentiment=None,
            trigger_reason="scheduled",
            current_config={"stop_loss_percent": 5.0},
            strategy_preset_info={
                "active_preset": {
                    "name": "steady_trend",
                    "display_name": "稳健趋势",
                    "description": "跟随明确趋势",
                    "risk_level": "low",
                },
                "all_presets": [
                    {"name": "steady_trend", "display_name": "稳健趋势",
                     "description": "跟随明确趋势", "risk_level": "low"},
                    {"name": "range_harvest", "display_name": "震荡收割",
                     "description": "区间震荡市场高抛低吸", "risk_level": "medium"},
                ],
            },
        )
        assert "稳健趋势" in context
        assert "steady_trend" in context
        assert "震荡收割" in context
        assert "[当前]" in context

    @pytest.mark.asyncio
    async def test_context_includes_market_classifications(self):
        builder = AdvisoryContextBuilder(db=None)
        context = await builder.build(
            symbols=["BTC/USDT:USDT"],
            positions=[],
            market_data={"BTC/USDT:USDT": {"current_price": 50000, "change_24h": 3.5}},
            sentiment=None,
            trigger_reason="scheduled",
            current_config={"stop_loss_percent": 5.0},
            market_classifications={
                "BTC/USDT:USDT": {
                    "state": "strong_trend",
                    "confidence": 0.85,
                    "adx_value": 30.5,
                    "volatility": 2.3,
                    "trend_direction": 1,
                },
            },
        )
        assert "strong_trend" in context
        assert "上涨" in context
        assert "ADX" in context

    @pytest.mark.asyncio
    async def test_context_no_preset_info(self):
        builder = AdvisoryContextBuilder(db=None)
        context = await builder.build(
            symbols=["BTC/USDT:USDT"],
            positions=[],
            market_data={},
            sentiment=None,
            trigger_reason="scheduled",
            current_config={"stop_loss_percent": 5.0},
        )
        assert "策略预设信息不可用" in context
        assert "市场分类信息不可用" in context

    @pytest.mark.asyncio
    async def test_config_format_filters_internal_keys(self):
        builder = AdvisoryContextBuilder(db=None)
        context = await builder.build(
            symbols=["BTC/USDT:USDT"],
            positions=[],
            market_data={},
            sentiment=None,
            trigger_reason="scheduled",
            current_config={
                "stop_loss_percent": 5.0,
                "_strategy_preset_info": {"should": "not appear"},
                "_market_classifications": {"should": "not appear"},
            },
        )
        assert "_strategy_preset_info" not in context
        assert "_market_classifications" not in context
        assert "stop_loss_percent" in context


# ========== Engine Type Mapping Tests ==========

class TestEngineTypeMapping:
    @pytest.mark.asyncio
    async def test_engine_parses_strategy_change_type(self):
        llm = AsyncMock()
        llm.chat = AsyncMock(return_value={
            "urgency": "medium",
            "market_summary": "市场从趋势转为震荡",
            "suggestions": [
                {
                    "type": "strategy_change",
                    "target": "range_harvest",
                    "action": "switch_preset",
                    "detail": {"preset_name": "range_harvest"},
                    "reasoning": "市场进入震荡区间，建议切换到均值回归策略",
                    "risk_note": "可能错过突破行情",
                }
            ],
        })
        llm.provider_name = "openrouter"
        llm.model_name = "test"

        persistence = AsyncMock()
        persistence.save_advisory = AsyncMock(return_value=uuid4())
        context_builder = AsyncMock()
        context_builder.build = AsyncMock(return_value="test context")

        engine = AdvisoryEngine(llm_client=llm, persistence=persistence, context_builder=context_builder)
        await engine.generate_advisory(
            trigger_type=TriggerType.SCHEDULED,
            trigger_detail={},
            symbols=["BTC/USDT:USDT"],
            positions=[],
            market_data={},
            sentiment=None,
            current_config={},
        )

        assert engine.last_result is not None
        assert len(engine.last_result.suggestions) == 1
        assert engine.last_result.suggestions[0].type == SuggestionType.STRATEGY_CHANGE
        assert engine.last_result.suggestions[0].action == "switch_preset"

    @pytest.mark.asyncio
    async def test_engine_maps_strategy_alias(self):
        llm = AsyncMock()
        llm.chat = AsyncMock(return_value={
            "urgency": "low",
            "market_summary": "市场稳定",
            "suggestions": [
                {
                    "type": "strategy",  # 使用别名
                    "target": "aggressive_trend",
                    "action": "switch_preset",
                    "detail": {"preset_name": "aggressive_trend"},
                    "reasoning": "建议切换",
                    "risk_note": "注意风险",
                }
            ],
        })
        llm.provider_name = "openrouter"
        llm.model_name = "test"

        persistence = AsyncMock()
        persistence.save_advisory = AsyncMock(return_value=uuid4())
        context_builder = AsyncMock()
        context_builder.build = AsyncMock(return_value="test context")

        engine = AdvisoryEngine(llm_client=llm, persistence=persistence, context_builder=context_builder)
        await engine.generate_advisory(
            trigger_type=TriggerType.SCHEDULED,
            trigger_detail={},
            symbols=["BTC/USDT:USDT"],
            positions=[],
            market_data={},
            sentiment=None,
            current_config={},
        )

        assert engine.last_result is not None
        assert engine.last_result.suggestions[0].type == SuggestionType.STRATEGY_CHANGE

    @pytest.mark.asyncio
    async def test_engine_passes_strategy_info_to_context(self):
        """验证 engine 将 _strategy_preset_info 传给 context_builder"""
        llm = AsyncMock()
        llm.chat = AsyncMock(return_value={
            "urgency": "low",
            "market_summary": "正常",
            "suggestions": [],
        })
        llm.provider_name = "openrouter"
        llm.model_name = "test"

        persistence = AsyncMock()
        persistence.save_advisory = AsyncMock(return_value=uuid4())
        context_builder = AsyncMock()
        context_builder.build = AsyncMock(return_value="test context")

        strategy_info = {"active_preset": {"name": "steady_trend"}, "all_presets": []}
        market_cls = {"BTC/USDT:USDT": {"state": "strong_trend"}}

        engine = AdvisoryEngine(llm_client=llm, persistence=persistence, context_builder=context_builder)
        await engine.generate_advisory(
            trigger_type=TriggerType.SCHEDULED,
            trigger_detail={},
            symbols=["BTC/USDT:USDT"],
            positions=[],
            market_data={},
            sentiment=None,
            current_config={
                "stop_loss_percent": 5.0,
                "_strategy_preset_info": strategy_info,
                "_market_classifications": market_cls,
            },
        )

        build_call = context_builder.build.call_args
        assert build_call.kwargs.get("strategy_preset_info") == strategy_info
        assert build_call.kwargs.get("market_classifications") == market_cls
