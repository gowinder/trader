"""LLM 使用量追踪器 - 记录调用统计和费用"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass

from ..utils.logger import logger


@dataclass
class UsageRecord:
    """使用记录"""
    id: Optional[int] = None
    timestamp: Optional[datetime] = None
    provider: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    success: bool = True
    error_message: str = ""

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if self.total_tokens == 0:
            self.total_tokens = self.input_tokens + self.output_tokens


class PricingManager:
    """价格管理器"""

    DEFAULT_PRICING = {
        "openrouter": {
            "deepseek/deepseek-v3.2": {"input": 0.14, "output": 0.28},
            "deepseek/deepseek-chat": {"input": 0.14, "output": 0.28},
        },
        "gemini": {
            "gemini-2.0-flash": {"input": 0, "output": 0},
            "gemini-1.5-pro": {"input": 0, "output": 0},
        },
        "codex": {
            "gpt-4o": {"input": 2.5, "output": 10},
            "gpt-4o-mini": {"input": 0.15, "output": 0.6},
        },
        "qwen": {
            "qwen-max-latest": {"input": 0, "output": 0},
            "qwen-plus": {"input": 0, "output": 0},
        },
    }

    def __init__(self, pricing_file: Optional[str] = None):
        self._pricing = self.DEFAULT_PRICING.copy()
        self._pricing_file = pricing_file

        if pricing_file:
            self._load_pricing_file(pricing_file)

    def _load_pricing_file(self, path: str):
        """从文件加载价格配置"""
        file_path = Path(path)
        if file_path.exists():
            try:
                with open(file_path, "r") as f:
                    custom_pricing = json.load(f)
                    # 合并配置
                    for provider, models in custom_pricing.items():
                        if provider not in self._pricing:
                            self._pricing[provider] = {}
                        self._pricing[provider].update(models)
            except Exception as e:
                logger.warning(f"Failed to load pricing file: {e}")

    def get_cost(self, provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
        """计算费用（USD）"""
        provider_pricing = self._pricing.get(provider, {})

        # 尝试精确匹配
        model_pricing = provider_pricing.get(model)

        # 尝试模糊匹配
        if model_pricing is None:
            for m, p in provider_pricing.items():
                if m in model or model in m:
                    model_pricing = p
                    break

        if model_pricing is None:
            return 0.0

        # 价格单位是 per 1M tokens
        input_cost = (input_tokens / 1_000_000) * model_pricing.get("input", 0)
        output_cost = (output_tokens / 1_000_000) * model_pricing.get("output", 0)

        return input_cost + output_cost


class UsageTracker:
    """使用量追踪器 - 使用 PostgreSQL 存储"""

    def __init__(
        self,
        pricing_file: Optional[str] = None,
    ):
        self._pricing_manager = PricingManager(pricing_file)
        self._persistence_service = None
        self._initialized = False

    def set_persistence_service(self, persistence_service):
        """设置持久化服务

        Args:
            persistence_service: DecisionPersistenceService 实例
        """
        self._persistence_service = persistence_service
        self._initialized = True
        logger.info("UsageTracker initialized with PostgreSQL persistence")

    async def record(
        self,
        provider: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        latency_ms: int = 0,
        success: bool = True,
        error_message: str = "",
        decision_id: Optional[str] = None,
        usage_type: Optional[str] = None,
        trigger_source: Optional[str] = None,
        llm_prompt: Optional[str] = None,
        llm_response: Optional[str] = None,
    ):
        """记录一次调用"""
        if not self._initialized or not self._persistence_service:
            logger.warning("UsageTracker not initialized, skipping record")
            return

        total_tokens = input_tokens + output_tokens
        cost_usd = self._pricing_manager.get_cost(
            provider, model, input_tokens, output_tokens
        )

        try:
            from uuid import UUID
            decision_uuid = UUID(decision_id) if decision_id else None

            await self._persistence_service.record_llm_usage(
                provider=provider,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                cost_usd=cost_usd,
                latency_ms=latency_ms,
                success=success,
                error_message=error_message if not success else None,
                decision_id=decision_uuid,
                usage_type=usage_type,
                trigger_source=trigger_source,
                llm_prompt=llm_prompt,
                llm_response=llm_response,
            )
        except Exception as e:
            logger.error(f"Failed to record LLM usage: {e}")

    async def get_stats(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """获取统计数据"""
        if not self._initialized or not self._persistence_service:
            return {
                "total_calls": 0,
                "total_tokens": 0,
                "total_cost_usd": 0,
                "today_cost_usd": 0,
                "success_rate": 0,
                "avg_latency_ms": 0,
                "by_provider": {},
            }

        return await self._persistence_service.get_llm_usage_stats(
            start_time=start_time,
            end_time=end_time,
        )

    async def get_daily_stats(self, days: int = 30) -> list:
        """获取每日统计数据"""
        if not self._initialized or not self._persistence_service:
            return []

        return await self._persistence_service.get_llm_daily_stats(days=days)

    async def get_records(
        self,
        limit: int = 100,
        offset: int = 0,
        provider: Optional[str] = None,
    ) -> Dict[str, Any]:
        """获取调用记录"""
        if not self._initialized or not self._persistence_service:
            return {"records": [], "total": 0, "limit": limit, "offset": offset}

        return await self._persistence_service.get_llm_usage_records(
            limit=limit,
            offset=offset,
            provider=provider,
        )

    async def get_today_cost(self) -> float:
        """获取今日费用"""
        stats = await self.get_stats()
        return stats.get("today_cost_usd", 0.0)

    async def close(self):
        """关闭（兼容接口）"""
        pass


# 全局单例
_usage_tracker: Optional[UsageTracker] = None


def get_usage_tracker() -> UsageTracker:
    """获取全局 UsageTracker 实例"""
    global _usage_tracker
    if _usage_tracker is None:
        _usage_tracker = UsageTracker()
    return _usage_tracker
