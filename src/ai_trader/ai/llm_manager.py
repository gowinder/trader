"""LLM Manager - 多 Provider 负载均衡、成本优化、故障转移"""

import asyncio
import time
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field
from enum import Enum

from .token_manager import get_token_manager, TokenManager
from .providers.base import BaseLLMProvider
from .providers.qwen_oauth import QwenOAuthProvider
from .providers.gemini_oauth import GeminiOAuthProvider
from .providers.codex_oauth import CodexOAuthProvider
from .providers.openrouter import OpenRouterProvider
from .providers.cli_provider import GeminiCLIProvider, QwenCLIProvider
from ..config import config
from ..utils.logger import logger


class ScheduleStrategy(Enum):
    """调度策略"""
    COST_FIRST = "cost_first"      # 成本优先（免费优先）
    ROUND_ROBIN = "round_robin"    # 加权轮询
    PRIORITY = "priority"          # 严格优先级


@dataclass
class ProviderConfig:
    """Provider 配置"""
    name: str
    priority: int = 1              # 优先级，数字越小越优先
    cost_tier: str = "free"        # free | paid
    weight: int = 1                # 轮询权重
    model: Optional[str] = None    # 使用的模型
    cooldown_until: float = 0      # 冷却截止时间（timestamp）
    consecutive_failures: int = 0  # 连续失败次数


@dataclass
class RetryConfig:
    """重试配置"""
    max_retries: int = 3
    backoff_seconds: List[float] = field(default_factory=lambda: [1, 5, 15])
    cooldown_on_429: int = 60      # 429 限流后冷却时间


class LLMManager:
    """LLM 统一管理器"""

    @staticmethod
    def _get_default_providers() -> List[ProviderConfig]:
        """根据环境配置动态生成 provider 列表

        如果配置了 LLM_PROVIDER=openrouter，优先使用 openrouter
        避免在 Docker 容器中无 CLI 工具时失败
        """
        configured_provider = config.llm_provider.lower()

        if configured_provider == "openrouter":
            # OpenRouter 配置时，将 openrouter 标记为 free 确保 COST_FIRST 策略优先使用
            logger.info("LLM_PROVIDER=openrouter, prioritizing OpenRouter")
            return [
                ProviderConfig(name="openrouter", priority=1, cost_tier="free", weight=10),
                ProviderConfig(name="codex", priority=2, cost_tier="paid", weight=2),
                ProviderConfig(name="qwen", priority=3, cost_tier="paid", weight=1),
                ProviderConfig(name="gemini", priority=3, cost_tier="paid", weight=1),
            ]
        else:
            # 默认：免费 CLI 优先
            return [
                ProviderConfig(name="qwen", priority=1, cost_tier="free", weight=4),
                ProviderConfig(name="gemini", priority=1, cost_tier="free", weight=3),
                ProviderConfig(name="codex", priority=1, cost_tier="free", weight=3),
                ProviderConfig(name="openrouter", priority=2, cost_tier="paid", weight=1),
            ]

    def __init__(
        self,
        strategy: ScheduleStrategy = ScheduleStrategy.COST_FIRST,
        providers_config: Optional[List[ProviderConfig]] = None,
        retry_config: Optional[RetryConfig] = None,
    ):
        self.strategy = strategy
        self.providers_config = providers_config or self._get_default_providers()
        self.retry_config = retry_config or RetryConfig()

        self._token_manager = get_token_manager()
        self._providers: Dict[str, BaseLLMProvider] = {}
        self._round_robin_index = 0
        self._usage_tracker = None  # 稍后注入

    def _create_provider(self, name: str, model: Optional[str] = None) -> BaseLLMProvider:
        """创建 Provider 实例"""
        if name == "qwen":
            # 使用 CLI Provider（更可靠）
            return QwenCLIProvider(model=model or "qwen-max")
        elif name == "gemini":
            # 使用 CLI Provider（OAuth scope 不足）
            return GeminiCLIProvider(model=model or "gemini-2.0-flash")
        elif name == "codex":
            return CodexOAuthProvider(model=model or "gpt-4o")
        elif name == "openrouter":
            return OpenRouterProvider(
                api_key=config.openrouter_api_key or config.llm_api_key,
                model=model or config.llm_model,
                fallback_model=config.llm_fallback_model,
            )
        else:
            raise ValueError(f"Unknown provider: {name}")

    def _get_provider(self, name: str, model: Optional[str] = None) -> BaseLLMProvider:
        """获取或创建 Provider 实例"""
        key = f"{name}:{model or 'default'}"
        if key not in self._providers:
            self._providers[key] = self._create_provider(name, model)
        return self._providers[key]

    def _is_provider_available(self, provider_config: ProviderConfig) -> bool:
        """检查 provider 是否可用"""
        import shutil

        # 检查冷却期
        if provider_config.cooldown_until > time.time():
            return False

        # CLI Provider - 检查命令是否存在
        if provider_config.name == "qwen":
            return shutil.which("qwen") is not None
        elif provider_config.name == "gemini":
            return shutil.which("gemini") is not None

        # Codex OAuth - 检查 token 可用性
        if provider_config.name == "codex":
            return self._token_manager.is_available("codex")

        # OpenRouter 只要有 API key 就可用
        if provider_config.name == "openrouter":
            return bool(config.openrouter_api_key or config.llm_api_key)

        return True

    def _select_provider_cost_first(self) -> Optional[ProviderConfig]:
        """成本优先策略选择 provider"""
        # 分组：免费和付费
        free_providers = [
            p for p in self.providers_config
            if p.cost_tier == "free" and self._is_provider_available(p)
        ]
        paid_providers = [
            p for p in self.providers_config
            if p.cost_tier == "paid" and self._is_provider_available(p)
        ]

        # 优先在免费组内按权重选择
        if free_providers:
            return self._weighted_select(free_providers)

        # 免费组用尽，使用付费组
        if paid_providers:
            return self._weighted_select(paid_providers)

        return None

    def _select_provider_round_robin(self) -> Optional[ProviderConfig]:
        """加权轮询策略选择 provider"""
        available = [
            p for p in self.providers_config
            if self._is_provider_available(p)
        ]
        if not available:
            return None

        return self._weighted_select(available)

    def _select_provider_priority(self) -> Optional[ProviderConfig]:
        """严格优先级策略选择 provider"""
        available = [
            p for p in self.providers_config
            if self._is_provider_available(p)
        ]
        if not available:
            return None

        # 按优先级排序，取最高优先级（数字最小）
        available.sort(key=lambda p: p.priority)
        return available[0]

    def _weighted_select(self, providers: List[ProviderConfig]) -> ProviderConfig:
        """加权选择"""
        total_weight = sum(p.weight for p in providers)
        self._round_robin_index = (self._round_robin_index + 1) % total_weight

        cumulative = 0
        for p in providers:
            cumulative += p.weight
            if self._round_robin_index < cumulative:
                return p

        return providers[0]

    def _select_provider(self) -> Optional[ProviderConfig]:
        """根据策略选择 provider"""
        if self.strategy == ScheduleStrategy.COST_FIRST:
            return self._select_provider_cost_first()
        elif self.strategy == ScheduleStrategy.ROUND_ROBIN:
            return self._select_provider_round_robin()
        elif self.strategy == ScheduleStrategy.PRIORITY:
            return self._select_provider_priority()
        return None

    def _handle_failure(self, provider_config: ProviderConfig, error: Exception):
        """处理失败"""
        provider_config.consecutive_failures += 1

        # 检查是否是 429 限流
        error_str = str(error)
        if "429" in error_str or "Too Many Requests" in error_str:
            provider_config.cooldown_until = time.time() + self.retry_config.cooldown_on_429
            logger.warning(
                f"Provider {provider_config.name} rate limited, "
                f"cooldown for {self.retry_config.cooldown_on_429}s"
            )
        elif provider_config.consecutive_failures >= 3:
            # 连续失败 3 次，短暂冷却
            provider_config.cooldown_until = time.time() + 30
            logger.warning(
                f"Provider {provider_config.name} consecutive failures, "
                f"cooldown for 30s"
            )

    def _handle_success(self, provider_config: ProviderConfig):
        """处理成功"""
        provider_config.consecutive_failures = 0

    async def chat(
        self,
        messages: List[Dict[str, str]],
        schema: Optional[Dict[str, Any]] = None,
        max_tokens: int = 2000,
        temperature: float = 0.3,
        provider: Optional[str] = None,
    ) -> Dict[str, Any]:
        """发送聊天请求，自动负载均衡和故障转移"""
        start_time = time.time()
        last_error = None
        tried_providers = set()

        for attempt in range(self.retry_config.max_retries + 1):
            # 选择 provider
            if provider:
                # 强制使用指定 provider
                provider_config = next(
                    (p for p in self.providers_config if p.name == provider),
                    None
                )
                if not provider_config:
                    raise ValueError(f"Unknown provider: {provider}")
            else:
                provider_config = self._select_provider()

            if provider_config is None:
                break

            # 跳过已尝试的 provider（除非只有一个）
            if provider_config.name in tried_providers and len(self.providers_config) > 1:
                continue

            tried_providers.add(provider_config.name)

            try:
                llm_provider = self._get_provider(
                    provider_config.name,
                    provider_config.model
                )
                logger.debug(f"Using provider: {provider_config.name}")

                result = await llm_provider.chat(
                    messages=messages,
                    schema=schema,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )

                self._handle_success(provider_config)

                # 记录统计
                latency_ms = int((time.time() - start_time) * 1000)
                if self._usage_tracker:
                    usage = result.get("usage", {})
                    await self._usage_tracker.record(
                        provider=provider_config.name,
                        model=provider_config.model or llm_provider.model,
                        input_tokens=usage.get("prompt_tokens", 0),
                        output_tokens=usage.get("completion_tokens", 0),
                        latency_ms=latency_ms,
                        success=True,
                    )

                return result

            except Exception as e:
                last_error = e
                self._handle_failure(provider_config, e)
                logger.warning(f"Provider {provider_config.name} failed: {e}")

                # 记录失败统计
                if self._usage_tracker:
                    latency_ms = int((time.time() - start_time) * 1000)
                    await self._usage_tracker.record(
                        provider=provider_config.name,
                        model=provider_config.model or "unknown",
                        input_tokens=0,
                        output_tokens=0,
                        latency_ms=latency_ms,
                        success=False,
                        error_message=str(e),
                    )

                # 退避等待
                if attempt < self.retry_config.max_retries:
                    backoff = self.retry_config.backoff_seconds[
                        min(attempt, len(self.retry_config.backoff_seconds) - 1)
                    ]
                    await asyncio.sleep(backoff)

        raise RuntimeError(
            f"All LLM providers failed after {self.retry_config.max_retries + 1} attempts. "
            f"Last error: {last_error}"
        )

    def set_usage_tracker(self, tracker):
        """设置使用量追踪器"""
        self._usage_tracker = tracker

    async def start(self):
        """启动 manager"""
        await self._token_manager.start_background_refresh()

    async def close(self):
        """关闭所有 provider"""
        await self._token_manager.close()
        for provider in self._providers.values():
            await provider.close()
        self._providers.clear()


# 全局单例
_llm_manager: Optional[LLMManager] = None


def get_llm_manager() -> LLMManager:
    """获取全局 LLMManager 实例"""
    global _llm_manager
    if _llm_manager is None:
        _llm_manager = LLMManager()
    return _llm_manager
