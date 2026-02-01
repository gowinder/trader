"""CLI Provider - 通过 subprocess 调用 CLI 工具"""

import asyncio
import json
import re
from typing import Optional, Dict, List, Any

from .base import BaseLLMProvider
from ...utils.logger import logger


class CLIProvider(BaseLLMProvider):
    """通用 CLI Provider 基类"""

    CLI_COMMAND: str = ""
    PROVIDER_NAME: str = ""

    def __init__(
        self,
        timeout: float = 120.0,
        **kwargs,
    ):
        self.timeout = timeout
        self.model = kwargs.get("model", "default")

    async def chat(
        self,
        messages: List[Dict[str, str]],
        schema: Optional[Dict[str, Any]] = None,
        max_tokens: int = 2000,
        temperature: float = 0.3,
    ) -> Dict[str, Any]:
        """通过 CLI 发送请求"""
        # 构建 prompt
        prompt = self._build_prompt(messages, schema)

        # 调用 CLI
        result = await self._run_cli(prompt)

        # 解析结果
        if schema:
            return self._parse_json_response(result)

        return {"content": result}

    def _build_prompt(
        self,
        messages: List[Dict[str, str]],
        schema: Optional[Dict[str, Any]] = None
    ) -> str:
        """构建 prompt"""
        parts = []

        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            if role == "system":
                parts.append(f"System: {content}")
            elif role == "user":
                parts.append(content)
            elif role == "assistant":
                parts.append(f"Assistant: {content}")

        prompt = "\n\n".join(parts)

        if schema:
            prompt += "\n\nRespond with valid JSON only, no markdown code blocks."

        return prompt

    async def _run_cli(self, prompt: str) -> str:
        """运行 CLI 命令"""
        cmd = [self.CLI_COMMAND]

        # 通过 stdin 传递 prompt
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(input=prompt.encode()),
                timeout=self.timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            raise RuntimeError(f"{self.PROVIDER_NAME} CLI timeout after {self.timeout}s")

        if process.returncode != 0:
            error_msg = stderr.decode().strip()
            raise RuntimeError(f"{self.PROVIDER_NAME} CLI error: {error_msg}")

        output = stdout.decode().strip()

        # 过滤掉 Node.js 警告和其他噪音
        lines = output.split("\n")
        filtered = []
        for line in lines:
            # 跳过 Node.js 警告
            if "DeprecationWarning" in line or "(Use `node" in line:
                continue
            # 跳过 CLI 初始化消息
            if any(x in line for x in ["Loaded cached", "Hook registry", "Server '", "supports tool"]):
                continue
            filtered.append(line)

        return "\n".join(filtered).strip()

    def _parse_json_response(self, text: str) -> Dict[str, Any]:
        """解析 JSON 响应"""
        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 尝试提取 JSON 代码块
        json_match = re.search(r"```(?:json)?\s*\n?(.+?)\n?```", text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # 尝试从文本中提取 JSON
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass

        logger.error(f"Failed to parse JSON from CLI response: {text[:200]}...")
        raise RuntimeError("Failed to parse JSON from CLI response")

    async def close(self):
        """关闭（无需操作）"""
        pass

    @property
    def provider_name(self) -> str:
        return self.PROVIDER_NAME

    def is_available(self) -> bool:
        """检查 CLI 是否可用"""
        import shutil
        return shutil.which(self.CLI_COMMAND) is not None


class GeminiCLIProvider(CLIProvider):
    """Gemini CLI Provider"""

    CLI_COMMAND = "gemini"
    PROVIDER_NAME = "gemini"

    def __init__(self, model: str = "gemini-2.0-flash", **kwargs):
        super().__init__(**kwargs)
        self.model = model


class QwenCLIProvider(CLIProvider):
    """Qwen CLI Provider"""

    CLI_COMMAND = "qwen"
    PROVIDER_NAME = "qwen"

    def __init__(self, model: str = "qwen-max", **kwargs):
        super().__init__(**kwargs)
        self.model = model
