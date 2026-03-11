import pytest
from ai_trader.models.symbol_strategy import SymbolStrategyConfig, merge_preset_with_overrides
from ai_trader.models.strategy_preset import StrategyPresetConfig


def _make_preset(**kwargs) -> StrategyPresetConfig:
    """Helper to create a StrategyPresetConfig with sensible defaults."""
    defaults = dict(
        enabled_strategies=["trend_following"],
        strategy_weights={"trend_following": 1.0},
        ai_weight=0.6,
        quant_weight=0.4,
        timeframes=["1h"],
        min_trade_interval_seconds=300,
        stop_loss_atr_multiplier=1.5,
        take_profit_atr_multiplier=2.0,
        max_position_pct=10,
    )
    defaults.update(kwargs)
    return StrategyPresetConfig(**defaults)


class TestMergePresetWithOverrides:
    def test_no_overrides_returns_preset_config(self):
        preset_config = _make_preset(ai_weight=0.6, quant_weight=0.4)
        result = merge_preset_with_overrides(preset_config, {})
        assert result.ai_weight == 0.6
        assert result.quant_weight == 0.4

    def test_overrides_replace_preset_values(self):
        preset_config = _make_preset(ai_weight=0.6, quant_weight=0.4)
        overrides = {"ai_weight": 0.8, "stop_loss_atr_multiplier": 2.0}
        result = merge_preset_with_overrides(preset_config, overrides)
        assert result.ai_weight == 0.8
        assert result.stop_loss_atr_multiplier == 2.0
        assert result.quant_weight == 0.4  # unchanged

    def test_invalid_override_key_ignored(self):
        preset_config = _make_preset(ai_weight=0.6, quant_weight=0.4)
        overrides = {"nonexistent_field": 999}
        result = merge_preset_with_overrides(preset_config, overrides)
        assert result.ai_weight == 0.6


class TestSymbolStrategyConfig:
    def test_create(self):
        preset_config = _make_preset(ai_weight=0.6, quant_weight=0.4)
        cfg = SymbolStrategyConfig(
            symbol="BTC/USDT:USDT",
            preset_name="steady_trend",
            preset_config=preset_config,
            config_overrides={"ai_weight": 0.7},
        )
        assert cfg.symbol == "BTC/USDT:USDT"
        assert cfg.merged_config.ai_weight == 0.7
        assert cfg.merged_config.quant_weight == 0.4
