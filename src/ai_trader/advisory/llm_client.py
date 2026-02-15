"""Advisory 专用 LLM 客户端 - 配置完全由 Dashboard/Redis 管理"""

from typing import Optional, Dict, List, Any
from ..ai.providers.base import HTTPBasedProvider, BaseLLMProvider
from ..utils.logger import logger


class _AdvisoryProvider(HTTPBasedProvider):
    """Advisory 专用 Provider - 实现 provider_name 抽象属性"""

    def __init__(self, api_key: str, model: str, base_url: str, timeout: float, name: str):
        super().__init__(api_key=api_key, model=model, base_url=base_url, timeout=timeout)
        self._name = name

    @property
    def provider_name(self) -> str:
        return self._name


def _create_provider(name: str, api_key: str, model: str, base_url: str, timeout: float) -> BaseLLMProvider:
    """根据 provider 名称创建对应实现"""
    if name == "gemini":
        from ..ai.providers.gemini import GeminiProvider
        return GeminiProvider(api_key=api_key, model=model, base_url=base_url, timeout=timeout)
    # openrouter / deepseek / 其他 OpenAI 兼容协议
    return _AdvisoryProvider(api_key=api_key, model=model, base_url=base_url, timeout=timeout, name=name)


class AdvisoryLLMClient:
    """Advisory 独立 LLM 客户端 - 配置由 Dashboard/Redis 提供，不从 .env 读取"""

    def __init__(
        self,
        provider: str,
        api_key: str,
        model: str,
        base_url: str,
        timeout: float = 180.0,
    ):
        if not provider or not model:
            raise ValueError(
                "Advisory LLM 未配置 provider/model，请在 Dashboard Advisory Settings 中配置"
            )

        self._provider_name = provider
        self._api_key = api_key
        self._model = model
        self._base_url = base_url
        self._timeout = max(timeout, 120.0)  # Advisory 分析需要较长时间，最少 120 秒

        self._provider = _create_provider(
            name=self._provider_name,
            api_key=self._api_key,
            model=self._model,
            base_url=self._base_url,
            timeout=self._timeout,
        )

    async def chat(
        self,
        messages: List[Dict[str, str]],
        schema: Optional[Dict[str, Any]] = None,
        max_tokens: int = 4000,
        temperature: float = 0.3,
    ) -> Dict[str, Any]:
        return await self._provider.chat(
            messages=messages, schema=schema,
            max_tokens=max_tokens, temperature=temperature,
        )

    async def close(self):
        await self._provider.close()

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def model_name(self) -> str:
        return self._model
