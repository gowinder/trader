"""LLM Provider 工厂函数"""

from .providers import (
    BaseLLMProvider,
    OpenRouterProvider,
    DeepSeekProvider,
    GLMProvider,
    GeminiProvider,
)
from ..config import config


def create_llm_provider() -> BaseLLMProvider:
    """创建 LLM Provider 实例

    根据配置创建对应的 LLM Provider。
    支持: openrouter, deepseek, glm, gemini

    Returns:
        BaseLLMProvider: LLM Provider 实例
    """
    llm_config = config.get_llm_config()
    provider = llm_config.provider.lower()
    api_key = llm_config.api_key
    model = llm_config.model
    fallback = llm_config.fallback_model
    base_url = llm_config.base_url
    timeout = llm_config.timeout

    if not api_key:
        raise ValueError(
            f"LLM API Key 未配置。请设置 LLM_API_KEY 或对应 Provider 的 API Key 环境变量。"
        )

    if provider == "openrouter":
        return OpenRouterProvider(
            api_key=api_key,
            model=model,
            fallback_model=fallback,
            base_url=base_url or OpenRouterProvider.DEFAULT_BASE_URL,
            timeout=timeout,
        )

    elif provider == "deepseek":
        return DeepSeekProvider(
            api_key=api_key,
            model=model,
            fallback_model=fallback,
            base_url=base_url or DeepSeekProvider.DEFAULT_BASE_URL,
            timeout=timeout,
        )

    elif provider == "glm":
        return GLMProvider(
            api_key=api_key,
            model=model,
            fallback_model=fallback,
            base_url=base_url or GLMProvider.DEFAULT_BASE_URL,
            timeout=timeout,
        )

    elif provider == "gemini":
        return GeminiProvider(
            api_key=api_key,
            model=model,
            fallback_model=fallback,
            base_url=base_url or GeminiProvider.DEFAULT_BASE_URL,
            timeout=timeout,
        )

    else:
        raise ValueError(f"不支持的 LLM Provider: {provider}")


# 为了向后兼容，保留 LLMClient 别名
class LLMClient:
    """LLM 客户端 (向后兼容)"""

    def __init__(self):
        self._provider = create_llm_provider()

    async def chat(
        self,
        messages,
        schema=None,
        max_tokens=2000,
        temperature=0.3,
    ):
        return await self._provider.chat(messages, schema, max_tokens, temperature)

    async def close(self):
        await self._provider.close()

    @property
    def provider_name(self) -> str:
        return self._provider.provider_name
