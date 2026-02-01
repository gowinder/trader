# tests/optimization/test_parameter_registry.py
import pytest
from ai_trader.optimization.parameter_registry import (
    AdjustableParameter,
    ParameterRegistry,
)


class TestAdjustableParameter:
    def test_create_parameter(self):
        param = AdjustableParameter(
            name="confidence_threshold",
            current_value=60.0,
            min_bound=40.0,
            max_bound=90.0,
            step=5.0,
            category="decision",
        )
        assert param.current_value == 60.0
        assert param.is_within_bounds(60.0)

    def test_bound_validation(self):
        param = AdjustableParameter(
            name="max_leverage",
            current_value=5.0,
            min_bound=1.0,
            max_bound=10.0,
            step=1.0,
            category="position",
        )
        assert param.is_within_bounds(5.0)
        assert not param.is_within_bounds(15.0)
        assert not param.is_within_bounds(0.5)

    def test_clamp_value(self):
        param = AdjustableParameter(
            name="stop_loss_percent",
            current_value=5.0,
            min_bound=2.0,
            max_bound=10.0,
            step=0.5,
            category="risk",
        )
        assert param.clamp(1.0) == 2.0
        assert param.clamp(15.0) == 10.0
        assert param.clamp(5.0) == 5.0


class TestParameterRegistry:
    def test_get_parameter(self):
        registry = ParameterRegistry()
        param = registry.get("confidence_threshold")
        assert param is not None
        assert param.category == "decision"

    def test_update_parameter(self):
        registry = ParameterRegistry()
        old_value = registry.get("confidence_threshold").current_value
        registry.update("confidence_threshold", 70.0)
        assert registry.get("confidence_threshold").current_value == 70.0

    def test_update_with_boundary_enforcement(self):
        registry = ParameterRegistry()
        registry.update("max_leverage", 20.0)  # 超出边界
        assert registry.get("max_leverage").current_value == 10.0  # 被限制

    def test_get_all_by_category(self):
        registry = ParameterRegistry()
        risk_params = registry.get_by_category("risk")
        assert len(risk_params) >= 2  # stop_loss, take_profit
