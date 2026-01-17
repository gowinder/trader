"""DeepSeek Provider"""

from .base import HTTPBasedProvider
from typing import Optional, Dict, List, Any


class DeepSeekProvider(HTTPBasedProvider):
    """DeepSeek API Provider - OpenAI Compatible"""

    DEFAULT_BASE_URL = "https://api.deepseek.com/v1"

    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-chat",
        fallback_model: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 60.0,
        **kwargs,
    ):
        super().__init__(api_key, model, base_url, timeout, **kwargs)
        self._fallback_model = fallback_model

    @property
    def provider_name(self) -> str:
        return "deepseek"
