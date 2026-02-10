import pytest
from ai_trader.models.advisory import (
    AdvisoryResult, Suggestion, SuggestionType, SuggestionStatus,
    AdvisoryStatus, Urgency, TriggerType,
)

def test_suggestion_model():
    s = Suggestion(
        type=SuggestionType.PARAM_ADJUST,
        target="global",
        action="reduce_leverage",
        detail={"leverage_max": 5},
        reasoning="市场波动加剧，建议降低最大杠杆",
        risk_note="可能错过高杠杆带来的收益",
    )
    assert s.type == SuggestionType.PARAM_ADJUST
    assert s.status == SuggestionStatus.PENDING

def test_advisory_result_model():
    s = Suggestion(
        type=SuggestionType.POSITION_ACTION,
        target="BTC/USDT:USDT",
        action="close_position",
        detail={"reason": "止损"},
        reasoning="浮亏超过阈值",
        risk_note="可能错过反弹",
    )
    result = AdvisoryResult(
        urgency=Urgency.HIGH,
        suggestions=[s],
        market_summary="BTC 短时间内大幅下跌",
    )
    assert result.urgency == Urgency.HIGH
    assert len(result.suggestions) == 1

def test_suggestion_status_flow():
    s = Suggestion(
        type=SuggestionType.SYMBOL_CHANGE,
        target="ETH/USDT:USDT",
        action="add_symbol",
        detail={},
        reasoning="ETH 趋势明确",
        risk_note="增加持仓风险",
    )
    assert s.status == SuggestionStatus.PENDING
    s.status = SuggestionStatus.ACCEPTED
    assert s.status == SuggestionStatus.ACCEPTED
