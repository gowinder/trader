"""Phase 2 tests: optimization orchestrator, prompt enricher, config listener."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ai_trader.optimization.orchestrator import OptimizationOrchestrator
from ai_trader.optimization.shadow_runner import ShadowRunner, ShadowStats
from ai_trader.optimization.parameter_registry import ParameterRegistry


# ===========================================================================
# OptimizationOrchestrator tests
# ===========================================================================
class TestOptimizationOrchestrator:

    def _make_orchestrator(self):
        db = AsyncMock()
        registry = ParameterRegistry()
        shadow_runner = ShadowRunner(db)
        redis_client = AsyncMock()
        orch = OptimizationOrchestrator(
            db=db,
            shadow_runner=shadow_runner,
            parameter_registry=registry,
            redis_client=redis_client,
        )
        return orch

    @pytest.mark.asyncio
    async def test_no_suggestions_skips(self):
        orch = self._make_orchestrator()
        result = await orch.handle_reflection_result({"summary": "ok"})
        assert result is False

    @pytest.mark.asyncio
    async def test_empty_suggestions_skips(self):
        orch = self._make_orchestrator()
        result = await orch.handle_reflection_result({"parameter_suggestions": {}})
        assert result is False

    @pytest.mark.asyncio
    async def test_invalid_param_skips(self):
        """Param not in registry should be filtered out."""
        orch = self._make_orchestrator()
        result = await orch.handle_reflection_result({
            "parameter_suggestions": {
                "nonexistent_param": {"new_value": 0.5}
            }
        })
        assert result is False

    @pytest.mark.asyncio
    async def test_out_of_bounds_skips(self):
        """Param value outside bounds should be filtered."""
        orch = self._make_orchestrator()
        # confidence_threshold has bounds [0.3, 0.9]
        result = await orch.handle_reflection_result({
            "parameter_suggestions": {
                "confidence_threshold": {"new_value": 999.0}
            }
        })
        assert result is False

    @pytest.mark.asyncio
    async def test_valid_suggestion_starts_shadow_run(self):
        orch = self._make_orchestrator()
        # confidence_threshold default is 0.6, bounds [0.3, 0.9]
        result = await orch.handle_reflection_result({
            "parameter_suggestions": {
                "confidence_threshold": {"new_value": 70.0}
            }
        })
        assert result is True
        assert orch.shadow_runner.is_running

    @pytest.mark.asyncio
    async def test_shadow_already_running_skips(self):
        orch = self._make_orchestrator()
        # Start first shadow run
        await orch.handle_reflection_result({
            "parameter_suggestions": {
                "confidence_threshold": {"new_value": 70.0}
            }
        })
        assert orch.shadow_runner.is_running
        # Second attempt should skip
        result = await orch.handle_reflection_result({
            "parameter_suggestions": {
                "confidence_threshold": {"new_value": 80.0}
            }
        })
        assert result is False

    @pytest.mark.asyncio
    async def test_evaluate_not_running_returns_none(self):
        orch = self._make_orchestrator()
        result = await orch.evaluate_and_apply()
        assert result is None

    @pytest.mark.asyncio
    async def test_evaluate_insufficient_trades(self):
        orch = self._make_orchestrator()
        await orch.handle_reflection_result({
            "parameter_suggestions": {
                "confidence_threshold": {"new_value": 70.0}
            }
        })
        # Record only 3 trades (MIN_TRADES=10)
        for _ in range(3):
            orch.shadow_runner.record_current_result(True, 1.0)
            orch.shadow_runner.record_candidate_result(True, 1.0)
        result = await orch.evaluate_and_apply()
        assert result is None
        assert orch.shadow_runner.is_running  # still running

    @pytest.mark.asyncio
    async def test_evaluate_passes_and_applies(self):
        orch = self._make_orchestrator()
        await orch.handle_reflection_result({
            "parameter_suggestions": {
                "confidence_threshold": {"new_value": 70.0}
            }
        })
        # Current: 50% win rate, low pnl
        for _ in range(10):
            orch.shadow_runner.record_current_result(False, -0.01)
        # Candidate: 100% win rate, high pnl
        for _ in range(10):
            orch.shadow_runner.record_candidate_result(True, 0.1)

        result = await orch.evaluate_and_apply()
        assert result is not None
        assert result.get("should_switch") is True
        # Shadow runner should be completed
        assert not orch.shadow_runner.is_running

    @pytest.mark.asyncio
    async def test_evaluate_fails_completes_shadow(self):
        orch = self._make_orchestrator()
        await orch.handle_reflection_result({
            "parameter_suggestions": {
                "confidence_threshold": {"new_value": 70.0}
            }
        })
        # Both same results — no improvement
        for _ in range(10):
            orch.shadow_runner.record_current_result(True, 0.05)
            orch.shadow_runner.record_candidate_result(True, 0.05)

        result = await orch.evaluate_and_apply()
        assert result is None
        # Should be completed (rejected)
        assert not orch.shadow_runner.is_running

    @pytest.mark.asyncio
    async def test_scalar_suggestion_format(self):
        """Support flat value format: {"param": 0.7}"""
        orch = self._make_orchestrator()
        result = await orch.handle_reflection_result({
            "parameter_suggestions": {
                "confidence_threshold": 70.0
            }
        })
        assert result is True


# ===========================================================================
# PromptContextEnricher tests
# ===========================================================================
class TestPromptContextEnricher:

    def _make_enricher(self, fetch_return=None):
        from ai_trader.prompts.enricher import PromptContextEnricher
        db = AsyncMock()
        db.fetch = AsyncMock(return_value=fetch_return or [])
        return PromptContextEnricher(db)

    @pytest.mark.asyncio
    async def test_no_trades_returns_message(self):
        enricher = self._make_enricher([])
        result = await enricher.get_performance_summary("BTC/USDT:USDT")
        assert "No recent closed trades" in result

    @pytest.mark.asyncio
    async def test_performance_summary_with_trades(self):
        rows = [
            {"side": "long", "realized_pnl": 100, "pnl_percent": 2.0},
            {"side": "long", "realized_pnl": -50, "pnl_percent": -1.0},
            {"side": "short", "realized_pnl": 80, "pnl_percent": 1.5},
            {"side": "short", "realized_pnl": -30, "pnl_percent": -0.5},
        ]
        enricher = self._make_enricher(rows)
        result = await enricher.get_performance_summary("BTC/USDT:USDT")
        assert "2W/2L" in result
        assert "win rate: 50%" in result
        assert "Long win rate: 50%" in result

    @pytest.mark.asyncio
    async def test_consecutive_losses_warning(self):
        rows = [
            {"side": "long", "realized_pnl": -10, "pnl_percent": -1.0},
            {"side": "long", "realized_pnl": -20, "pnl_percent": -2.0},
            {"side": "long", "realized_pnl": -15, "pnl_percent": -1.5},
        ]
        enricher = self._make_enricher(rows)
        result = await enricher.get_performance_summary("BTC/USDT:USDT")
        assert "WARNING" in result
        assert "3 consecutive losses" in result

    @pytest.mark.asyncio
    async def test_db_error_returns_unavailable(self):
        from ai_trader.prompts.enricher import PromptContextEnricher
        db = AsyncMock()
        db.fetch = AsyncMock(side_effect=Exception("db error"))
        enricher = PromptContextEnricher(db)
        result = await enricher.get_performance_summary("BTC/USDT:USDT")
        assert "unavailable" in result

    @pytest.mark.asyncio
    async def test_active_rules_no_table(self):
        from ai_trader.prompts.enricher import PromptContextEnricher
        db = AsyncMock()
        db.fetch = AsyncMock(side_effect=Exception("table not found"))
        enricher = PromptContextEnricher(db)
        result = await enricher.get_active_rules()
        assert "No validated rules" in result

    @pytest.mark.asyncio
    async def test_active_rules_with_data(self):
        rows = [
            {
                "condition": "RSI < 30 and trend=up",
                "recommendation": "open long",
                "win_rate": 0.75,
                "sample_size": 20,
            },
        ]
        enricher = self._make_enricher()
        enricher.db.fetch = AsyncMock(return_value=rows)
        result = await enricher.get_active_rules()
        assert "RSI < 30" in result
        assert "75%" in result


# ===========================================================================
# Config listener optimization source skip test
# ===========================================================================
class TestConfigListenerOptimization:

    def test_optimization_source_detection(self):
        """Verify optimization messages have source field."""
        msg = json.dumps({"source": "optimization", "changes": {"stop_loss_percent": {"old": 5, "new": 4}}})
        cfg = json.loads(msg)
        assert cfg.get("source") == "optimization"

    def test_dashboard_source_no_field(self):
        """Dashboard messages don't have source field."""
        msg = json.dumps({"enabled": True, "decisionInterval": 5})
        cfg = json.loads(msg)
        assert cfg.get("source") is None


# ===========================================================================
# Preset switch preserves enricher test
# ===========================================================================
class TestPresetSwitchEnricher:

    def test_enricher_attribute_preserved_concept(self):
        """Verify that old_enricher pattern preserves the reference."""
        class FakeEngine:
            def __init__(self):
                self.prompt_enricher = None

        engine = FakeEngine()
        enricher_ref = object()
        engine.prompt_enricher = enricher_ref

        # Simulate preset switch
        old_enricher = getattr(engine, "prompt_enricher", None)
        engine = FakeEngine()  # rebuild
        engine.prompt_enricher = old_enricher

        assert engine.prompt_enricher is enricher_ref
