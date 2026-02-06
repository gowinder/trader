# src/ai_trader/reflection/service.py
"""复盘服务 - 独立进程"""

import asyncio
import json
import logging
from typing import Optional

import redis.asyncio as redis

from ..config import config
from ..persistence.database import DatabaseManager
from ..ai.client import LLMClient
from ..memory import TradeMemoryCollector
from ..optimization import ParameterRegistry
from .engine import ReflectionEngine

logger = logging.getLogger(__name__)


class ReflectionService:
    """复盘服务 - 从 Redis 队列消费任务"""

    QUEUE_NAME = "reflection:tasks"
    RESULT_PREFIX = "reflection:result:"

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        db: Optional[DatabaseManager] = None,
    ):
        self.redis_url = redis_url
        self.redis: Optional[redis.Redis] = None
        self.db = db
        self.engine: Optional[ReflectionEngine] = None
        self.collector: Optional[TradeMemoryCollector] = None
        self._running = False

    async def start(self):
        """启动服务"""
        logger.info("启动复盘服务...")

        # 连接 Redis
        self.redis = redis.from_url(self.redis_url, decode_responses=True)
        await self.redis.ping()
        logger.info("Redis 连接成功")

        # 初始化数据库
        if not self.db:
            self.db = DatabaseManager(config.dashboard_database_url)
            await self.db.connect()

        # 初始化组件
        llm = LLMClient()
        registry = ParameterRegistry()
        self.collector = TradeMemoryCollector(self.db)
        self.engine = ReflectionEngine(llm, self.db, registry)

        self._running = True
        logger.info("复盘服务启动完成，开始监听任务...")

        await self._consume_loop()

    async def stop(self):
        """停止服务"""
        self._running = False
        if self.redis:
            await self.redis.close()
        logger.info("复盘服务已停止")

    async def _consume_loop(self):
        """消费循环"""
        while self._running:
            try:
                # 阻塞等待任务，超时 5 秒
                result = await self.redis.brpop(self.QUEUE_NAME, timeout=5)
                if result:
                    _, task_json = result
                    await self._process_task(task_json)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"消费任务异常: {e}")
                await asyncio.sleep(1)

    async def _process_task(self, task_json: str):
        """处理单个任务"""
        try:
            task = json.loads(task_json)
            task_id = task.get("task_id", "unknown")
            trade_count = task.get("trade_count", config.reflection_trade_count)

            logger.info(f"开始处理复盘任务: {task_id}, 交易数: {trade_count}")

            # 获取交易记忆
            memories = await self.collector.get_recent(limit=trade_count)

            if not memories:
                logger.warning(f"任务 {task_id}: 没有可分析的交易记录")
                await self._save_result(task_id, {"status": "no_data"})
                return

            # 运行复盘
            result = await self.engine.run_reflection(memories)

            # 保存结果到 Redis（供调用方查询）
            await self._save_result(task_id, {
                "status": "completed",
                "result": result,
            })

            logger.info(f"复盘任务完成: {task_id}")

        except Exception as e:
            logger.error(f"处理任务失败: {e}")
            if "task_id" in locals():
                await self._save_result(task_id, {
                    "status": "error",
                    "error": str(e),
                })

    async def _save_result(self, task_id: str, result: dict):
        """保存结果到 Redis，24 小时过期"""
        key = f"{self.RESULT_PREFIX}{task_id}"
        await self.redis.setex(key, 86400, json.dumps(result))


class ReflectionClient:
    """复盘客户端 - 用于发送任务到队列"""

    QUEUE_NAME = "reflection:tasks"
    RESULT_PREFIX = "reflection:result:"

    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self.redis: Optional[redis.Redis] = None

    async def connect(self):
        """连接 Redis"""
        self.redis = redis.from_url(self.redis_url, decode_responses=True)

    async def close(self):
        """关闭连接"""
        if self.redis:
            await self.redis.close()

    async def submit_task(self, task_id: str, trade_count: int) -> bool:
        """提交复盘任务到队列"""
        if not self.redis:
            await self.connect()

        task = {
            "task_id": task_id,
            "trade_count": trade_count,
        }
        await self.redis.lpush(self.QUEUE_NAME, json.dumps(task))
        logger.info(f"已提交复盘任务: {task_id}")
        return True

    async def get_result(self, task_id: str) -> Optional[dict]:
        """获取任务结果"""
        if not self.redis:
            await self.connect()

        key = f"{self.RESULT_PREFIX}{task_id}"
        result = await self.redis.get(key)
        if result:
            return json.loads(result)
        return None


async def main():
    """主入口"""
    import os

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")

    service = ReflectionService(redis_url=redis_url)

    try:
        await service.start()
    except KeyboardInterrupt:
        await service.stop()


if __name__ == "__main__":
    asyncio.run(main())
