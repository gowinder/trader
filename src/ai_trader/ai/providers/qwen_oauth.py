"""Qwen OAuth Provider - 使用 qwen-code CLI 的 OAuth token"""

from typing import Optional, Dict, List, Any
import httpx

from .base import BaseLLMProvider
from ..token_manager import get_token_manager
from ...utils.logger import logger


class QwenOAuthProvider(BaseLLMProvider):
    """Qwen OAuth Provider - 使用本地 OAuth token 调用 Qwen API"""

    BASE_URL = "https://portal.qwen.ai/v1"
    DEFAULT_MODEL = "coder-model"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        timeout: float = 60.0,
        base_url: str = "",
        **kwargs,
    ):
        self.model = model
        self.timeout = timeout
        if base_url:
            self.BASE_URL = base_url.rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None
        self._token_manager = get_token_manager()

    async def _get_client(self) -> httpx.AsyncClient:
        """获取 HTTP 客户端"""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def _get_headers(self) -> Dict[str, str]:
        """获取请求头（包含 OAuth token）"""
        token = await self._token_manager.get_token("qwen")
        if not token:
            raise RuntimeError("Qwen OAuth token not available")

        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def _get_payload(
        self,
        messages: List[Dict[str, str]],
        schema: Optional[Dict[str, Any]] = None,
        max_tokens: int = 2000,
        temperature: float = 0.3,
    ) -> Dict[str, Any]:
        """构建请求 payload"""
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }

        if schema:
            # Qwen 支持 JSON mode
            payload["response_format"] = {"type": "json_object"}

        return payload

    def _parse_response(
        self, data: Dict[str, Any], schema: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """解析响应"""
        import json
        import re

        content = data["choices"][0]["message"]["content"]

        # 提取 usage 信息
        usage = data.get("usage", {})

        if schema:
            result = None
            # 尝试解析 JSON
            try:
                result = json.loads(content)
            except json.JSONDecodeError:
                pass

            if result is None:
                # 尝试提取 JSON 代码块
                json_match = re.search(r"```(?:json)?\s*\n?(.+?)\n?```", content, re.DOTALL)
                if json_match:
                    try:
                        result = json.loads(json_match.group(1))
                    except json.JSONDecodeError:
                        pass

            if result is None:
                # 尝试从文本中提取 JSON
                start = content.find("{")
                end = content.rfind("}")
                if start != -1 and end != -1 and end > start:
                    try:
                        result = json.loads(content[start : end + 1])
                    except json.JSONDecodeError:
                        pass

            if result is None:
                logger.error(f"Failed to parse JSON from Qwen response: {content[:200]}...")
                raise RuntimeError("Failed to parse JSON from Qwen response")

            result["_raw_content"] = content
            return result

        return {"content": content, "_raw_content": content, "usage": usage}

    async def chat(
        self,
        messages: List[Dict[str, str]],
        schema: Optional[Dict[str, Any]] = None,
        max_tokens: int = 2000,
        temperature: float = 0.3,
    ) -> Dict[str, Any]:
        """发送聊天请求"""
        client = await self._get_client()
        headers = await self._get_headers()
        payload = self._get_payload(messages, schema, max_tokens, temperature)

        url = f"{self.BASE_URL}/chat/completions"

        try:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return self._parse_response(data, schema)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                # Token 失效，尝试刷新
                logger.warning("Qwen token expired, attempting refresh")
                if await self._token_manager.refresh_token("qwen"):
                    # 重试
                    headers = await self._get_headers()
                    resp = await client.post(url, headers=headers, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    return self._parse_response(data, schema)
                else:
                    self._token_manager.mark_unavailable("qwen")
            raise

    async def close(self):
        """关闭客户端"""
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def provider_name(self) -> str:
        return "qwen"

    def is_available(self) -> bool:
        """检查 provider 是否可用"""
        return self._token_manager.is_available("qwen")
