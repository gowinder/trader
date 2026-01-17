"""Gemini Provider (Google AI)"""

from .base import BaseLLMProvider
from typing import Optional, Dict, List, Any
import httpx
import json


class GeminiProvider(BaseLLMProvider):
    """Google Gemini API Provider"""

    # Google AI API base URL
    DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-1.5-flash",
        fallback_model: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 60.0,
        **kwargs,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._fallback_model = fallback_model
        self._client = httpx.AsyncClient(timeout=timeout)

    def _format_messages(self, messages: List[Dict[str, str]]) -> str:
        """将消息格式化为 Gemini 格式"""
        parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            # Gemini 使用不同的 role 映射
            if role == "system":
                parts.append(
                    {"role": "user", "parts": [{"text": f"SYSTEM: {content}"}]}
                )
            else:
                parts.append({"role": role, "parts": [{"text": content}]})
        return {"contents": parts}

    def _get_url(self) -> str:
        """获取请求 URL"""
        return f"{self.base_url}/models/{self.model}:generateContent"

    def _parse_response(
        self, data: Dict[str, Any], schema: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """解析 Gemini 响应"""
        try:
            candidate = data["candidates"][0]
            content = candidate["content"]["parts"][0]["text"]

            # 清理 content (移除 markdown 代码块标记)
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            if schema:
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    import logging

                    logging.error(f"Failed to parse JSON: {content}")
                    raise
            return {"content": content}
        except (KeyError, IndexError) as e:
            raise RuntimeError(f"Invalid Gemini response format: {e}")

    async def chat(
        self,
        messages: List[Dict[str, str]],
        schema: Optional[Dict[str, Any]] = None,
        max_tokens: int = 2000,
        temperature: float = 0.3,
    ) -> Dict[str, Any]:
        """发送聊天请求"""
        headers = {
            "Content-Type": "application/json",
        }

        body = self._format_messages(messages)

        # 添加 generation parameters
        body["generationConfig"] = {
            "maxOutputTokens": max_tokens,
            "temperature": temperature,
            "topP": 0.95,
        }

        # 如果有 schema，添加到请求中
        # Gemini 使用 responseMimeType 来强制 JSON 输出
        if schema:
            body["generationConfig"]["responseMimeType"] = "application/json"

        params = {"key": self.api_key}

        try:
            url = self._get_url()
            r = await self._client.post(url, headers=headers, params=params, json=body)
            r.raise_for_status()
            data = r.json()
            return self._parse_response(data, schema)

        except Exception as e:
            if self._fallback_model:
                import logging

                logging.warning(
                    f"主模型 {self.model} 失败，尝试备用 {self._fallback_model}: {e}"
                )
                return await self._fallback_chat(
                    messages, schema, max_tokens, temperature
                )
            raise

    async def _fallback_chat(
        self,
        messages: List[Dict[str, str]],
        schema: Optional[Dict[str, Any]] = None,
        max_tokens: int = 2000,
        temperature: float = 0.3,
    ) -> Dict[str, Any]:
        """备用模型请求"""
        import logging

        headers = {"Content-Type": "application/json"}
        body = self._format_messages(messages)
        body["generationConfig"] = {
            "maxOutputTokens": max_tokens,
            "temperature": temperature,
            "topP": 0.95,
        }
        if schema:
            body["generationConfig"]["responseMimeType"] = "application/json"

        # 使用备用模型
        fallback_url = f"{self.base_url}/models/{self._fallback_model}:generateContent"
        params = {"key": self.api_key}

        try:
            r = await self._client.post(
                fallback_url, headers=headers, params=params, json=body
            )
            r.raise_for_status()
            data = r.json()
            return self._parse_response(data, schema)
        except Exception as e2:
            logging.error(f"备用模型也失败: {e2}")
            raise RuntimeError(f"All LLM models failed: Primary({e}), Fallback({e2})")

    async def close(self):
        await self._client.aclose()

    @property
    def provider_name(self) -> str:
        return "gemini"
