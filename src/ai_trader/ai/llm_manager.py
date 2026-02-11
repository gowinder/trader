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
        self._providers_pool: Dict[str, Dict[str, Any]] = {}  # Dashboard 动态配置的 provider 池

    def _create_provider(self, name: str, model: Optional[str] = None) -> BaseLLMProvider:
        """创建 Provider 实例，支持从 providers_pool 获取动态参数"""
        pool = getattr(self, '_providers_pool', {})
        pool_info = pool.get(name, {})
        api_key = pool_info.get("api_key", "")
        base_url = pool_info.get("base_url", "")
        timeout = pool_info.get("timeout") or 60

        if name == "qwen":
            if api_key:
                # 有 API Key 时使用 HTTP Provider（OpenAI 兼容）
                from .providers.base import HTTPBasedProvider
                return HTTPBasedProvider(
                    api_key=api_key,
                    model=model or "qwen-max",
                    base_url=base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1",
                    timeout=timeout,
                )
            return QwenCLIProvider(model=model or "qwen-max")
        elif name == "gemini":
            if api_key:
                from .providers.gemini import GeminiProvider
                return GeminiProvider(
                    api_key=api_key,
                    model=model or "gemini-2.0-flash",
                    base_url=base_url or "https://generativelanguage.googleapis.com/v1beta",
                    timeout=timeout,
                )
            return GeminiCLIProvider(model=model or "gemini-2.0-flash")
        elif name == "codex":
            return CodexOAuthProvider(model=model or "gpt-4o")
        elif name == "openrouter":
            return OpenRouterProvider(
                api_key=api_key or config.openrouter_api_key or config.llm_api_key,
                model=model or config.llm_model,
                fallback_model=config.llm_fallback_model,
            )
        elif name == "deepseek":
            from .providers.deepseek import DeepSeekProvider
            return DeepSeekProvider(
                api_key=api_key or config.llm_api_key,
                model=model or "deepseek-chat",
                base_url=base_url or "https://api.deepseek.com/v1",
                timeout=timeout,
            )
        elif name == "glm":
            from .providers.glm import GLMProvider
            return GLMProvider(
                api_key=api_key or config.llm_api_key,
                model=model or "glm-4-plus",
                base_url=base_url or "https://open.bigmodel.cn/api/anthropic",
                timeout=timeout,
            )
        else:
            # 自定义 Provider — 默认 OpenAI 兼容协议
            if not api_key:
                raise ValueError(f"Provider '{name}' requires api_key (configure in Dashboard settings)")
            from .providers.base import HTTPBasedProvider
            return HTTPBasedProvider(
                api_key=api_key,
                model=model or "default",
                base_url=base_url,
                timeout=timeout,
            )

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

    def _get_ordered_providers(self, exclude: set = None) -> List[ProviderConfig]:
        """按策略返回排序后的可用 provider 列表（用于故障转移）

        Args:
            exclude: 需要排除的 provider 名称集合
        """
        exclude = exclude or set()
        available = [
            p for p in self.providers_config
            if self._is_provider_available(p) and p.name not in exclude
        ]
        if not available:
            return []

        if self.strategy == ScheduleStrategy.PRIORITY:
            # 严格按优先级排序
            available.sort(key=lambda p: p.priority)
        elif self.strategy == ScheduleStrategy.COST_FIRST:
            # 免费优先，同组内按优先级排序
            available.sort(key=lambda p: (0 if p.cost_tier == "free" else 1, p.priority))
        # ROUND_ROBIN 保持原顺序

        return available

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
        """发送聊天请求，自动负载均衡和故障转移

        按优先级逐个尝试 provider，成功立即返回，失败则 fallback 到下一个。
        """
        start_time = time.time()
        last_error = None
        tried_providers = set()

        if provider:
            # 强制使用指定 provider，不做 fallback
            provider_config = next(
                (p for p in self.providers_config if p.name == provider),
                None
            )
            if not provider_config:
                raise ValueError(f"Unknown provider: {provider}")
            providers_to_try = [provider_config]
        else:
            # 按策略获取排序后的 provider 列表
            providers_to_try = self._get_ordered_providers()

        if not providers_to_try:
            raise RuntimeError("No LLM providers available")

        for i, provider_config in enumerate(providers_to_try):
            tried_providers.add(provider_config.name)

            try:
                llm_provider = self._get_provider(
                    provider_config.name,
                    provider_config.model
                )
                logger.debug(
                    f"Using provider: {provider_config.name} "
                    f"(priority={provider_config.priority}, {i+1}/{len(providers_to_try)})"
                )

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
                logger.warning(
                    f"Provider {provider_config.name} failed ({i+1}/{len(providers_to_try)}): {e}"
                )

                # 记录失败统计
                if self._usage_tracker:
                    latency_ms = int((time.time() - start_time) * 1000)
                    await self._usage_tracker.record(
                        provider=provider_config.name,
                        model=provider_config.model or llm_provider.model,
                        input_tokens=0,
                        output_tokens=0,
                        latency_ms=latency_ms,
                        success=False,
                        error_message=str(e),
                    )

                # 退避等待（最后一个 provider 不等待）
                if i < len(providers_to_try) - 1:
                    backoff = self.retry_config.backoff_seconds[
                        min(i, len(self.retry_config.backoff_seconds) - 1)
                    ]
                    await asyncio.sleep(backoff)

        raise RuntimeError(
            f"All LLM providers failed after trying {len(tried_providers)} providers "
            f"({', '.join(tried_providers)}). Last error: {last_error}"
        )

    def set_usage_tracker(self, tracker):
        """设置使用量追踪器"""
        self._usage_tracker = tracker

    def update_providers(self, provider_list: List[Dict[str, Any]],
                         providers_pool: Optional[Dict[str, Dict[str, Any]]] = None,
                         strategy: Optional[str] = None):
        """动态更新 provider 配置（从 Redis 配置）

        provider_list 格式: [{"name": "qwen", "model": "qwen-max"}, ...]
                     或    [{"provider": "qwen", "model": "qwen-max"}, ...]
        providers_pool 格式: {"qwen": {"api_key": "...", "base_url": "...", "timeout": 60}, ...}
        """
        new_configs = []
        for i, p in enumerate(provider_list):
            name = p.get("name", "") or p.get("provider", "")
            model = p.get("model")
            if not name:
                continue
            new_configs.append(ProviderConfig(
                name=name,
                priority=i + 1,
                cost_tier="free",
                weight=max(1, len(provider_list) - i),
                model=model,
            ))

        if new_configs:
            self.providers_config = new_configs
            if strategy:
                try:
                    self.strategy = ScheduleStrategy(strategy)
                except ValueError:
                    self.strategy = ScheduleStrategy.PRIORITY
            else:
                self.strategy = ScheduleStrategy.PRIORITY

            # 保存 provider 池信息供 _create_provider 使用
            if providers_pool:
                self._providers_pool = providers_pool

            # 关闭旧 provider 实例并清空缓存
            for provider in self._providers.values():
                try:
                    import asyncio
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        loop.create_task(provider.close())
                    else:
                        loop.run_until_complete(provider.close())
                except Exception:
                    pass
            self._providers.clear()

            logger.info(
                f"Provider config updated: "
                f"{[f'{p.name}({p.model})' for p in new_configs]}"
                + (f", pool keys: {list(providers_pool.keys())}" if providers_pool else "")
            )

    def get_providers_info(self) -> List[Dict[str, Any]]:
        """获取当前 provider 配置信息"""
        return [
            {
                "name": p.name,
                "model": p.model,
                "priority": p.priority,
                "available": self._is_provider_available(p),
                "cooldown_until": p.cooldown_until if p.cooldown_until > time.time() else 0,
                "consecutive_failures": p.consecutive_failures,
            }
            for p in self.providers_config
        ]

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
