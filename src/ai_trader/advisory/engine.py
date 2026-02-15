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
        advisory_id = None
        llm_provider = getattr(self.llm, "provider_name", "unknown")
        llm_model = getattr(self.llm, "model_name", "unknown")

        # 先创建 running 状态记录
        if self.persistence:
            try:
                advisory_id = await self.persistence.create_running_advisory(
                    trigger_type=trigger_type,
                    trigger_detail=trigger_detail,
                    llm_provider=llm_provider,
                    llm_model=llm_model,
                )
            except Exception as e:
                logger.error(f"Failed to create running advisory: {e}")

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
                strategy_preset_info=current_config.get("_strategy_preset_info"),
                market_classifications=current_config.get("_market_classifications"),
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

            if self.persistence and advisory_id:
                await self.persistence.complete_advisory(advisory_id, result)
            elif self.persistence:
                # 降级：running 记录创建失败时走旧逻辑
                advisory_id = await self.persistence.save_advisory(
                    result=result,
                    trigger_type=trigger_type,
                    trigger_detail=trigger_detail,
                    llm_provider=llm_provider,
                    llm_model=llm_model,
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
            # 标记为失败
            if self.persistence and advisory_id:
                try:
                    await self.persistence.fail_advisory(advisory_id, f"{type(e).__name__}: {e}")
                except Exception:
                    pass
            return None

    @property
    def last_result(self) -> Optional[AdvisoryResult]:
        return self._last_result

    # LLM 返回的 type 名称到 SuggestionType 的映射
    _TYPE_ALIASES: Dict[str, str] = {
        # param_adjust
        "param_adjust": "param_adjust",
        "parameter_adjustment": "param_adjust",
        "param_adjustment": "param_adjust",
        "parameter_adjustments": "param_adjust",
        "parameter": "param_adjust",
        "adjustment": "param_adjust",
        "config_change": "param_adjust",
        "config": "param_adjust",
        # position_action
        "position": "position_action",
        "position_action": "position_action",
        "position_actions": "position_action",
        "position_management": "position_action",
        "trade_action": "position_action",
        "trade": "position_action",
        # symbol_change
        "symbol": "symbol_change",
        "symbol_change": "symbol_change",
        "symbol_management": "symbol_change",
        "symbol_changes": "symbol_change",
        "symbol_adjustment": "symbol_change",
        "trading_pair": "symbol_change",
        # strategy_change
        "strategy_change": "strategy_change",
        "strategy": "strategy_change",
        "preset_change": "strategy_change",
        "strategy_switch": "strategy_change",
        "preset": "strategy_change",
        "preset_switch": "strategy_change",
        "strategy_adjustment": "strategy_change",
    }

    # suggestions 为 dict 时，key 到 type 的映射
    _CATEGORY_TYPE_MAP: Dict[str, str] = {
        # param_adjust
        "parameter_adjustments": "param_adjust",
        "parameter_adjustment": "param_adjust",
        "param_adjustments": "param_adjust",
        "param_adjust": "param_adjust",
        "config_changes": "param_adjust",
        # position_action
        "position_actions": "position_action",
        "position_action": "position_action",
        "trade_actions": "position_action",
        # symbol_change
        "symbol_management": "symbol_change",
        "symbol_changes": "symbol_change",
        "symbol_change": "symbol_change",
        "trading_pairs": "symbol_change",
        # strategy_change
        "strategy_changes": "strategy_change",
        "strategy_change": "strategy_change",
        "preset_changes": "strategy_change",
    }

    def _flatten_suggestions(self, raw_suggestions) -> List[Dict[str, Any]]:
        """将 suggestions 统一为 list，兼容 dict 分类结构和 list 结构"""
        if isinstance(raw_suggestions, list):
            return raw_suggestions
        if isinstance(raw_suggestions, dict):
            flat = []
            for category_key, items in raw_suggestions.items():
                inferred_type = self._CATEGORY_TYPE_MAP.get(category_key)
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict):
                            if inferred_type and "type" not in item:
                                item["type"] = inferred_type
                            flat.append(item)
                elif isinstance(items, dict):
                    if inferred_type and "type" not in items:
                        items["type"] = inferred_type
                    flat.append(items)
            return flat
        return []

    def _parse_result(self, raw: Dict[str, Any]) -> AdvisoryResult:
        import json as _json
        logger.info(f"Raw advisory LLM output: {_json.dumps(raw, ensure_ascii=False, default=str)[:2000]}")
        suggestions = []
        # 全局 risk_note（部分 LLM 把 risk_note 放在顶层）
        global_risk_note = raw.get("risk_note", "")
        if isinstance(global_risk_note, dict):
            global_risk_note = _json.dumps(global_risk_note, ensure_ascii=False)

        raw_suggestions = self._flatten_suggestions(raw.get("suggestions", []))
        for s in raw_suggestions:
            try:
                raw_type = s.get("type", "param_adjust")
                mapped_type = self._TYPE_ALIASES.get(raw_type, raw_type)
                # 兼容不同字段名: detail / details / changes
                detail = s.get("detail") or s.get("details") or s.get("changes", {})
                if not isinstance(detail, dict):
                    detail = {}
                # target: target / symbol / scope
                target = s.get("target") or s.get("symbol") or s.get("scope", "global")
                # action: 优先取顶层 action，否则从 detail key 推断
                action = s.get("action", "")
                if not action and detail:
                    action = next(iter(detail.keys()), "adjust")
                action = action or "adjust"
                # reasoning: 多个可能的来源
                reasoning = s.get("reasoning", "") or s.get("reasoning_cn", "") or s.get("note", "")
                if not reasoning and isinstance(detail, dict):
                    reasoning = detail.pop("reasoning", "") or detail.pop("reasoning_cn", "")
                # risk_note: 每条或全局
                risk_note = s.get("risk_note", "") or s.get("risk", "") or global_risk_note
                # 额外字段也收集到 detail 中（如 size_percent, targets, urgency 等）
                extra_keys = set(s.keys()) - {"type", "target", "symbol", "scope", "action",
                    "detail", "details", "changes", "reasoning", "reasoning_cn",
                    "risk_note", "risk", "note"}
                for k in extra_keys:
                    if k not in detail:
                        detail[k] = s[k]

                suggestions.append(Suggestion(
                    type=SuggestionType(mapped_type),
                    target=target,
                    action=action,
                    detail=detail,
                    reasoning=reasoning,
                    risk_note=risk_note,
                ))
            except (ValueError, KeyError) as e:
                logger.warning(f"Skipping malformed suggestion: {e}, raw={s}")
        # market_summary: 可能是 dict 或 string
        market_summary = raw.get("market_summary", "")
        if isinstance(market_summary, dict):
            # 有些 LLM 把 summary/overview 放在 dict 里
            market_summary = market_summary.get("summary") or market_summary.get("overview") \
                or _json.dumps(market_summary, ensure_ascii=False)
        # urgency: 可能在顶层或 market_summary dict 里
        urgency_str = raw.get("urgency", "")
        if not urgency_str and isinstance(raw.get("market_summary"), dict):
            urgency_str = raw["market_summary"].get("urgency", "low")
        urgency_str = urgency_str or "low"
        return AdvisoryResult(
            urgency=Urgency(urgency_str),
            suggestions=suggestions,
            market_summary=market_summary,
        )
