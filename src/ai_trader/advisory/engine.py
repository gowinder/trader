"""Advisory 引擎 - 核心决策生成"""

from typing import Optional, List, Dict, Any
from uuid import UUID

from .llm_client import AdvisoryLLMClient
from .persistence import AdvisoryPersistenceService
from .context import AdvisoryContextBuilder
from .prompts import ADVISORY_SYSTEM, ADVISORY_SCHEMA
from ..models.advisory import AdvisoryResult, Suggestion, TriggerType, SuggestionType, Urgency
from ..utils.logger import logger


class AdvisoryEngine:
    def __init__(
        self,
        llm_client: AdvisoryLLMClient,
        persistence: Optional[AdvisoryPersistenceService],
        context_builder: AdvisoryContextBuilder,
    ):
        self.llm = llm_client
        self.persistence = persistence
        self.context_builder = context_builder
        self._last_result: Optional[AdvisoryResult] = None

    async def generate_advisory(
        self,
        trigger_type: TriggerType,
        trigger_detail: Dict[str, Any],
        symbols: List[str],
        positions: List[Dict],
        market_data: Dict[str, Dict],
        sentiment: Optional[Dict],
        current_config: Dict[str, Any],
        account_summary: Optional[Dict] = None,
    ) -> Optional[UUID]:
        try:
            trigger_reason = f"{trigger_type.value}: {trigger_detail}" if trigger_detail else trigger_type.value
            context = await self.context_builder.build(
                symbols=symbols,
                positions=positions,
                market_data=market_data,
                sentiment=sentiment,
                trigger_reason=trigger_reason,
                current_config=current_config,
                account_summary=account_summary,
            )
            messages = [
                {"role": "system", "content": ADVISORY_SYSTEM},
                {"role": "user", "content": context},
            ]
            raw_result = await self.llm.chat(
                messages=messages,
                schema=ADVISORY_SCHEMA,
                max_tokens=4000,
                temperature=0.3,
            )
            result = self._parse_result(raw_result)
            self._last_result = result

            advisory_id = None
            if self.persistence:
                advisory_id = await self.persistence.save_advisory(
                    result=result,
                    trigger_type=trigger_type,
                    trigger_detail=trigger_detail,
                    llm_provider=getattr(self.llm, "provider_name", "unknown"),
                    llm_model=getattr(self.llm, "model_name", "unknown"),
                    tokens_used=0,
                )

            logger.info(
                f"Advisory generated: id={advisory_id}, urgency={result.urgency.value}, "
                f"suggestions={len(result.suggestions)}"
            )
            return advisory_id
        except Exception as e:
            logger.error(f"Failed to generate advisory: {type(e).__name__}: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return None

    @property
    def last_result(self) -> Optional[AdvisoryResult]:
        return self._last_result

    # LLM 返回的 type 名称到 SuggestionType 的映射
    _TYPE_ALIASES: Dict[str, str] = {
        "parameter_adjustment": "param_adjust",
        "param_adjustment": "param_adjust",
        "position": "position_action",
        "symbol": "symbol_change",
    }

    def _parse_result(self, raw: Dict[str, Any]) -> AdvisoryResult:
        suggestions = []
        for s in raw.get("suggestions", []):
            try:
                raw_type = s.get("type", "param_adjust")
                mapped_type = self._TYPE_ALIASES.get(raw_type, raw_type)
                # 兼容 LLM 返回的不同字段名
                detail = s.get("detail") or s.get("details", {})
                suggestions.append(Suggestion(
                    type=SuggestionType(mapped_type),
                    target=s.get("target") or s.get("symbol", "global"),
                    action=s.get("action", "unknown"),
                    detail=detail,
                    reasoning=s.get("reasoning") or detail.get("reasoning", "") if isinstance(detail, dict) else "",
                    risk_note=s.get("risk_note", ""),
                ))
            except (ValueError, KeyError) as e:
                logger.warning(f"Skipping malformed suggestion: {e}, raw={s}")
        # market_summary 可能是 dict 或 string
        market_summary = raw.get("market_summary", "")
        if isinstance(market_summary, dict):
            import json
            market_summary = json.dumps(market_summary, ensure_ascii=False)
        return AdvisoryResult(
            urgency=Urgency(raw.get("urgency", "low")),
            suggestions=suggestions,
            market_summary=market_summary,
        )
