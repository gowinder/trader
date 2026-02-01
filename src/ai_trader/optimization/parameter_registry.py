"""参数注册表 - 管理所有可调参数及其硬边界"""

from dataclasses import dataclass, field
from typing import Optional
from copy import deepcopy


@dataclass
class AdjustableParameter:
    """可调参数定义"""

    name: str
    current_value: float
    min_bound: float
    max_bound: float
    step: float
    category: str  # decision, position, risk, timing
    description: str = ""

    def is_within_bounds(self, value: float) -> bool:
        """检查值是否在边界内"""
        return self.min_bound <= value <= self.max_bound

    def clamp(self, value: float) -> float:
        """将值限制在边界内"""
        return max(self.min_bound, min(self.max_bound, value))


# 默认参数配置
DEFAULT_PARAMETERS = {
    # 决策偏好类
    "confidence_threshold": AdjustableParameter(
        name="confidence_threshold",
        current_value=60.0,
        min_bound=40.0,
        max_bound=90.0,
        step=5.0,
        category="decision",
        description="开仓置信度阈值",
    ),
    "hold_bias": AdjustableParameter(
        name="hold_bias",
        current_value=0.0,
        min_bound=-0.3,
        max_bound=0.3,
        step=0.05,
        category="decision",
        description="HOLD 倾向权重",
    ),
    "quant_ai_weight_trend": AdjustableParameter(
        name="quant_ai_weight_trend",
        current_value=0.7,
        min_bound=0.3,
        max_bound=0.9,
        step=0.1,
        category="decision",
        description="趋势市量化权重",
    ),
    "quant_ai_weight_ranging": AdjustableParameter(
        name="quant_ai_weight_ranging",
        current_value=0.4,
        min_bound=0.2,
        max_bound=0.7,
        step=0.1,
        category="decision",
        description="震荡市量化权重",
    ),
    # 仓位控制类
    "max_position_percent": AdjustableParameter(
        name="max_position_percent",
        current_value=20.0,
        min_bound=5.0,
        max_bound=30.0,
        step=5.0,
        category="position",
        description="最大仓位百分比",
    ),
    "max_leverage": AdjustableParameter(
        name="max_leverage",
        current_value=5.0,
        min_bound=1.0,
        max_bound=10.0,
        step=1.0,
        category="position",
        description="最大杠杆",
    ),
    # 风险控制类
    "stop_loss_percent": AdjustableParameter(
        name="stop_loss_percent",
        current_value=5.0,
        min_bound=2.0,
        max_bound=10.0,
        step=0.5,
        category="risk",
        description="止损百分比",
    ),
    "take_profit_percent": AdjustableParameter(
        name="take_profit_percent",
        current_value=10.0,
        min_bound=5.0,
        max_bound=25.0,
        step=1.0,
        category="risk",
        description="止盈百分比",
    ),
}


class ParameterRegistry:
    """参数注册表"""

    def __init__(self, parameters: Optional[dict[str, AdjustableParameter]] = None):
        """初始化参数注册表"""
        self._parameters = deepcopy(parameters or DEFAULT_PARAMETERS)
        self._history: list[dict] = []

    def get(self, name: str) -> Optional[AdjustableParameter]:
        """获取参数"""
        return self._parameters.get(name)

    def update(self, name: str, new_value: float, reason: str = "") -> bool:
        """更新参数值（自动限制在边界内）"""
        param = self._parameters.get(name)
        if not param:
            return False

        old_value = param.current_value
        param.current_value = param.clamp(new_value)

        # 记录历史
        self._history.append({
            "name": name,
            "old_value": old_value,
            "new_value": param.current_value,
            "reason": reason,
        })
        return True

    def get_by_category(self, category: str) -> list[AdjustableParameter]:
        """按类别获取参数"""
        return [p for p in self._parameters.values() if p.category == category]

    def get_all(self) -> dict[str, AdjustableParameter]:
        """获取所有参数"""
        return self._parameters.copy()

    def to_dict(self) -> dict[str, float]:
        """导出为简单字典"""
        return {name: p.current_value for name, p in self._parameters.items()}

    def get_history(self) -> list[dict]:
        """获取变更历史"""
        return self._history.copy()
