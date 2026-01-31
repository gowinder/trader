"""数据库连接管理"""

from typing import Optional
import asyncpg
from contextlib import asynccontextmanager

from ..utils.logger import logger


class DatabaseManager:
    """PostgreSQL 数据库连接管理器"""

    def __init__(self, database_url: str):
        """初始化数据库管理器

        Args:
            database_url: PostgreSQL 连接 URL
                格式: postgresql://user:password@host:port/database
        """
        self.database_url = database_url
        self._pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        """建立数据库连接池"""
        if self._pool is not None:
            return

        try:
            self._pool = await asyncpg.create_pool(
                self.database_url,
                min_size=2,
                max_size=10,
                command_timeout=60,
            )
            logger.info("数据库连接池已建立")
        except Exception as e:
            logger.error(f"数据库连接失败: {e}")
            raise

    async def close(self) -> None:
        """关闭数据库连接池"""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            logger.info("数据库连接池已关闭")

    @property
    def pool(self) -> asyncpg.Pool:
        """获取连接池"""
        if self._pool is None:
            raise RuntimeError("数据库未连接，请先调用 connect()")
        return self._pool

    @asynccontextmanager
    async def acquire(self):
        """获取数据库连接"""
        async with self.pool.acquire() as conn:
            yield conn

    @asynccontextmanager
    async def transaction(self):
        """事务上下文"""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                yield conn

    async def execute(self, query: str, *args) -> str:
        """执行 SQL 语句"""
        async with self.acquire() as conn:
            return await conn.execute(query, *args)

    async def fetch(self, query: str, *args) -> list:
        """查询多行数据"""
        async with self.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args) -> Optional[asyncpg.Record]:
        """查询单行数据"""
        async with self.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetchval(self, query: str, *args):
        """查询单个值"""
        async with self.acquire() as conn:
            return await conn.fetchval(query, *args)
