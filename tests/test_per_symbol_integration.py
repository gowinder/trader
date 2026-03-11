"""Integration tests for per-symbol strategy configuration."""
import pytest
from ai_trader.models.symbol_strategy import SymbolStrategyConfig, merge_preset_with_overrides
from ai_trader.models.strategy_preset import StrategyPresetConfig
from ai_trader.strategies.strategy_selector import StrategySelector
from ai_trader.strategies.presets import SYSTEM_PRESETS, get_preset_by_name


class TestPerSymbolIntegration:
    """Test that different symbols can use different strategies."""

    def test_btc_uses_trend_following(self):
        preset = get_preset_by_name("steady_trend")
        cfg = SymbolStrategyConfig(
            symbol="BTC/USDT:USDT",
            preset_name="steady_trend",
            preset_config=preset.config,
            config_overrides={},
        )
        selector = StrategySelector(cfg.merged_config.enabled_strategies)
        assert "trend_following" in selector.strategies

    def test_doge_uses_scalping(self):
        preset = get_preset_by_name("mild_scalping")
        cfg = SymbolStrategyConfig(
            symbol="DOGE/USDT:USDT",
            preset_name="mild_scalping",
            preset_config=preset.config,
            config_overrides={},
        )
        selector = StrategySelector(cfg.merged_config.enabled_strategies)
        assert "mean_reversion" in selector.strategies
        assert "trend_following" in selector.strategies

    def test_override_weights(self):
        preset = get_preset_by_name("steady_trend")
        cfg = SymbolStrategyConfig(
            symbol="ETH/USDT:USDT",
            preset_name="steady_trend",
            preset_config=preset.config,
            config_overrides={"ai_weight": 0.8, "quant_weight": 0.2},
        )
        merged = cfg.merged_config
        assert merged.ai_weight == 0.8
        assert merged.quant_weight == 0.2
        # Unchanged params
        assert merged.stop_loss_atr_multiplier == preset.config.stop_loss_atr_multiplier

    def test_different_selectors_independent(self):
        """Two symbols should have independent StrategySelector instances."""
        btc_preset = get_preset_by_name("steady_trend")
        doge_preset = get_preset_by_name("aggressive_scalping")

        btc_selector = StrategySelector(btc_preset.config.enabled_strategies)
        doge_selector = StrategySelector(doge_preset.config.enabled_strategies)

        assert set(btc_selector.strategies.keys()) != set(doge_selector.strategies.keys()) or \
               len(btc_selector.strategies) != len(doge_selector.strategies)

    def test_all_presets_produce_valid_selector(self):
        """Every system preset should produce a working StrategySelector."""
        for preset in SYSTEM_PRESETS:
            selector = StrategySelector(preset.config.enabled_strategies)
            assert len(selector.strategies) > 0, f"Preset {preset.name} has no strategies"
