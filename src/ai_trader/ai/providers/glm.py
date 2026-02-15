"""GLM (智谱AI) Provider - 使用 Anthropic 协议"""

from typing import Optional, Dict, List, Any
import httpx
import json


class GLMProvider:
    """智谱AI GLM API Provider - Anthropic 协议兼容"""

    DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/anthropic"

    def __init__(
        self,
        api_key: str,
        model: str = "glm-4",
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

    @property
    def provider_name(self) -> str:
        return "glm"

    def _extract_usage(self, data: Dict[str, Any]) -> Dict[str, int]:
        """从 Anthropic 协议响应中提取 usage 信息"""
        usage = data.get("usage", {})
        return {
            "prompt_tokens": usage.get("input_tokens", 0),
            "completion_tokens": usage.get("output_tokens", 0),
            "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
        }

    def _format_messages(
        self, messages: List[Dict[str, str]]
    ) -> tuple[str, List[Dict[str, Any]]]:
        """将 OpenAI 格式的消息转换为 Anthropic 格式

        Returns:
            system_prompt: 系统提示（如果有）
            formatted_messages: 格式化后的消息列表
        """
        system_prompt = ""
        formatted = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                system_prompt = content
            elif role == "user":
                formatted.append({"role": "user", "content": content})
            elif role == "assistant":
                formatted.append({"role": "assistant", "content": content})

        return system_prompt, formatted

    def _parse_response(
        self, data: Dict[str, Any], schema: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """解析 Anthropic 响应"""
        try:
            content_blocks = data.get("content", [])
            # 获取第一个 text block 的内容
            text_content = ""
            for block in content_blocks:
                if block.get("type") == "text":
                    text_content = block.get("text", "")
                    break

            if not text_content:
                raise RuntimeError("No text content in response")

            # 清理 content (移除 markdown 代码块标记)
            if isinstance(text_content, str):
                if text_content.startswith("```json"):
                    text_content = text_content[7:]
                elif text_content.startswith("```"):
                    text_content = text_content[3:]
                if text_content.endswith("```"):
                    text_content = text_content[:-3]
                text_content = text_content.strip()

            if schema:
                try:
                    return json.loads(text_content)
                except json.JSONDecodeError:
                    import logging

                    logging.error(f"Failed to parse JSON: {text_content}")
                    raise
            return {"content": text_content}
        except (KeyError, IndexError) as e:
            raise RuntimeError(f"Invalid GLM response format: {e}")

    async def chat(
        self,
        messages: List[Dict[str, str]],
        schema: Optional[Dict[str, Any]] = None,
        max_tokens: int = 2000,
        temperature: float = 0.3,
    ) -> Dict[str, Any]:
        """发送聊天请求 (Anthropic 协议)"""
        system_prompt, formatted_messages = self._format_messages(messages)

        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }

        body = {
            "model": self.model,
            "messages": formatted_messages,
            "max_tokens": min(max_tokens, 4096),  # GLM 限制
            "temperature": min(max(temperature, 0.0), 1.0),  # 限制范围
        }

        if system_prompt:
            body["system"] = system_prompt

        # 如果有 schema，添加到请求中
        if schema:
            # Anthropic 不直接支持 JSON schema，但可以通过提示引导
            # 这里不做特殊处理，让模型自行解析
            pass

        try:
            url = f"{self.base_url}/v1/messages"
            import logging

            logging.debug(f"GLM 请求: {url}")
            logging.debug(f"GLM body: {body}")
            r = await self._client.post(url, headers=headers, json=body)
            logging.debug(f"GLM 响应状态: {r.status_code}")
            if not r.is_success:
                logging.error(f"GLM 响应内容: {r.text[:500]}")
            r.raise_for_status()
            data = r.json()
            usage = self._extract_usage(data)
            result = self._parse_response(data, schema)
            if isinstance(result, dict) and "usage" not in result:
                result["usage"] = usage
            return result

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
        system_prompt, formatted_messages = self._format_messages(messages)

        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }

        body = {
            "model": self._fallback_model,
            "messages": formatted_messages,
            "max_tokens": min(max_tokens, 4096),
            "temperature": min(max(temperature, 0.0), 1.0),
        }

        if system_prompt:
            body["system"] = system_prompt

        try:
            url = f"{self.base_url}/v1/messages"
            import logging

            logging.debug(f"GLM Fallback 请求: {url}")
            logging.debug(f"GLM Fallback body: {body}")
            r = await self._client.post(url, headers=headers, json=body)
            logging.debug(f"GLM Fallback 响应状态: {r.status_code}")
            if not r.is_success:
                logging.error(f"GLM Fallback 响应内容: {r.text[:500]}")
            r.raise_for_status()
            data = r.json()
            usage = self._extract_usage(data)
            result = self._parse_response(data, schema)
            if isinstance(result, dict) and "usage" not in result:
                result["usage"] = usage
            return result
        except Exception as fallback_error:
            import logging

            logging.error(f"备用模型也失败: {fallback_error}")
            raise RuntimeError(
                f"All LLM models failed: Primary({primary_error}), Fallback({fallback_error})"
            )

    async def close(self):
        await self._client.aclose()
