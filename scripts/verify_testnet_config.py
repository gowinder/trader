"""Verify Testnet configuration and connectivity"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ai_trader.config import config
from ai_trader.exchange import create_exchange_client
from ai_trader.utils.logger import logger


async def main():
    """Verify Testnet configuration"""
    logger.info("=" * 60)
    logger.info("🔍 Testnet Configuration Verification")
    logger.info("=" * 60)

    # 1. Check configuration
    logger.info(f"\n📋 Configuration:")
    logger.info(f"  Trading Mode: {config.trading_mode}")
    logger.info(f"  Testnet Exchange: {config.testnet_exchange}")
    logger.info(f"  Trading Symbol: {config.trading_symbol}")
    logger.info(f"  LLM Provider: {config.llm_provider}")
    logger.info(f"  LLM Model: {config.llm_model}")

    if config.trading_mode != "testnet":
        logger.error("❌ TRADING_MODE must be 'testnet'!")
        return False

    # 2. Test exchange connection
    logger.info(f"\n🔌 Testing Exchange Connection...")
    try:
        client = create_exchange_client()
        logger.info(f"✅ Exchange client created: {type(client).__name__}")
    except Exception as e:
        logger.error(f"❌ Failed to create exchange client: {e}")
        return False

    # 3. Test account info
    logger.info(f"\n💰 Testing Account Info...")
    try:
        account = await client.get_account()
        logger.info(f"✅ Account Balance:")
        logger.info(f"  Total Equity: {account.total_equity:.2f} USDT")
        logger.info(f"  Available Balance: {account.available_balance:.2f} USDT")
        logger.info(f"  Margin Used: {account.margin_used:.2f} USDT")
        logger.info(f"  Unrealized PnL: {account.unrealized_pnl:+.2f} USDT")
    except Exception as e:
        logger.error(f"❌ Failed to get account info: {e}")
        await client.close()
        return False

    # 4. Test market data
    logger.info(f"\n📊 Testing Market Data (BTCUSDT)...")
    try:
        ticker = await client.get_ticker("BTCUSDT")
        logger.info(f"✅ Market Data:")
        logger.info(f"  Symbol: {ticker.symbol}")
        logger.info(f"  Last Price: {ticker.last_price:.2f} USDT")
        logger.info(f"  24h High: {ticker.high_24h:.2f} USDT")
        logger.info(f"  24h Low: {ticker.low_24h:.2f} USDT")
        logger.info(f"  24h Volume: {ticker.volume_24h:.2f}")
        logger.info(f"  24h Change: {ticker.change_24h:+.2f}%")
    except Exception as e:
        logger.error(f"❌ Failed to get market data: {e}")
        await client.close()
        return False

    # 5. Test klines
    logger.info(f"\n📈 Testing K-line Data...")
    try:
        klines = await client.get_klines("BTCUSDT", "15m", 10)
        logger.info(f"✅ K-line Data: Fetched {len(klines)} candles")
        if klines:
            latest = klines[-1]
            logger.info(f"  Latest Candle:")
            logger.info(f"    Open: {latest.open:.2f}")
            logger.info(f"    High: {latest.high:.2f}")
            logger.info(f"    Low: {latest.low:.2f}")
            logger.info(f"    Close: {latest.close:.2f}")
            logger.info(f"    Volume: {latest.volume:.2f}")
    except Exception as e:
        logger.error(f"❌ Failed to get k-line data: {e}")
        await client.close()
        return False

    # 6. Test positions
    logger.info(f"\n📍 Testing Position Data...")
    try:
        positions = await client.get_positions("BTCUSDT")
        logger.info(f"✅ Position Data: Found {len(positions)} position(s)")
        for pos in positions:
            logger.info(f"  Position: {pos.side.upper()} {pos.size} @ {pos.entry_price:.2f}")
            logger.info(f"    Unrealized PnL: {pos.unrealized_pnl:+.2f} USDT")
            logger.info(f"    ROI: {pos.roi:+.2f}%")
    except Exception as e:
        logger.error(f"❌ Failed to get position data: {e}")
        await client.close()
        return False

    # Cleanup
    await client.close()

    logger.info(f"\n" + "=" * 60)
    logger.info(f"✅ All Testnet Configuration Checks Passed!")
    logger.info(f"=" * 60)
    return True


if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result else 1)
