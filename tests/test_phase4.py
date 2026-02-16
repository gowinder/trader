"""Phase 4 tests: backtest validation, performance tracking, decision quality scoring."""

import json
import math
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_trader.models.decision import TradingDecision
from ai_trader.models.market import MarketData


# ===========================================================================
# 4.1 Backtest before apply (orchestrator)
# ===========================================================================
class TestBacktestBeforeApply:

    def _make_orchestrator(self, rows=None, db_error=False):
        from ai_trader.optimization.orchestrator import OptimizationOrchestrator
        from ai_trader.optimization.parameter_registry import ParameterRegistry
        from ai_trader.optimization.shadow_runner import ShadowRunner

        db = AsyncMock()
        if db_error:
            db.fetch = AsyncMock(side_effect=Exception("DB error"))
        elif rows is not None:
            db.fetch = AsyncMock(return_value=rows)
        else:
            db.fetch = AsyncMock(return_value=[])

        shadow = MagicMock(spec=ShadowRunner)
        registry = ParameterRegistry()
        orch = OptimizationOrchestrator(db, shadow, registry)
        return orch

    @pytest.mark.asyncio
    async def test_no_db_returns_true(self):
        from ai_trader.optimization.orchestrator import OptimizationOrchestrator
        from ai_trader.optimization.parameter_registry import ParameterRegistry
        from ai_trader.optimization.shadow_runner import ShadowRunner

        shadow = MagicMock(spec=ShadowRunner)
        registry = ParameterRegistry()
        orch = OptimizationOrchestrator(None, shadow, registry)
        result = await orch._backtest_before_apply({"stop_loss_percent": 5.0})
        assert result is True

    @pytest.mark.asyncio
    async def test_insufficient_samples_returns_true(self):
        rows = [{"pnl_percent": 2.0} for _ in range(5)]
        orch = self._make_orchestrator(rows)
        result = await orch._backtest_before_apply({"stop_loss_percent": 5.0})
        assert result is True

    @pytest.mark.asyncio
    async def test_db_error_returns_true(self):
        orch = self._make_orchestrator(db_error=True)
        result = await orch._backtest_before_apply({"stop_loss_percent": 5.0})
        assert result is True

    @pytest.mark.asyncio
    async def test_good_trades_pass(self):
        """大部分盈利交易 → 通过"""
        rows = []
        for i in range(20):
            rows.append({"pnl_percent": 3.0 if i % 3 != 0 else -1.0})
        orch = self._make_orchestrator(rows)
        result = await orch._backtest_before_apply(
            {"stop_loss_percent": 5.0, "take_profit_percent": 10.0}
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_bad_trades_fail(self):
        """大部分亏损交易 → 不通过"""
        rows = [{"pnl_percent": -4.0} for _ in range(20)]
        orch = self._make_orchestrator(rows)
        result = await orch._backtest_before_apply(
            {"stop_loss_percent": 5.0, "take_profit_percent": 10.0}
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_sl_tp_clamping(self):
        """pnl_pct 被 SL/TP 截断"""
        rows = [{"pnl_percent": 20.0} for _ in range(15)]
        orch = self._make_orchestrator(rows)
        result = await orch._backtest_before_apply(
            {"stop_loss_percent": 5.0, "take_profit_percent": 8.0}
        )
        # 20% clamped to 8%, all wins, avg_pnl > 0, no drawdown → pass
        assert result is True

    @pytest.mark.asyncio
    async def test_evaluate_and_apply_rejects_on_backtest_fail(self):
        """影子运行通过但回测验证不达标 → 拒绝参数切换"""
        orch = self._make_orchestrator(
            rows=[{"pnl_percent": -4.0} for _ in range(20)]
        )
        orch.shadow_runner.is_running = True
        orch.shadow_runner.evaluate.return_value = {"should_switch": True}
        orch.shadow_runner._candidate_params = {"stop_loss_percent": 5.0}
        orch.shadow_runner.complete = AsyncMock()

        result = await orch.evaluate_and_apply()
        assert result is None
        orch.shadow_runner.complete.assert_called_once_with(
            switched=False, conclusion="影子运行通过但回测验证不达标"
        )


# ===========================================================================
# 4.2 PerformanceTracker
# ===========================================================================
class TestPerformanceTracker:

    def _make_tracker(self, rows=None, report_row=None, db_error=False):
        from ai_trader.monitoring.performance_tracker import PerformanceTracker

        db = AsyncMock()
        if db_error:
            db.fetch = AsyncMock(side_effect=Exception("DB error"))
        elif rows is not None:
            db.fetch = AsyncMock(return_value=rows)
        else:
            db.fetch = AsyncMock(return_value=[])

        db.fetchrow = AsyncMock(return_value=report_row)
        db.execute = AsyncMock()
        return PerformanceTracker(db), db

    @pytest.mark.asyncio
    async def test_empty_report_on_no_trades(self):
        tracker, _ = self._make_tracker(rows=[])
        report = await tracker.compute_weekly_report()
        assert report["total_trades"] == 0
        assert report["win_rate"] == 0

    @pytest.mark.asyncio
    async def test_db_error_returns_empty(self):
        tracker, _ = self._make_tracker(db_error=True)
        report = await tracker.compute_weekly_report()
        assert report["total_trades"] == 0

    @pytest.mark.asyncio
    async def test_weekly_report_calculation(self):
        rows = [
            {"pnl_percent": 3.0},
            {"pnl_percent": -1.0},
            {"pnl_percent": 5.0},
            {"pnl_percent": 2.0},
            {"pnl_percent": -2.0},
        ]
        tracker, _ = self._make_tracker(rows)
        report = await tracker.compute_weekly_report()
        assert report["total_trades"] == 5
        assert report["win_rate"] == 0.6  # 3 wins / 5
        assert abs(report["avg_pnl"] - 1.4) < 0.01  # (3-1+5+2-2)/5
        assert report["sharpe_ratio"] != 0

    @pytest.mark.asyncio
    async def test_max_drawdown_calculation(self):
        rows = [
            {"pnl_percent": 5.0},
            {"pnl_percent": -3.0},
            {"pnl_percent": -4.0},
            {"pnl_percent": 2.0},
        ]
        tracker, _ = self._make_tracker(rows)
        report = await tracker.compute_weekly_report()
        # equity: 5, 2, -2, 0; peak: 5, 5, 5, 5; dd: 0, 3, 7, 5
        assert report["max_drawdown_pct"] == 7.0

    @pytest.mark.asyncio
    async def test_detect_degradation_win_rate_drop(self):
        rows = [
            {"pnl_percent": -1.0},
            {"pnl_percent": -2.0},
            {"pnl_percent": -1.5},
            {"pnl_percent": 0.5},
            {"pnl_percent": -0.5},
        ]
        tracker, _ = self._make_tracker(
            rows=rows,
            report_row={
                "raw_data": json.dumps({
                    "win_rate": 0.6,
                    "avg_pnl": 1.5,
                    "total_trades": 10,
                })
            },
        )
        warning = await tracker.detect_degradation()
        assert warning is not None
        assert "胜率下降" in warning

    @pytest.mark.asyncio
    async def test_no_degradation_when_no_previous(self):
        rows = [{"pnl_percent": 2.0} for _ in range(10)]
        tracker, _ = self._make_tracker(rows=rows, report_row=None)
        warning = await tracker.detect_degradation()
        assert warning is None

    @pytest.mark.asyncio
    async def test_save_report(self):
        tracker, db = self._make_tracker()
        report = {
            "period": "weekly",
            "total_trades": 10,
            "win_rate": 0.6,
            "avg_pnl": 1.5,
            "total_pnl": 15.0,
            "sharpe_ratio": 1.2,
            "max_drawdown_pct": 5.0,
        }
        await tracker.save_report(report)
        db.execute.assert_called_once()


# ===========================================================================
# 4.3 Decision quality scoring
# ===========================================================================
class TestDecisionQualityScoring:

    def _make_service(self):
        from ai_trader.persistence.service import DecisionPersistenceService

        db = AsyncMock()
        return DecisionPersistenceService(db)

    def _make_decision(self, **kwargs):
        defaults = {
            "action": "open_long",
            "confidence": 75.0,
            "entry_price": 50000.0,
            "stop_loss_price": 47500.0,  # 5% below
            "take_profit_price": 55000.0,  # 10% above
        }
        defaults.update(kwargs)
        return TradingDecision(**defaults)

    def _make_market_data(self, current_price=50000.0):
        md = MagicMock(spec=MarketData)
        md.current_price = current_price
        return md

    def test_hold_gets_perfect_score(self):
        svc = self._make_service()
        decision = self._make_decision(action="hold")
        md = self._make_market_data()
        result = svc._compute_decision_quality(decision, md)
        assert result["quality_score"] == 100
        assert result["issues"] == []

    def test_good_decision_high_score(self):
        svc = self._make_service()
        decision = self._make_decision()
        md = self._make_market_data(50000.0)
        result = svc._compute_decision_quality(decision, md)
        assert result["quality_score"] == 100
        assert result["issues"] == []

    def test_large_price_deviation_penalized(self):
        svc = self._make_service()
        decision = self._make_decision(entry_price=54000.0)  # 8% off
        md = self._make_market_data(50000.0)
        result = svc._compute_decision_quality(decision, md)
        assert result["quality_score"] < 100
        assert any("entry_price偏差过大" in i for i in result["issues"])

    def test_extreme_stop_loss_penalized(self):
        svc = self._make_service()
        # SL distance = 20% (too far)
        decision = self._make_decision(
            entry_price=50000.0,
            stop_loss_price=40000.0,
        )
        md = self._make_market_data(50000.0)
        result = svc._compute_decision_quality(decision, md)
        assert any("止损距离异常" in i for i in result["issues"])

    def test_tiny_stop_loss_penalized(self):
        svc = self._make_service()
        # SL distance = 0.1% (too close)
        decision = self._make_decision(
            entry_price=50000.0,
            stop_loss_price=49950.0,
        )
        md = self._make_market_data(50000.0)
        result = svc._compute_decision_quality(decision, md)
        assert any("止损距离异常" in i for i in result["issues"])

    def test_bad_risk_reward_penalized(self):
        svc = self._make_service()
        # Risk: 50000-47500=2500, Reward: 51000-50000=1000, RR=0.4
        decision = self._make_decision(
            entry_price=50000.0,
            stop_loss_price=47500.0,
            take_profit_price=51000.0,
        )
        md = self._make_market_data(50000.0)
        result = svc._compute_decision_quality(decision, md)
        assert any("风险回报比不足" in i for i in result["issues"])

    def test_multiple_issues_compound(self):
        svc = self._make_service()
        # Price deviation + bad SL + bad RR = 3 issues → score = 40
        decision = self._make_decision(
            entry_price=54000.0,  # 8% off from 50000
            stop_loss_price=44000.0,  # 18.5% from entry (too far)
            take_profit_price=55000.0,  # reward < risk
        )
        md = self._make_market_data(50000.0)
        result = svc._compute_decision_quality(decision, md)
        assert result["quality_score"] == 40
        assert len(result["issues"]) == 3

    def test_no_prices_no_penalty(self):
        svc = self._make_service()
        decision = self._make_decision(
            entry_price=None,
            stop_loss_price=None,
            take_profit_price=None,
        )
        md = self._make_market_data(50000.0)
        result = svc._compute_decision_quality(decision, md)
        assert result["quality_score"] == 100
        assert result["issues"] == []

    def test_score_never_below_zero(self):
        svc = self._make_service()
        # 所有检查都失败
        decision = self._make_decision(
            entry_price=60000.0,  # 20% off
            stop_loss_price=10000.0,  # 83% from entry
            take_profit_price=61000.0,  # reward/risk < 1
        )
        md = self._make_market_data(50000.0)
        result = svc._compute_decision_quality(decision, md)
        assert result["quality_score"] >= 0
