import pytest
from unittest.mock import AsyncMock, MagicMock
from ai_trader.persistence.strategy_service import StrategyPresetService


class TestSymbolStrategyService:
    @pytest.fixture
    def service(self):
        svc = StrategyPresetService.__new__(StrategyPresetService)
        svc.db = AsyncMock()
        return svc

    @pytest.mark.asyncio
    async def test_get_all_symbol_strategies_empty(self, service):
        service.db.fetch.return_value = []

        result = await service.get_all_symbol_strategies()
        assert result == []

    @pytest.mark.asyncio
    async def test_get_all_symbol_strategies_returns_rows(self, service):
        row = {
            "symbol": "BTC/USDT:USDT",
            "preset_name": "steady_trend",
            "config_json": {
                "enabled_strategies": ["trend_following"],
                "ai_weight": 0.6,
                "quant_weight": 0.4,
                "strategy_weights": {"trend_following": 1.0},
                "timeframes": ["1h", "4h"],
                "min_trade_interval_seconds": 21600,
                "stop_loss_atr_multiplier": 3.0,
                "take_profit_atr_multiplier": 8.0,
                "max_position_pct": 15.0,
                "enable_pyramid": False,
                "max_pyramid_times": 0,
                "enable_sentiment": True,
                "min_profit_threshold": 0,
                "use_market_order_only": False,
                "sentiment_weight": 0.2,
            },
            "config_overrides": {"ai_weight": 0.7},
            "enabled": True,
        }
        service.db.fetch.return_value = [row]

        result = await service.get_all_symbol_strategies()
        assert len(result) == 1
        assert result[0].symbol == "BTC/USDT:USDT"
        assert result[0].merged_config.ai_weight == 0.7
