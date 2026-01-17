"""程序入口"""

import asyncio
import signal
import sys
from ai_trader.scheduler import Scheduler
from ai_trader.utils.logger import logger


async def main():
    scheduler = Scheduler()
    loop = asyncio.get_event_loop()
    main_task = asyncio.current_task()

    def handle_signal(sig, frame):
        logger.info("Received stop signal, shutting down...")
        # Cancel the main task immediately
        if main_task:
            main_task.cancel()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        await scheduler.start()
    except asyncio.CancelledError:
        logger.info("Main task cancelled")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
    finally:
        await scheduler.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
