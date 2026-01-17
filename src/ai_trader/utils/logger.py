"""日志工具模块"""

import sys
from pathlib import Path
from loguru import logger
from ..config import config


def setup_logger():
    """配置日志"""
    log_path = Path(config.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger.remove()

    # 控制台输出 - INFO 级别（简洁）
    logger.add(
        sys.stderr,
        level="INFO",
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    )

    # 文件输出 - DEBUG 级别（详细）
    logger.add(
        log_path,
        rotation="100 MB",
        retention="10 days",
        level="DEBUG",
        encoding="utf-8",
    )


# 初始化日志
try:
    setup_logger()
except Exception:
    pass

__all__ = ["logger"]
