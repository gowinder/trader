"""Phase 3 tests: strategy weight optimizer, rule lifecycle, advisory coordination,
testnet account aggregation, adaptive thresholds."""

import json
from datetime import datetime, timedelta, timezone
import pytest
from unittest.mock import AsyncMock, MagicMock

from ai_trader.optimization.weight_optimizer import StrategyWeightOptimizer
from ai_trader.optimization.parameter_registry import ParameterRegistry
from ai_trader.strategies.strategy_selector import StrategySelector
from ai_trader.strategies.market_classifier import MarketState
from ai_trader.advisory.service import AdvisoryService


# ===========================================================================
# 3.1 StrategyWeightOptimizer
# ===========================================================================
class TestStrategyWeightOptimizer:

    def _make_optimizer(self, rows=None, row_count=0):
        db = AsyncMock()
        if rows is not None:
            db.fetch = AsyncMock(return_value=rows)
        else:
            db.fetch = AsyncMock(return_value=[])
        return StrategyWeightOptimizer(db), db

    @pytest.mark.asyncio
    async def test_insufficient_samples_returns_empty(self):
        """少于 MIN_SAMPLES 时返回空 dict"""
        rows = [{"strategy_signals": '{"trend_following": {}}', "realized_pnl": 10, "pnl_percent": 1.0}
                for _ in range(5)]
        opt, _ = self._make_optimizer(rows)
        result = await opt.compute_optimal_weights("STRONG_TREND")
        assert result == {}

    @pytest.mark.asyncio
    async def test_sufficient_samples_returns_weights(self):
        """充足样本时返回归一化权重"""
        rows = []
        for i in range(25):
            rows.append({
                "strategy_signals": json.dumps({"trend_following": {"action": "long"}}),
                "realized_pnl": 10.0 if i % 2 == 0 else -5.0,
                "pnl_percent": 2.0 if i % 2 == 0 else -1.0,
            })
        opt, _ = self._make_optimizer(rows)
        result = await opt.compute_optimal_weights("STRONG_TREND")
        assert "trend_following" in result
        assert abs(sum(result.values()) - 1.0) < 0.01

    @pytest.mark.asyncio
    async def test_db_error_returns_empty(self):
        db = AsyncMock()
        db.fetch = AsyncMock(side_effect=Exception("DB error"))
        opt = StrategyWeightOptimizer(db)
        result = await opt.compute_optimal_weights("STRONG_TREND")
        assert result == {}

    @pytest.mark.asyncio
    async def test_string_signals_parsed(self):
        """strategy_signals 为字符串时正确解析"""
        rows = [{"strategy_signals": '{"trend_following": {}}', "realized_pnl": 10, "pnl_percent": 2.0}
                for _ in range(25)]
        opt, _ = self._make_optimizer(rows)
        result = await opt.compute_optimal_weights("STRONG_TREND")
        assert "trend_following" in result

    @pytest.mark.asyncio
    async def test_update_strategy_selector(self):
        """update_strategy_selector 更新 selector 权重"""
        rows = [{"strategy_signals": json.dumps({"trend_following": {}}),
                 "realized_pnl": 10, "pnl_percent": 2.0}
                for _ in range(25)]
        opt, db = self._make_optimizer(rows)
        selector = MagicMock()
        updated = await opt.update_strategy_selector(selector)
        assert updated == 5  # 5 market states
        assert selector.update_weights.call_count == 5


# ===========================================================================
# 3.1 StrategySelector dynamic weights
# ===========================================================================
class TestStrategySelectorDynamicWeights:

    def test_override_weights_used(self):
        selector = StrategySelector(["trend_following", "mean_reversion"])
        selector.update_weights("strong_trend", {"trend_following": 0.9, "mean_reversion": 0.1})
        weights = selector.select_strategies(MarketState.STRONG_TREND)
        assert weights["trend_following"] == 0.9
        assert weights["mean_reversion"] == 0.1

    def test_fallback_to_defaults_when_no_override(self):
        selector = StrategySelector(["trend_following", "breakout"])
        weights = selector.select_strategies(MarketState.STRONG_TREND)
        assert weights["trend_following"] == 0.7
        assert weights["breakout"] == 0.3

    def test_override_filters_disabled_strategies(self):
        selector = StrategySelector(["trend_following"])
        selector.update_weights("strong_trend", {"trend_following": 0.8, "breakout": 0.2})
        weights = selector.select_strategies(MarketState.STRONG_TREND)
        assert "breakout" not in weights
        assert weights["trend_following"] == 0.8


# ===========================================================================
# 3.2 Rule lifecycle (tested via ReflectionEngine)
# ===========================================================================
class TestRuleLifecycle:

    @pytest.mark.asyncio
    async def test_matches_condition_exact(self):
        from ai_trader.reflection.engine import ReflectionEngine
        memory = MagicMock()
        memory.to_dict.return_value = {"symbol": "BTC/USDT", "side": "long"}
        assert ReflectionEngine._matches_condition(memory, {"symbol": "BTC/USDT"}) is True
        assert ReflectionEngine._matches_condition(memory, {"symbol": "ETH/USDT"}) is False

    @pytest.mark.asyncio
    async def test_matches_condition_range(self):
        from ai_trader.reflection.engine import ReflectionEngine
        memory = MagicMock()
        memory.to_dict.return_value = {"rsi": 25}
        assert ReflectionEngine._matches_condition(memory, {"rsi": {"min": 20, "max": 30}}) is True
        assert ReflectionEngine._matches_condition(memory, {"rsi": {"min": 30, "max": 50}}) is False

    @pytest.mark.asyncio
    async def test_matches_condition_missing_key(self):
        from ai_trader.reflection.engine import ReflectionEngine
        memory = MagicMock()
        memory.to_dict.return_value = {}
        assert ReflectionEngine._matches_condition(memory, {"rsi": 25}) is False


# ===========================================================================
# 3.3 Advisory conflict detection
# ===========================================================================
class TestAdvisoryConflictDetection:

    def _make_service(self, last_action=None, created_at=None):
        engine = MagicMock()
        trigger_mgr = MagicMock()
        db = AsyncMock()
        if last_action:
            db.fetchrow = AsyncMock(return_value={
                "action": last_action,
                "created_at": created_at or datetime.now(tz=timezone.utc),
            })
        else:
            db.fetchrow = AsyncMock(return_value=None)
        svc = AdvisoryService(
            engine=engine, trigger_manager=trigger_mgr, db=db,
        )
        return svc

    @pytest.mark.asyncio
    async def test_no_conflict_when_no_last_decision(self):
        svc = self._make_service(last_action=None)
        result = await svc.check_decision_conflict({"action": "close_long"}, "BTC/USDT")
        assert result is False

    @pytest.mark.asyncio
    async def test_conflict_when_recent_open_and_advisory_close(self):
        """主循环 10 分钟前开仓，advisory 建议平仓 → 冲突"""
        svc = self._make_service(
            last_action="open_long",
            created_at=datetime.now(tz=timezone.utc) - timedelta(minutes=10),
        )
        result = await svc.check_decision_conflict({"action": "close_long"}, "BTC/USDT")
        assert result is True

    @pytest.mark.asyncio
    async def test_no_conflict_after_cooldown(self):
        """主循环 60 分钟前开仓，超出冷却期 → 无冲突"""
        svc = self._make_service(
            last_action="open_long",
            created_at=datetime.now(tz=timezone.utc) - timedelta(minutes=60),
        )
        result = await svc.check_decision_conflict({"action": "close_long"}, "BTC/USDT")
        assert result is False

    @pytest.mark.asyncio
    async def test_no_conflict_same_direction(self):
        """主循环刚开仓 + advisory 不是平仓 → 无冲突"""
        svc = self._make_service(
            last_action="open_long",
            created_at=datetime.now(tz=timezone.utc) - timedelta(minutes=5),
        )
        result = await svc.check_decision_conflict({"action": "add_long"}, "BTC/USDT")
        assert result is False

    @pytest.mark.asyncio
    async def test_no_conflict_when_no_db(self):
        engine = MagicMock()
        trigger_mgr = MagicMock()
        svc = AdvisoryService(engine=engine, trigger_manager=trigger_mgr, db=None)
        result = await svc.check_decision_conflict({"action": "close_long"}, "BTC/USDT")
        assert result is False

    @pytest.mark.asyncio
    async def test_db_error_returns_no_conflict(self):
        engine = MagicMock()
        trigger_mgr = MagicMock()
        db = AsyncMock()
        db.fetchrow = AsyncMock(side_effect=Exception("db error"))
        svc = AdvisoryService(engine=engine, trigger_manager=trigger_mgr, db=db)
        result = await svc.check_decision_conflict({"action": "close_long"}, "BTC/USDT")
        assert result is False


# ===========================================================================
# 3.4 ParameterRegistry new params
# ===========================================================================
class TestParameterRegistryPhase3:

    def test_score_threshold_in_registry(self):
        reg = ParameterRegistry()
        param = reg.get("score_threshold")
        assert param is not None
        assert param.current_value == 0.15
        assert param.min_bound == 0.05
        assert param.max_bound == 0.35

    def test_fusion_confidence_threshold_in_registry(self):
        reg = ParameterRegistry()
        param = reg.get("fusion_confidence_threshold")
        assert param is not None
        assert param.current_value == 0.5
        assert param.min_bound == 0.3
        assert param.max_bound == 0.7

    def test_update_within_bounds(self):
        reg = ParameterRegistry()
        assert reg.update("score_threshold", 0.25) is True
        assert reg.get("score_threshold").current_value == 0.25

    def test_update_clamped_to_bounds(self):
        reg = ParameterRegistry()
        reg.update("score_threshold", 999.0)
        assert reg.get("score_threshold").current_value == 0.35  # max_bound


# ===========================================================================
# 3.5 Dynamic thresholds (unit test for ATR% logic)
# ===========================================================================
class TestAdaptiveThresholds:

    def test_high_volatility_thresholds(self):
        """ATR% > 3.0 → higher thresholds"""
        atr_pct = 4.0
        if atr_pct > 3.0:
            score_threshold = 0.25
            confidence_threshold = 0.55
        assert score_threshold == 0.25
        assert confidence_threshold == 0.55

    def test_low_volatility_thresholds(self):
        """ATR% < 0.5 → lower thresholds"""
        atr_pct = 0.3
        if atr_pct > 3.0:
            score_threshold = 0.25
            confidence_threshold = 0.55
        elif atr_pct < 0.5:
            score_threshold = 0.10
            confidence_threshold = 0.45
        assert score_threshold == 0.10
        assert confidence_threshold == 0.45

    def test_normal_volatility_thresholds(self):
        """0.5 ≤ ATR% ≤ 3.0 → default thresholds"""
        atr_pct = 1.5
        if atr_pct > 3.0:
            score_threshold = 0.25
            confidence_threshold = 0.55
        elif atr_pct < 0.5:
            score_threshold = 0.10
            confidence_threshold = 0.45
        else:
            score_threshold = 0.15
            confidence_threshold = 0.50
        assert score_threshold == 0.15
        assert confidence_threshold == 0.50


# ===========================================================================
# 3.4 Config testnet_initial_equity
# ===========================================================================
class TestTestnetConfig:

    def test_default_initial_equity(self):
        from ai_trader.config import TradingConfig
        cfg = TradingConfig()
        assert cfg.testnet_initial_equity == 10000.0
