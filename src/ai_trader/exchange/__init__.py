"""Exchange module - factory function for creating exchange clients"""

from typing import Optional
from .base import BaseExchange
from .ccxt_adapter import CCXTAdapter
from .weex_client import WeexClient
from .binance_adapter import BinanceAdapter
from ..config import config
from ..utils.logger import logger


def create_exchange_client() -> BaseExchange:
    """Create exchange client instance based on configuration

    Automatically selects appropriate implementation based on config:
    - testnet mode: Uses dedicated adapters for testnet exchanges
    - live mode: Uses CCXT or native implementation based on use_ccxt config

    Returns:
        BaseExchange: Exchange client instance

    Raises:
        ValueError: If exchange is not supported or configuration is invalid
    """
    # Testnet only allows exchanges with dedicated adapters or explicit support
    SUPPORTED_TESTNET_EXCHANGES = ["binance", "bybit"]

    if config.trading_mode == "testnet":
        exchange = config.testnet_exchange.lower()
        logger.info(f"Creating Testnet client: {exchange}")

        if exchange not in SUPPORTED_TESTNET_EXCHANGES:
            raise ValueError(
                f"Testnet mode does not support {exchange}. "
                f"Supported exchanges: {SUPPORTED_TESTNET_EXCHANGES}. "
                f"Please use live mode or switch to a supported exchange."
            )

        # Use dedicated adapters for better testnet/demo support
        if exchange == "binance":
            # Binance futures uses demo trading mode (testnet deprecated)
            # Demo trading uses real Binance API keys from demo.binance.com
            return BinanceAdapter(
                api_key=config.testnet_api_key,
                api_secret=config.testnet_api_secret,
                testnet=True,
                proxy=None,
            )
        elif exchange == "bybit":
            # Bybit uses CCXT adapter with custom testnet URL
            return CCXTAdapter.from_config(
                exchange_id="bybit",
                api_key=config.testnet_api_key,
                api_secret=config.testnet_api_secret,
                testnet=True,
                proxy=config.proxy_url or None,
            )
        else:
            raise ValueError(f"No testnet implementation for {exchange}")

    # Live mode - use independent credentials for each exchange
    exchange_type = config.exchange_type
    creds = config.get_exchange_credentials(exchange_type)

    if exchange_type == "weex":
        if config.use_ccxt:
            try:
                return CCXTAdapter.from_config(
                    exchange_id="weex",
                    api_key=creds["api_key"],
                    api_secret=creds["api_secret"],
                    passphrase=creds.get("passphrase"),
                    testnet=False,
                    proxy=config.proxy_url or None,
                )
            except ValueError as e:
                logger.warning(f"CCXT does not support WEEX: {e}, falling back to native implementation")
                return WeexClient()
        else:
            return WeexClient()

    # Other exchanges use CCXT adapter with independent credentials
    return CCXTAdapter.from_config(
        exchange_id=exchange_type,
        api_key=creds["api_key"],
        api_secret=creds["api_secret"],
        passphrase=creds.get("passphrase"),
        testnet=False,
        proxy=config.proxy_url or None,
    )


# Export public API
__all__ = [
    "BaseExchange",
    "CCXTAdapter",
    "WeexClient",
    "BinanceAdapter",
    "create_exchange_client",
]
