# tests/optimization/test_rule_validator.py
import pytest
from datetime import datetime
from ai_trader.optimization.rule_validator import RuleValidator
from ai_trader.memory.models import TradeMemoryEntry


class TestRuleValidator:
    @pytest.fixture
    def validator(self):
        return RuleValidator()

    @pytest.fixture
    def sample_trades(self):
        # 创建 30 笔交易，其中震荡市 20 笔
        trades = []
        for i in range(30):
            is_ranging = i < 20
            # 震荡市胜率 75%，趋势市胜率 67%
            is_winner = (i % 4 != 0) if is_ranging else (i % 3 != 0)

            trades.append(TradeMemoryEntry(
                trade_id=f"t{i}",
                timestamp=datetime.now(),
                symbol="BTCUSDT",
                action="close_long",
                confidence=55.0 if is_ranging else 70.0,
                leverage=5.0,
                reasoning="test",
                market_state="ranging" if is_ranging else "strong_trend",
                entry_price=50000.0,
                pnl_percent=2.0 if is_winner else -1.5,
                is_winner=is_winner,
            ))
        return trades

    def test_validate_with_sufficient_samples(self, validator, sample_trades):
        rule = {
            "condition": {"market_state": "ranging"},
            "recommendation": {"confidence_threshold": "+10"},
        }

        result = validator.validate(rule, sample_trades)

        assert "is_valid" in result
        assert "sample_size" in result
        assert result["sample_size"] >= 20

    def test_reject_insufficient_samples(self, validator):
        trades = [
            TradeMemoryEntry(
                trade_id="t1",
                timestamp=datetime.now(),
                symbol="BTCUSDT",
                action="close_long",
                confidence=70.0,
                leverage=5.0,
                reasoning="test",
                market_state="ranging",
                entry_price=50000.0,
                is_winner=True,
            )
        ] * 5  # 只有 5 笔

        rule = {"condition": {"market_state": "ranging"}, "recommendation": {}}

        result = validator.validate(rule, trades)

        assert result["is_valid"] is False
        assert "样本不足" in result["reason"]
