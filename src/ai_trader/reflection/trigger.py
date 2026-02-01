# src/ai_trader/reflection/trigger.py
"""复盘触发器"""

import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..memory.collector import TradeMemoryCollector
    from .engine import ReflectionEngine

logger = logging.getLogger(__name__)


class ReflectionTrigger:
    """复盘触发器 - 按交易数量触发"""

    def __init__(
        self,
        collector: "TradeMemoryCollector",
        engine: "ReflectionEngine",
        threshold: int = 10,
    ):
        """初始化触发器

        Args:
            collector: 交易记忆收集器
            engine: 复盘引擎
            threshold: 触发复盘的交易数量阈值
        """
        self.collector = collector
        self.engine = engine
        self.threshold = threshold

    async def check_and_run(self) -> Optional[dict]:
        """检查是否需要触发复盘

        Returns:
            复盘结果（如果触发），否则 None
        """
        count = await self.collector.get_count_since_last_reflection()

        if count < self.threshold:
            logger.debug(f"复盘未触发: {count}/{self.threshold} 笔交易")
            return None

        logger.info(f"触发复盘: 已累计 {count} 笔交易")

        # 获取需要分析的交易
        memories = await self.collector.get_recent(limit=count)

        # 运行复盘
        result = await self.engine.run_reflection(memories)

        return result
