"""LLM Provider 抽象基类"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, List, Any
import httpx


class BaseLLMProvider(ABC):
    """LLM Provider 抽象基类"""

    @abstractmethod
    def __init__(self, api_key: str, model: str, **kwargs):
        """初始化 Provider"""
        pass

    @abstractmethod
    async def chat(
        self,
        messages: List[Dict[str, str]],
        schema: Optional[Dict[str, Any]] = None,
        max_tokens: int = 2000,
        temperature: float = 0.3,
    ) -> Dict[str, Any]:
        """发送聊天请求"""
        pass

    @abstractmethod
    async def close(self):
        """关闭客户端"""
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider 名称"""
        pass


class HTTPBasedProvider(BaseLLMProvider):
    """基于 HTTP 的 Provider 基类"""

    def __init__(
        self, api_key: str, model: str, base_url: str, timeout: float = 60.0, **kwargs
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout)
        self._fallback_model: Optional[str] = None

    def _get_headers(self) -> Dict[str, str]:
        """获取请求头 - 子类可重写"""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _get_payload(
        self,
        messages: List[Dict[str, str]],
        schema: Optional[Dict[str, Any]] = None,
        max_tokens: int = 2000,
        temperature: float = 0.3,
    ) -> Dict[str, Any]:
        """构建请求 payload - 子类可重写"""
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "response", "strict": True, "schema": schema},
            }
        return payload

    def _parse_response(
        self, data: Dict[str, Any], schema: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """解析响应 - 子类可重写"""
        import json
        import re

        content = data["choices"][0]["message"]["content"]
        if schema:
            # 首先尝试直接解析
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                pass

            # 尝试提取 JSON 代码块
            json_match = re.search(r"```(?:json)?\s*\n?(.+?)\n?```", content, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group(1))
                except json.JSONDecodeError:
                    pass

            # 尝试从文本中提取 JSON 对象
            # 查找第一个 { 和最后一个 }
            start = content.find("{")
            end = content.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(content[start : end + 1])
                except json.JSONDecodeError:
                    pass

            # 如果都失败了，记录错误并抛出
            import logging

            logging.error(f"Failed to parse JSON from response:")
            logging.error(f"Content: {content[:500]}...")
            raise RuntimeError("Failed to parse JSON from LLM response")
        return {"content": content}

    async def chat(
        self,
        messages: List[Dict[str, str]],
        schema: Optional[Dict[str, Any]] = None,
        max_tokens: int = 2000,
        temperature: float = 0.3,
    ) -> Dict[str, Any]:
        """发送聊天请求"""
        headers = self._get_headers()
        payload = self._get_payload(messages, schema, max_tokens, temperature)

        try:
            url = f"{self.base_url}/chat/completions"
            r = await self._client.post(url, headers=headers, json=payload)
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
                    e, messages, schema, max_tokens, temperature
                )
            raise

    async def _fallback_chat(
        self,
        primary_error: Exception,
        messages: List[Dict[str, str]],
        schema: Optional[Dict[str, Any]] = None,
        max_tokens: int = 2000,
        temperature: float = 0.3,
    ) -> Dict[str, Any]:
        """备用模型请求"""
        import json

        headers = self._get_headers()
        payload = self._get_payload(messages, schema, max_tokens, temperature)
        payload["model"] = self._fallback_model

        try:
            url = f"{self.base_url}/chat/completions"
            r = await self._client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
            return self._parse_response(data, schema)
        except Exception as fallback_error:
            import logging

            logging.error(f"备用模型也失败: {fallback_error}")
            raise RuntimeError(
                f"All LLM models failed: Primary({primary_error}), Fallback({fallback_error})"
            )

    async def close(self):
        await self._client.aclose()
