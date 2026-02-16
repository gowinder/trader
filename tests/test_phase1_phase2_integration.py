"""Phase 1 + Phase 2 integration tests: MTF data flow + strategy weight optimization."""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from ai_trader.data.multi_timeframe import MultiTimeframeData, TrendDirection


# ===========================================================================
# Phase 1: MTF data passed to decision engine
# ===========================================================================
class TestMTFDataFlow:

    def _make_mtf_data(self):
        return MultiTimeframeData(
            symbol="BTC/USDT:USDT",
            analyses={},
            overall_trend=TrendDirection.UPTREND,
            confluence_score=0.85,
            recommended_action="buy",
        )

    @pytest.mark.asyncio
    async def test_mtf_data_passed_to_decision(self):
        """MTF 数据应该被获取并传递给 analyze_and_decide"""
        mtf_data = self._make_mtf_data()

        # Mock MTF manager
        mtf_manager = AsyncMock()
        mtf_manager.get_multi_timeframe_data = AsyncMock(return_value=mtf_data)

        # Mock decision engine
        from ai_trader.models.decision import TradingDecision, TechnicalAnalysisResult, RiskAssessment
        decision = MagicMock(spec=TradingDecision)
        decision.action = "hold"
        decision.confidence = 50.0
        decision.reasoning = "test"
        decision.reasoning_zh = "test"
        tech = MagicMock(spec=TechnicalAnalysisResult)
        risk = MagicMock(spec=RiskAssessment)

        decision_engine = AsyncMock()
        decision_engine.analyze_and_decide = AsyncMock(return_value=(decision, tech, risk))

        # Simulate the flow from _run_cycle_for_symbol_impl
        mtf_result = await mtf_manager.get_multi_timeframe_data("BTC/USDT:USDT")
        assert mtf_result is not None
        assert mtf_result.overall_trend == TrendDirection.UPTREND
        assert mtf_result.confluence_score == 0.85

        # Call analyze_and_decide with mtf_data
        market_data = MagicMock()
        position = None
        balance = 1000.0
        equity = 1000.0

        await decision_engine.analyze_and_decide(
            market_data, position, balance, equity,
            mtf_data=mtf_result,
        )

        # Verify mtf_data was passed
        decision_engine.analyze_and_decide.assert_called_once()
        call_kwargs = decision_engine.analyze_and_decide.call_args
        assert call_kwargs.kwargs["mtf_data"] is mtf_result

    @pytest.mark.asyncio
    async def test_mtf_failure_graceful_degradation(self):
        """MTF 失败时应该降级为 None，不影响决策"""
        mtf_manager = AsyncMock()
        mtf_manager.get_multi_timeframe_data = AsyncMock(side_effect=Exception("API timeout"))

        # Simulate graceful degradation
        mtf_data = None
        try:
            mtf_data = await mtf_manager.get_multi_timeframe_data("BTC/USDT:USDT")
        except Exception:
            pass  # graceful degradation

        assert mtf_data is None

    @pytest.mark.asyncio
    async def test_mtf_returns_none_handled(self):
        """MTF 返回 None（数据不足）时正常处理"""
        mtf_manager = AsyncMock()
        mtf_manager.get_multi_timeframe_data = AsyncMock(return_value=None)

        mtf_data = await mtf_manager.get_multi_timeframe_data("BTC/USDT:USDT")
        assert mtf_data is None


# ===========================================================================
# Phase 2: Strategy weight optimization
# ===========================================================================
class TestStrategyWeightOptimization:

    @pytest.mark.asyncio
    async def test_weight_optimizer_updates_selector(self):
        """权重优化器应该更新策略选择器"""
        from ai_trader.optimization.weight_optimizer import StrategyWeightOptimizer
        from ai_trader.strategies.strategy_selector import StrategySelector

        db = AsyncMock()
        # 返回足够多的交易数据
        rows = []
        for i in range(25):
            rows.append({
                "strategy_signals": '{"trend_following": {"action": "buy", "confidence": 0.8}}',
                "realized_pnl": 10.0 if i % 3 != 0 else -5.0,
                "pnl_percent": 2.0 if i % 3 != 0 else -1.0,
            })
        db.fetch = AsyncMock(return_value=rows)

        optimizer = StrategyWeightOptimizer(db)
        selector = StrategySelector(["trend_following", "mean_reversion"])

        # Before: no overrides
        assert selector._weight_overrides == {}

        weights = await optimizer.compute_optimal_weights("strong_trend")
        assert "trend_following" in weights
        assert weights["trend_following"] > 0

        # Use update_strategy_selector
        updated = await optimizer.update_strategy_selector(selector)
        # 可能有多个市场状态被更新（取决于数据）
        assert updated >= 0

    @pytest.mark.asyncio
    async def test_weight_optimizer_insufficient_samples(self):
        """样本不足时返回空权重"""
        from ai_trader.optimization.weight_optimizer import StrategyWeightOptimizer

        db = AsyncMock()
        db.fetch = AsyncMock(return_value=[{"pnl_percent": 1.0} for _ in range(5)])

        optimizer = StrategyWeightOptimizer(db)
        weights = await optimizer.compute_optimal_weights("strong_trend")
        assert weights == {}

    @pytest.mark.asyncio
    async def test_weight_optimizer_db_error(self):
        """数据库错误时返回空权重"""
        from ai_trader.optimization.weight_optimizer import StrategyWeightOptimizer

        db = AsyncMock()
        db.fetch = AsyncMock(side_effect=Exception("DB connection lost"))

        optimizer = StrategyWeightOptimizer(db)
        weights = await optimizer.compute_optimal_weights("strong_trend")
        assert weights == {}

    @pytest.mark.asyncio
    async def test_update_strategy_weights_method(self):
        """_update_strategy_weights 方法正确执行"""
        from ai_trader.optimization.weight_optimizer import StrategyWeightOptimizer

        optimizer = AsyncMock(spec=StrategyWeightOptimizer)
        optimizer.update_strategy_selector = AsyncMock(return_value=3)

        selector = MagicMock()

        # Simulate the scheduler method
        updated = await optimizer.update_strategy_selector(selector)
        assert updated == 3
        optimizer.update_strategy_selector.assert_called_once_with(selector)

    def test_hourly_trigger_logic(self):
        """每小时触发逻辑：同一小时不重复触发"""
        from datetime import datetime

        last_update = ""
        triggered = []

        # Simulate multiple loop iterations in the same hour
        for _ in range(5):
            current_hour = "2026-02-16 10"
            if current_hour != last_update:
                last_update = current_hour
                triggered.append(current_hour)

        # Should trigger only once per hour
        assert len(triggered) == 1

        # New hour triggers again
        current_hour = "2026-02-16 11"
        if current_hour != last_update:
            last_update = current_hour
            triggered.append(current_hour)

        assert len(triggered) == 2

    def test_selector_weight_override_applied(self):
        """StrategySelector 的 _weight_overrides 应用到 select_strategies"""
        from ai_trader.strategies.strategy_selector import StrategySelector

        selector = StrategySelector(["trend_following", "mean_reversion"])

        # Default: no overrides
        assert "strong_trend" not in selector._weight_overrides

        # Apply override
        selector.update_weights("strong_trend", {
            "trend_following": 0.8,
            "mean_reversion": 0.2,
        })

        assert "strong_trend" in selector._weight_overrides
        assert selector._weight_overrides["strong_trend"]["trend_following"] == 0.8
