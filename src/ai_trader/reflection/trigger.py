# src/ai_trader/reflection/trigger.py
"""复盘触发器"""

import asyncio
import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..memory.collector import TradeMemoryCollector
    from .engine import ReflectionEngine

logger = logging.getLogger(__name__)


class ReflectionTrigger:
    """复盘触发器 - 按交易数量触发，后台异步执行"""

    def __init__(
        self,
        collector: "TradeMemoryCollector",
        engine: "ReflectionEngine",
        threshold: int = 10,
    ):
        self.collector = collector
        self.engine = engine
        self.threshold = threshold
        self._running_task: Optional[asyncio.Task] = None

    @property
    def is_running(self) -> bool:
        """检查是否有复盘任务正在运行"""
        return self._running_task is not None and not self._running_task.done()

    async def check_and_run(self) -> bool:
        """检查是否需要触发复盘（非阻塞）

        Returns:
            是否启动了复盘任务
        """
        if self.is_running:
            logger.debug("复盘任务正在运行中，跳过本次触发")
            return False

        count = await self.collector.get_count_since_last_reflection()

        if count < self.threshold:
            logger.debug(f"复盘未触发: {count}/{self.threshold} 笔交易")
            return False

        logger.info(f"触发复盘: 已累计 {count} 笔交易，启动后台任务")
        self._running_task = asyncio.create_task(self._run_reflection_background(count))
        return True

    async def _run_reflection_background(self, count: int) -> Optional[dict]:
        """后台执行复盘"""
        try:
            memories = await self.collector.get_recent(limit=count)
            result = await self.engine.run_reflection(memories)
            logger.info(f"复盘完成: 分析了 {len(memories)} 笔交易")
            return result
        except Exception as e:
            logger.error(f"后台复盘失败: {e}")
            return None
        finally:
            self._running_task = None

    async def wait_for_completion(self, timeout: Optional[float] = None) -> Optional[dict]:
        """等待当前复盘任务完成（用于测试或优雅关闭）"""
        if not self._running_task:
            return None
        try:
            return await asyncio.wait_for(self._running_task, timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("等待复盘完成超时")
            return None
