#!/usr/bin/env python3
"""Demo: Log translation feature"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from loguru import logger
from ai_trader.utils.translator import enable_chinese_logs

print("=" * 60)
print("日志翻译功能演示")
print("=" * 60)
print()

# 启用中文翻译
print("启用中文翻译...")
enable_chinese_logs()
print()

# 模拟交易系统日志
logger.info("Trading system initialized")
logger.info("Connecting to Binance exchange")
logger.success("Connection established successfully")

logger.info("Loading market data for BTCUSDT")
logger.info("Market analysis started")
logger.info("Market state: STRONG_TREND, ADX: 28.5")

logger.warning("High volatility detected: 3.2%")
logger.info("Signal generated: LONG (confidence: 85%)")

logger.info("Opening position: LONG 0.5 BTC at $50000")
logger.success("Order executed successfully")

logger.info("Position monitoring started")
logger.warning("Price dropped to $49500")
logger.warning("Stop loss triggered")
logger.success("Position closed at $49500")

logger.info("Trade summary: P&L: -$250")
logger.info("System running normally")

print()
print("=" * 60)
print("所有日志消息已自动翻译为中文")
print("=" * 60)
