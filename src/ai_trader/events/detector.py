"""EventDetector — 市场事件检测主编排器。

整合所有子检测器、冷却管理、策略过滤，提供统一的 scan() 接口。
"""

from __future__ import annotations

from typing import Optional

from ..utils.logger import logger
from .config import DEFAULT_EVENT_TRIGGER_CONFIG, STRATEGY_EVENT_DEFAULTS
from .cooldown import CooldownManager
from .detectors import (
    BollingerBreakDetector,
    MACDCrossDetector,
    MarketStateChangeDetector,
    PositionPnLDetector,
    PriceSurgeDetector,
    RSIExtremeDetector,
    VolumeSpikeDetector,
)
from .models import TriggerEvent


class EventDetector:
    """市场事件检测主类 — 整合检测器 + 冷却 + 策略过滤。"""

    def __init__(self, event_config: dict, enabled_strategies: list[str]) -> None:
        self._config = event_config
        self._enabled_strategies = list(enabled_strategies)
        self._init_detectors()
        self._init_cooldown()

    # ── 初始化 ────────────────────────────────────────────────────────

    def _init_detectors(self) -> None:
        events_cfg = self._config.get("events", {})

        ps_cfg = events_cfg.get("price_surge", {})
        self._price_surge = PriceSurgeDetector(
            atr_multiplier=ps_cfg.get("atr_multiplier", 1.5),
            lookback_seconds=ps_cfg.get("lookback_seconds", 300),
        )

        vs_cfg = events_cfg.get("volume_spike", {})
        self._volume_spike = VolumeSpikeDetector(
            volume_multiplier=vs_cfg.get("volume_multiplier", 2.5),
        )

        rsi_cfg = events_cfg.get("rsi_extreme", {})
        self._rsi_extreme = RSIExtremeDetector(
            upper_threshold=rsi_cfg.get("upper_threshold", 75),
            lower_threshold=rsi_cfg.get("lower_threshold", 25),
        )

        self._macd_cross = MACDCrossDetector()

        self._bollinger_break = BollingerBreakDetector()

        self._market_state_change = MarketStateChangeDetector()

        pnl_cfg = events_cfg.get("position_pnl", {})
        self._position_pnl = PositionPnLDetector(
            profit_threshold=pnl_cfg.get("profit_threshold_percent", 3.0),
            loss_threshold=pnl_cfg.get("loss_threshold_percent", -2.0),
        )

        # 检测器映射: event_type -> (detector, is_standard)
        # is_standard=True 表示使用 .check() 接口
        # is_standard=False 表示有特殊接口 (MarketStateChangeDetector)
        self._detector_map: dict[str, tuple] = {
            "price_surge": (self._price_surge, True),
            "volume_spike": (self._volume_spike, True),
            "rsi_extreme": (self._rsi_extreme, True),
            "macd_cross": (self._macd_cross, True),
            "bollinger_break": (self._bollinger_break, True),
            "market_state_change": (self._market_state_change, False),
            "position_pnl": (self._position_pnl, True),
        }

    def _init_cooldown(self) -> None:
        self._cooldown = CooldownManager(
            global_cooldown=self._config.get("global_cooldown_seconds", 300),
            per_event_cooldown=self._config.get("per_event_cooldown_seconds", 600),
        )

    # ── 热更新 ────────────────────────────────────────────────────────

    def update_config(self, event_config: dict, enabled_strategies: list[str]) -> None:
        """热更新配置，重建检测器和冷却管理器。"""
        self._config = event_config
        self._enabled_strategies = list(enabled_strategies)
        self._init_detectors()
        self._init_cooldown()
        logger.info("EventDetector 配置已热更新")

    # ── 策略过滤 ──────────────────────────────────────────────────────

    def _get_active_event_types(self) -> set[str]:
        """根据已启用策略，返回需要检测的事件类型并集。"""
        active: set[str] = set()
        for strategy in self._enabled_strategies:
            events = STRATEGY_EVENT_DEFAULTS.get(strategy, [])
            active.update(events)
        return active

    # ── 核心扫描 ──────────────────────────────────────────────────────

    def scan(
        self,
        market_data,
        position,
        market_state: str | None,
    ) -> list[TriggerEvent]:
        """扫描所有检测器，返回触发的事件列表。

        流程:
        1. 检查全局启用状态
        2. 获取当前策略需要的事件类型
        3. 逐检测器: 类型是否活跃 -> 是否在配置中启用 -> 冷却检查 -> 执行检测
        4. 为触发的事件记录冷却
        """
        # 1. 全局开关
        if not self._config.get("enabled", True):
            return []

        # 2. 活跃事件类型
        active_types = self._get_active_event_types()
        if not active_types:
            return []

        events_cfg = self._config.get("events", {})
        triggered: list[TriggerEvent] = []

        # 3. 遍历检测器
        for event_type, (detector, is_standard) in self._detector_map.items():
            # 3a. 策略过滤
            if event_type not in active_types:
                continue

            # 3b. 配置启用检查
            evt_cfg = events_cfg.get(event_type, {})
            if not evt_cfg.get("enabled", True):
                continue

            # 3c. 冷却检查
            if not self._cooldown.can_trigger(event_type):
                continue

            # 3d. 执行检测
            event: Optional[TriggerEvent] = None
            try:
                if is_standard:
                    event = detector.check(market_data, market_data.indicators, position)
                else:
                    # MarketStateChangeDetector 特殊接口
                    if market_state is not None:
                        event = detector.check_state_change(market_state)
            except Exception:
                logger.exception(f"检测器 {event_type} 执行异常")
                continue

            if event is not None:
                triggered.append(event)
                self._cooldown.record_trigger(event_type)

        if triggered:
            logger.info(
                f"事件检测完成: 触发 {len(triggered)} 个事件 "
                f"[{', '.join(e.event_type for e in triggered)}]"
            )

        return triggered


def format_trigger_context(
    events: list[TriggerEvent],
    active_strategies: list[str],
    strategy_weights: dict | None = None,
) -> str:
    """将触发事件格式化为 LLM prompt 文本。"""
    lines: list[str] = []
    lines.append("⚡ 本次分析由市场事件触发（非定时调用），请重点关注以下信号：\n")

    for idx, event in enumerate(events, 1):
        lines.append(f"[{idx}] {event.format_for_prompt()}\n")

    # 策略信息
    strategy_parts: list[str] = []
    for s in active_strategies:
        if strategy_weights and s in strategy_weights:
            strategy_parts.append(f"{s}(权重:{strategy_weights[s]})")
        else:
            strategy_parts.append(s)
    lines.append(f"当前活跃策略: {', '.join(strategy_parts)}")

    lines.append("请结合以上触发事件，判断是否需要立即行动。")

    return "\n".join(lines)
