"""Per-symbol strategy configuration model."""

from dataclasses import dataclass, field

from .strategy_preset import StrategyPresetConfig


def merge_preset_with_overrides(
    preset_config: StrategyPresetConfig,
    overrides: dict,
) -> StrategyPresetConfig:
    """Merge preset config with per-symbol overrides.

    Only known fields from StrategyPresetConfig are applied.
    Unknown keys in overrides are ignored.
    """
    base = preset_config.model_dump()
    valid_fields = set(base.keys())
    filtered = {k: v for k, v in overrides.items() if k in valid_fields}
    base.update(filtered)
    return StrategyPresetConfig(**base)


@dataclass
class SymbolStrategyConfig:
    """Per-symbol strategy configuration."""

    symbol: str
    preset_name: str
    preset_config: StrategyPresetConfig
    config_overrides: dict = field(default_factory=dict)

    @property
    def merged_config(self) -> StrategyPresetConfig:
        return merge_preset_with_overrides(self.preset_config, self.config_overrides)
