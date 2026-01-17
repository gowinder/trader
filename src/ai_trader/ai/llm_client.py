"""OpenRouter LLM 客户端 - 支持结构化输出"""

import json
import httpx
from typing import Optional, Dict, List, Any
from ..config import config
from ..utils.logger import logger


class LLMClient:
    """OpenRouter API 客户端"""

    URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self):
        self.api_key = config.openrouter_api_key
        self.model = config.ai_model
        self.fallback = config.ai_fallback_model
        self._client = httpx.AsyncClient(timeout=60.0)

    async def chat(
        self,
        messages: List[Dict[str, str]],
        schema: Optional[Dict[str, Any]] = None,
        max_tokens: int = 2000,
        temperature: float = 0.3,
    ) -> Dict[str, Any]:
        """发送请求，支持 JSON Schema 结构化输出"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/gowinder/trader",  # Optional for OpenRouter
        }

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        if schema:
            # OpenRouter supports 'response_format' for some models, or we prompt for JSON.
            # Plan uses 'json_schema' type which is OpenAI format.
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "response", "strict": True, "schema": schema},
            }

        try:
            r = await self._client.post(self.URL, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
            content = data["choices"][0]["message"]["content"]

            if schema:
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse JSON: {content}")
                    raise
            return {"content": content}

        except Exception as e:
            logger.warning(f"主模型 {self.model} 失败，尝试备用 {self.fallback}: {e}")

            # Switch to fallback model
            payload["model"] = self.fallback
            try:
                r = await self._client.post(self.URL, headers=headers, json=payload)
                r.raise_for_status()
                data = r.json()
                content = data["choices"][0]["message"]["content"]

                if schema:
                    return json.loads(content)
                return {"content": content}
            except Exception as e2:
                logger.error(f"备用模型也失败: {e2}")
                raise RuntimeError(
                    f"All LLM models failed: Primary({e}), Fallback({e2})"
                )

    async def close(self):
        await self._client.aclose()
