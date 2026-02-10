"""Advisory 专用 LLM 客户端"""

from typing import Optional, Dict, List, Any
from ..ai.providers.base import HTTPBasedProvider
from ..config import config
from ..utils.logger import logger


class _AdvisoryProvider(HTTPBasedProvider):
    """Advisory 专用 Provider - 实现 provider_name 抽象属性"""

    def __init__(self, api_key: str, model: str, base_url: str, timeout: float, name: str):
        super().__init__(api_key=api_key, model=model, base_url=base_url, timeout=timeout)
        self._name = name

    @property
    def provider_name(self) -> str:
        return self._name


class AdvisoryLLMClient:
    """Advisory 独立 LLM 客户端 - 不使用 LLMManager 调度"""

    def __init__(
        self,
        provider: str = "",
        api_key: str = "",
        model: str = "",
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        self._provider_name = provider or config.advisory_llm_provider
        self._api_key = api_key or config.advisory_llm_api_key or config.llm_api_key or config.openrouter_api_key
        self._model = model or config.advisory_llm_model
        self._base_url = base_url or config.advisory_llm_base_url or "https://openrouter.ai/api/v1"
        self._timeout = timeout if timeout is not None else config.advisory_llm_timeout

        self._provider = _AdvisoryProvider(
            api_key=self._api_key,
            model=self._model,
            base_url=self._base_url,
            timeout=self._timeout,
            name=self._provider_name,
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
