"""OpenRouter LLM client - supports structured output"""

import json
import time
import httpx
from typing import Optional, Dict, List, Any
from ..config import config
from ..utils.logger import logger
from .usage_tracker import get_usage_tracker


class LLMClient:
    """OpenRouter API 客户端"""

    URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self):
        self.api_key = config.openrouter_api_key
        self.model = config.ai_model
        self.fallback = config.ai_fallback_model
        import os
        http_proxy = os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
        self._client = httpx.AsyncClient(timeout=60.0, proxy=http_proxy)

    async def chat(
        self,
        messages: List[Dict[str, str]],
        schema: Optional[Dict[str, Any]] = None,
        max_tokens: int = 2000,
        temperature: float = 0.3,
        usage_type: Optional[str] = None,
        trigger_source: Optional[str] = None,
    ) -> Dict[str, Any]:
        """发送请求，支持 JSON Schema 结构化输出"""
        start_time = time.time()
        self._current_usage_type = usage_type
        self._current_trigger_source = trigger_source or getattr(self, "_cycle_trigger_source", None)
        used_model = self.model
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/gowinder/trader",
        }

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

        try:
            r = await self._client.post(self.URL, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
            content = data["choices"][0]["message"]["content"]

            usage = data.get("usage", {})
            latency_ms = int((time.time() - start_time) * 1000)
            await self._track_usage(used_model, usage, latency_ms, True,
                                    messages=messages, response_content=content)

            if schema:
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse JSON: {content}")
                    raise
            return {"content": content}

        except Exception as e:
            logger.warning(f"主模型 {self.model} 失败，尝试备用 {self.fallback}: {e}")

            used_model = self.fallback
            payload["model"] = self.fallback
            try:
                r = await self._client.post(self.URL, headers=headers, json=payload)
                r.raise_for_status()
                data = r.json()
                content = data["choices"][0]["message"]["content"]

                usage = data.get("usage", {})
                latency_ms = int((time.time() - start_time) * 1000)
                await self._track_usage(used_model, usage, latency_ms, True,
                                        messages=messages, response_content=content)

                if schema:
                    return json.loads(content)
                return {"content": content}
            except Exception as e2:
                latency_ms = int((time.time() - start_time) * 1000)
                await self._track_usage(used_model, {}, latency_ms, False, str(e2),
                                        messages=messages)
                logger.error(f"备用模型也失败: {e2}")
                raise RuntimeError(
                    f"All LLM models failed: Primary({e}), Fallback({e2})"
                )

    async def _track_usage(
        self, model, usage, latency_ms, success, error_message="",
        messages=None, response_content=None,
    ):
        """Record LLM call to UsageTracker"""
        try:
            tracker = get_usage_tracker()
            llm_prompt = json.dumps(messages, ensure_ascii=False) if messages else None
            await tracker.record(
                provider="openrouter",
                model=model,
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
                latency_ms=latency_ms,
                success=success,
                error_message=error_message,
                usage_type=getattr(self, "_current_usage_type", None),
                trigger_source=getattr(self, "_current_trigger_source", None),
                llm_prompt=llm_prompt,
                llm_response=response_content,
            )
        except Exception as e:
            logger.debug(f"Usage tracking failed: {e}")

    async def close(self):
        await self._client.aclose()
