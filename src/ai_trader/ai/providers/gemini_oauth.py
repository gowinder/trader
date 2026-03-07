"""Gemini OAuth Provider - 使用 gemini-cli 的 OAuth token"""

from typing import Optional, Dict, List, Any
import httpx

from .base import BaseLLMProvider
from ..token_manager import get_token_manager
from ...utils.logger import logger


class GeminiOAuthProvider(BaseLLMProvider):
    """Gemini OAuth Provider - 使用本地 OAuth token 调用 Gemini API"""

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
    DEFAULT_MODEL = "gemini-2.0-flash"

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
        token = await self._token_manager.get_token("gemini")
        if not token:
            raise RuntimeError("Gemini OAuth token not available")

        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def _convert_messages_to_gemini_format(
        self, messages: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """将 OpenAI 格式的 messages 转换为 Gemini 格式"""
        contents = []
        system_instruction = None

        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            if role == "system":
                system_instruction = {"parts": [{"text": content}]}
            elif role == "user":
                contents.append({"role": "user", "parts": [{"text": content}]})
            elif role == "assistant":
                contents.append({"role": "model", "parts": [{"text": content}]})

        result = {"contents": contents}
        if system_instruction:
            result["systemInstruction"] = system_instruction

        return result

    def _get_payload(
        self,
        messages: List[Dict[str, str]],
        schema: Optional[Dict[str, Any]] = None,
        max_tokens: int = 2000,
        temperature: float = 0.3,
    ) -> Dict[str, Any]:
        """构建请求 payload"""
        payload = self._convert_messages_to_gemini_format(messages)

        payload["generationConfig"] = {
            "maxOutputTokens": max_tokens,
            "temperature": temperature,
        }

        if schema:
            # Gemini 支持 JSON mode
            payload["generationConfig"]["responseMimeType"] = "application/json"

        return payload

    def _parse_response(
        self, data: Dict[str, Any], schema: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """解析响应"""
        import json
        import re

        # Gemini 响应格式
        candidates = data.get("candidates", [])
        if not candidates:
            raise RuntimeError("No response from Gemini")

        content = candidates[0].get("content", {})
        parts = content.get("parts", [])
        if not parts:
            raise RuntimeError("Empty response from Gemini")

        text = parts[0].get("text", "")

        # 提取 usage 信息
        usage_metadata = data.get("usageMetadata", {})
        usage = {
            "prompt_tokens": usage_metadata.get("promptTokenCount", 0),
            "completion_tokens": usage_metadata.get("candidatesTokenCount", 0),
            "total_tokens": usage_metadata.get("totalTokenCount", 0),
        }

        if schema:
            result = None
            # 尝试解析 JSON
            try:
                result = json.loads(text)
            except json.JSONDecodeError:
                pass

            if result is None:
                # 尝试提取 JSON 代码块
                json_match = re.search(r"```(?:json)?\s*\n?(.+?)\n?```", text, re.DOTALL)
                if json_match:
                    try:
                        result = json.loads(json_match.group(1))
                    except json.JSONDecodeError:
                        pass

            if result is None:
                # 尝试从文本中提取 JSON
                start = text.find("{")
                end = text.rfind("}")
                if start != -1 and end != -1 and end > start:
                    try:
                        result = json.loads(text[start : end + 1])
                    except json.JSONDecodeError:
                        pass

            if result is None:
                logger.error(f"Failed to parse JSON from Gemini response: {text[:200]}...")
                raise RuntimeError("Failed to parse JSON from Gemini response")

            result["_raw_content"] = text
            return result

        return {"content": text, "_raw_content": text, "usage": usage}

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

        url = f"{self.BASE_URL}/models/{self.model}:generateContent"

        try:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return self._parse_response(data, schema)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                # Token 失效，尝试刷新
                logger.warning("Gemini token expired, attempting refresh")
                if await self._token_manager.refresh_token("gemini"):
                    # 重试
                    headers = await self._get_headers()
                    resp = await client.post(url, headers=headers, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    return self._parse_response(data, schema)
                else:
                    self._token_manager.mark_unavailable("gemini")
            raise

    async def close(self):
        """关闭客户端"""
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def provider_name(self) -> str:
        return "gemini"

    def is_available(self) -> bool:
        """检查 provider 是否可用"""
        return self._token_manager.is_available("gemini")
