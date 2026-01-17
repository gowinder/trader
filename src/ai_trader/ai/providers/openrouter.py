"""OpenRouter Provider"""

from .base import HTTPBasedProvider
from typing import Optional, Dict, List, Any


class OpenRouterProvider(HTTPBasedProvider):
    """OpenRouter API Provider"""

    DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(
        self,
        api_key: str,
        model: str,
        fallback_model: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 60.0,
        **kwargs,
    ):
        super().__init__(api_key, model, base_url, timeout, **kwargs)
        self._fallback_model = fallback_model

    def _get_headers(self) -> Dict[str, str]:
        headers = super()._get_headers()
        # OpenRouter requires HTTP-Referer
        headers["HTTP-Referer"] = "https://github.com/gowinder/trader"
        return headers

    @property
    def provider_name(self) -> str:
        return "openrouter"
