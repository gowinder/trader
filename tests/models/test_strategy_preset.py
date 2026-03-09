"""策略预设模型单元测试"""

import pytest
from pydantic import ValidationError

from ai_trader.models.strategy_preset import StrategyPreset, StrategyPresetConfig
from ai_trader.strategies.presets import (
    DEFAULT_PRESET_NAME,
    SYSTEM_PRESETS,
    get_all_system_defaults,
    get_preset_by_name,
)


def _make_config(**overrides) -> StrategyPresetConfig:
    defaults = dict(
        enabled_strategies=["trend_following"],
        strategy_weights={"trend_following": 1.0},
        ai_weight=0.5,
        quant_weight=0.5,
        timeframes=["1h"],
        min_trade_interval_seconds=300,
        stop_loss_atr_multiplier=2.0,
        take_profit_atr_multiplier=4.0,
        max_position_pct=20.0,
    )
    defaults.update(overrides)
    return StrategyPresetConfig(**defaults)


# ── StrategyPresetConfig ─────────────────────────────────────────────


class TestStrategyPresetConfig:
    def test_strategy_preset_config_valid(self):
        c = _make_config()
        assert c.ai_weight == 0.5
        assert c.quant_weight == 0.5
        assert c.sentiment_weight == 0
        assert c.enable_pyramid is False
        assert c.max_pyramid_times == 0
        assert c.enable_sentiment is False
        assert c.min_profit_threshold == 0
        assert c.use_market_order_only is False

    def test_strategy_preset_config_ai_weight_boundary(self):
        c0 = _make_config(ai_weight=0)
        assert c0.ai_weight == 0
        c1 = _make_config(ai_weight=1)
        assert c1.ai_weight == 1

    def test_strategy_preset_config_ai_weight_below_0(self):
        with pytest.raises(ValidationError):
            _make_config(ai_weight=-0.1)

    def test_strategy_preset_config_ai_weight_above_1(self):
        with pytest.raises(ValidationError):
            _make_config(ai_weight=1.1)

    def test_strategy_preset_config_quant_weight_invalid(self):
        with pytest.raises(ValidationError):
            _make_config(quant_weight=-1)

    def test_strategy_preset_config_sentiment_weight_invalid(self):
        with pytest.raises(ValidationError):
            _make_config(sentiment_weight=2.0)

    def test_strategy_preset_config_min_trade_interval_below_60(self):
        with pytest.raises(ValidationError):
            _make_config(min_trade_interval_seconds=59)

    def test_strategy_preset_config_min_trade_interval_exactly_60(self):
        c = _make_config(min_trade_interval_seconds=60)
        assert c.min_trade_interval_seconds == 60

    def test_strategy_preset_config_stop_loss_atr_below_05(self):
        with pytest.raises(ValidationError):
            _make_config(stop_loss_atr_multiplier=0.4)

    def test_strategy_preset_config_take_profit_atr_below_05(self):
        with pytest.raises(ValidationError):
            _make_config(take_profit_atr_multiplier=0.49)

    def test_strategy_preset_config_max_position_pct_below_1(self):
        with pytest.raises(ValidationError):
            _make_config(max_position_pct=0.5)

    def test_strategy_preset_config_max_position_pct_above_100(self):
        with pytest.raises(ValidationError):
            _make_config(max_position_pct=101)

    def test_strategy_preset_config_max_pyramid_times_negative(self):
        with pytest.raises(ValidationError):
            _make_config(max_pyramid_times=-1)

    def test_strategy_preset_config_min_profit_threshold_negative(self):
        with pytest.raises(ValidationError):
            _make_config(min_profit_threshold=-0.01)


# ── StrategyPreset ───────────────────────────────────────────────────


class TestStrategyPreset:
    def test_strategy_preset_defaults(self):
        p = StrategyPreset(
            name="test", display_name="Test", description="desc",
            category="cat", risk_level="low", config=_make_config(),
        )
        assert p.is_system is True
        assert p.id is None

    def test_strategy_preset_is_system_false(self):
        p = StrategyPreset(
            name="custom", display_name="Custom", description="d",
            category="c", risk_level="high", config=_make_config(),
            is_system=False,
        )
        assert p.is_system is False


# ── presets.py 函数 ──────────────────────────────────────────────────


class TestPresetsModule:
    def test_system_presets_count(self):
        assert len(SYSTEM_PRESETS) == 7

    def test_get_preset_by_name_exists(self):
        p = get_preset_by_name("steady_trend")
        assert p is not None
        assert p.name == "steady_trend"

    def test_get_preset_by_name_not_exists(self):
        assert get_preset_by_name("nonexistent") is None

    def test_get_all_system_defaults(self):
        defaults = get_all_system_defaults()
        assert isinstance(defaults, dict)
        assert len(defaults) == 7
        assert "steady_trend" in defaults
        assert "ai_weight" in defaults["steady_trend"]

    def test_default_preset_name(self):
        assert DEFAULT_PRESET_NAME == "steady_trend"

    def test_all_presets_are_system(self):
        for p in SYSTEM_PRESETS:
            assert p.is_system is True
