import pytest
import shutil
from pathlib import Path
from ai_trader.reporter import Reporter
from ai_trader.models.market import MarketData, Indicators, Kline
from ai_trader.models.decision import TradingDecision, TechnicalAnalysisResult


@pytest.fixture
def temp_output_dir(tmp_path):
    d = tmp_path / "test_reports"
    d.mkdir()
    return d


def test_generate_report(temp_output_dir):
    """Test report generation"""
    reporter = Reporter(output_dir=str(temp_output_dir))

    # Mock data
    market_data = MarketData(
        symbol="BTCUSDT",
        current_price=10000,
        klines=[],
        interval="15m",
        indicators=Indicators(
            ma7=100,
            ma25=100,
            ma99=100,
            rsi=50,
            macd=0,
            macd_signal=0,
            macd_histogram=0,
            boll_upper=101,
            boll_middle=100,
            boll_lower=99,
            atr=1,
        ),
        high_24h=10000,
        low_24h=9000,
        change_24h=0,
        volume_24h=100,
    )

    tech_result = TechnicalAnalysisResult(
        trend="bullish",
        trend_confidence=80,
        support_levels=[],
        resistance_levels=[],
        volume_trend="stable",
        pattern="none",
        signal_strength="buy",
        key_observations=["Test"],
    )

    decision = TradingDecision(
        action="open_long",
        confidence=90,
        leverage=5,
        position_size_percent=10,
        entry_price=10000,
        stop_loss_price=9000,
        take_profit_price=11000,
        order_type="market",
        reasoning="Test",
        execution_urgency="immediate",
    )

    filepath = reporter.generate(market_data, tech_result, decision, None, None, 0.0)

    assert filepath.exists()
    # Check for Chinese action name in filename
    # open_long -> 买入开多
    assert "买入开多" in filepath.name
    content = filepath.read_text("utf-8")
    assert "# 交易运行报告" in content
    assert "BTCUSDT" in content
