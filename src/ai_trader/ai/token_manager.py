"""OAuth Token 管理器 - 支持多 Provider 的 token 读取和刷新"""

import json
import asyncio
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
import httpx

from ..utils.logger import logger


@dataclass
class TokenInfo:
    """Token 信息"""
    access_token: str
    refresh_token: Optional[str] = None
    expiry_date: Optional[datetime] = None
    token_type: str = "Bearer"
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        """检查 token 是否过期"""
        if self.expiry_date is None:
            return False
        return datetime.now() >= self.expiry_date

    @property
    def expires_soon(self) -> bool:
        """检查 token 是否即将过期（10分钟内）"""
        if self.expiry_date is None:
            return False
        return datetime.now() >= self.expiry_date - timedelta(minutes=10)


class TokenManager:
    """OAuth Token 管理器"""

    # 默认 token 文件路径
    DEFAULT_TOKEN_PATHS = {
        "gemini": "~/.gemini/oauth_creds.json",
        "codex": "~/.codex/auth.json",
        "qwen": "~/.qwen/oauth_creds.json",
        "opencode": "~/.codex/auth.json",  # 复用 codex
    }

    # CLI 刷新命令
    CLI_REFRESH_COMMANDS = {
        "gemini": ["gemini", "auth", "login"],
        "codex": ["codex", "auth"],
        "qwen": ["qwen", "auth", "login"],
    }

    # OAuth 刷新端点
    OAUTH_ENDPOINTS = {
        "gemini": "https://oauth2.googleapis.com/token",
        "qwen": "https://chat.qwen.ai/api/v1/oauth2/token",
    }

    # OAuth client ID (从 CLI 工具中提取)
    OAUTH_CLIENTS = {
        "gemini": {
            "client_id": "681255809395-oo8ft2oprdrn9e3aqf6av3hmdib135j.apps.googleusercontent.com",
            "client_secret": "",  # Google OAuth 不需要 client_secret for installed apps
        },
    }

    def __init__(self, custom_paths: Optional[Dict[str, str]] = None):
        self._tokens: Dict[str, TokenInfo] = {}
        self._token_paths = {**self.DEFAULT_TOKEN_PATHS}
        if custom_paths:
            self._token_paths.update(custom_paths)
        self._unavailable_providers: set = set()
        self._http_client: Optional[httpx.AsyncClient] = None
        self._refresh_task: Optional[asyncio.Task] = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        """获取 HTTP 客户端"""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

    def _expand_path(self, path: str) -> Path:
        """展开路径中的 ~ 符号"""
        return Path(path).expanduser()

    def _load_token_file(self, provider: str) -> Optional[TokenInfo]:
        """从文件加载 token"""
        path = self._token_paths.get(provider)
        if not path:
            return None

        file_path = self._expand_path(path)
        if not file_path.exists():
            logger.warning(f"Token file not found for {provider}: {file_path}")
            return None

        try:
            with open(file_path, "r") as f:
                data = json.load(f)

            return self._parse_token_data(provider, data)
        except Exception as e:
            logger.error(f"Failed to load token for {provider}: {e}")
            return None

    def _parse_token_data(self, provider: str, data: Dict[str, Any]) -> TokenInfo:
        """解析不同格式的 token 数据"""
        # Gemini 和 Qwen 格式类似
        if provider in ("gemini", "qwen"):
            expiry_ms = data.get("expiry_date")
            expiry_date = None
            if expiry_ms:
                expiry_date = datetime.fromtimestamp(expiry_ms / 1000)

            return TokenInfo(
                access_token=data.get("access_token", ""),
                refresh_token=data.get("refresh_token"),
                expiry_date=expiry_date,
                token_type=data.get("token_type", "Bearer"),
                extra=data,
            )

        # Codex/OpenAI 格式
        elif provider in ("codex", "opencode"):
            tokens = data.get("tokens", {})
            access_token = tokens.get("access_token", "")
            refresh_token = tokens.get("refresh_token")

            # Codex token 没有明确的过期时间，但可以从 JWT 解析
            # 暂时设为 None，依赖刷新机制
            return TokenInfo(
                access_token=access_token,
                refresh_token=refresh_token,
                expiry_date=None,
                token_type="Bearer",
                extra=data,
            )

        # 默认格式
        return TokenInfo(
            access_token=data.get("access_token", ""),
            refresh_token=data.get("refresh_token"),
            token_type=data.get("token_type", "Bearer"),
            extra=data,
        )

    async def get_token(self, provider: str) -> Optional[str]:
        """获取有效 token，自动刷新过期的"""
        if provider in self._unavailable_providers:
            return None

        # 检查缓存
        token_info = self._tokens.get(provider)

        # 未缓存则从文件加载
        if token_info is None:
            token_info = self._load_token_file(provider)
            if token_info is None:
                self._unavailable_providers.add(provider)
                return None
            self._tokens[provider] = token_info

        # 检查是否需要刷新
        if token_info.expires_soon:
            success = await self.refresh_token(provider)
            if not success:
                # 刷新失败，尝试重新加载文件（可能 CLI 已刷新）
                token_info = self._load_token_file(provider)
                if token_info and not token_info.is_expired:
                    self._tokens[provider] = token_info
                else:
                    self._unavailable_providers.add(provider)
                    return None

        return self._tokens[provider].access_token

    async def refresh_token(self, provider: str) -> bool:
        """刷新指定 provider 的 token（混合策略）"""
        logger.info(f"Refreshing token for {provider}")

        # 优先尝试 API 刷新
        if await self._refresh_via_api(provider):
            return True

        # API 失败则尝试 CLI
        if await self._refresh_via_cli(provider):
            return True

        logger.error(f"Failed to refresh token for {provider}")
        return False

    async def _refresh_via_api(self, provider: str) -> bool:
        """通过 OAuth API 刷新 token"""
        token_info = self._tokens.get(provider)
        if not token_info or not token_info.refresh_token:
            return False

        endpoint = self.OAUTH_ENDPOINTS.get(provider)
        if not endpoint:
            return False

        client_config = self.OAUTH_CLIENTS.get(provider, {})

        try:
            client = await self._get_http_client()

            if provider == "gemini":
                # Google OAuth 刷新
                data = {
                    "client_id": client_config.get("client_id", ""),
                    "refresh_token": token_info.refresh_token,
                    "grant_type": "refresh_token",
                }
                resp = await client.post(endpoint, data=data)
                resp.raise_for_status()
                new_data = resp.json()

                # 更新 token
                token_info.access_token = new_data["access_token"]
                if "expires_in" in new_data:
                    token_info.expiry_date = datetime.now() + timedelta(
                        seconds=new_data["expires_in"]
                    )

                # 保存到文件
                self._save_token_file(provider, token_info)
                logger.info(f"Token refreshed via API for {provider}")
                return True

            elif provider == "qwen":
                # Qwen OAuth 刷新 (Device Flow)
                data = {
                    "refresh_token": token_info.refresh_token,
                    "grant_type": "refresh_token",
                    "client_id": "f0304373b74a44d2b584a3fb70ca9e56",
                }
                resp = await client.post(endpoint, data=data, headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                })
                resp.raise_for_status()
                new_data = resp.json()

                token_info.access_token = new_data.get("access_token", token_info.access_token)
                if "expiry_date" in new_data:
                    token_info.expiry_date = datetime.fromtimestamp(new_data["expiry_date"] / 1000)

                self._save_token_file(provider, token_info)
                logger.info(f"Token refreshed via API for {provider}")
                return True

        except Exception as e:
            logger.warning(f"API refresh failed for {provider}: {e}")
            return False

        return False

    async def _refresh_via_cli(self, provider: str) -> bool:
        """通过 CLI 命令刷新 token"""
        cmd = self.CLI_REFRESH_COMMANDS.get(provider)
        if not cmd:
            return False

        try:
            # 运行 CLI 命令（非交互式可能失败）
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0:
                # 重新加载 token 文件
                token_info = self._load_token_file(provider)
                if token_info and not token_info.is_expired:
                    self._tokens[provider] = token_info
                    logger.info(f"Token refreshed via CLI for {provider}")
                    return True
            else:
                logger.warning(f"CLI refresh failed for {provider}: {result.stderr}")

        except subprocess.TimeoutExpired:
            logger.warning(f"CLI refresh timeout for {provider}")
        except FileNotFoundError:
            logger.warning(f"CLI not found for {provider}: {cmd[0]}")
        except Exception as e:
            logger.warning(f"CLI refresh error for {provider}: {e}")

        return False

    def _save_token_file(self, provider: str, token_info: TokenInfo):
        """保存 token 到文件"""
        path = self._token_paths.get(provider)
        if not path:
            return

        file_path = self._expand_path(path)

        try:
            # 读取原始数据并更新
            if file_path.exists():
                with open(file_path, "r") as f:
                    data = json.load(f)
            else:
                data = {}

            data["access_token"] = token_info.access_token
            if token_info.expiry_date:
                data["expiry_date"] = int(token_info.expiry_date.timestamp() * 1000)

            with open(file_path, "w") as f:
                json.dump(data, f, indent=2)

        except Exception as e:
            logger.error(f"Failed to save token for {provider}: {e}")

    async def check_and_refresh_all(self):
        """检查并刷新所有即将过期的 token"""
        for provider in self._token_paths.keys():
            if provider in self._unavailable_providers:
                continue

            token_info = self._tokens.get(provider)
            if token_info is None:
                token_info = self._load_token_file(provider)
                if token_info:
                    self._tokens[provider] = token_info

            if token_info and token_info.expires_soon:
                await self.refresh_token(provider)

    def is_available(self, provider: str) -> bool:
        """检查 provider 是否可用"""
        if provider in self._unavailable_providers:
            return False

        # 尝试加载 token
        if provider not in self._tokens:
            token_info = self._load_token_file(provider)
            if token_info:
                self._tokens[provider] = token_info
            else:
                return False

        token_info = self._tokens.get(provider)
        return token_info is not None and not token_info.is_expired

    def mark_unavailable(self, provider: str):
        """标记 provider 为不可用"""
        self._unavailable_providers.add(provider)

    def mark_available(self, provider: str):
        """标记 provider 为可用"""
        self._unavailable_providers.discard(provider)

    async def start_background_refresh(self, interval_minutes: int = 5):
        """启动后台刷新任务"""
        async def refresh_loop():
            while True:
                await asyncio.sleep(interval_minutes * 60)
                try:
                    await self.check_and_refresh_all()
                except Exception as e:
                    logger.error(f"Background token refresh error: {e}")

        self._refresh_task = asyncio.create_task(refresh_loop())
        logger.info(f"Started background token refresh (interval: {interval_minutes}min)")

    async def stop_background_refresh(self):
        """停止后台刷新任务"""
        if self._refresh_task:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
            self._refresh_task = None

    async def close(self):
        """关闭资源"""
        await self.stop_background_refresh()
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None


# 全局单例
_token_manager: Optional[TokenManager] = None


def get_token_manager() -> TokenManager:
    """获取全局 TokenManager 实例"""
    global _token_manager
    if _token_manager is None:
        _token_manager = TokenManager()
    return _token_manager
