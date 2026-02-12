"""Historical data fetcher with caching"""

import os
from pathlib import Path
from datetime import datetime
from typing import Optional
import pandas as pd
import ccxt
from loguru import logger


class BinanceDataFetcher:
    """Fetch historical data from Binance"""

    def __init__(self, testnet: bool = False, proxy_url: str = ""):
        """Initialize Binance data fetcher

        Args:
            testnet: Whether to use testnet
            proxy_url: HTTP proxy URL (e.g., "http://127.0.0.1:7890")
        """
        config_dict = {
            "enableRateLimit": True,
            "options": {"defaultType": "future"},
        }

        # 添加代理支持
        if proxy_url:
            # 确保 URL 末尾有斜杠
            if not proxy_url.endswith("/"):
                proxy_url = proxy_url + "/"
            config_dict["proxies"] = {
                "http": proxy_url,
                "https": proxy_url,
            }
            logger.info(f"Using proxy: {proxy_url}")

        # 使用 binanceusdm 获取 USDT 期货数据
        self.exchange = ccxt.binanceusdm(config_dict)

        if testnet:
            self.exchange.enable_demo_trading(True)
            logger.info("Using Binance demo trading for data fetching")

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        since: Optional[datetime] = None,
        limit: int = 1000,
    ) -> pd.DataFrame:
        """Fetch OHLCV data

        Args:
            symbol: Trading symbol (e.g., "BTC/USDT")
            timeframe: Timeframe (1m, 5m, 15m, 1h, 4h, 1d)
            since: Start datetime
            limit: Max number of candles to fetch

        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
        """
        try:
            since_ts = None
            if since:
                since_ts = int(since.timestamp() * 1000)

            ohlcv = self.exchange.fetch_ohlcv(
                symbol=symbol,
                timeframe=timeframe,
                since=since_ts,
                limit=limit,
            )

            df = pd.DataFrame(
                ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"]
            )

            # Convert timestamp to datetime
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")

            logger.debug(
                f"Fetched {len(df)} candles for {symbol} {timeframe} "
                f"from {df['timestamp'].iloc[0]} to {df['timestamp'].iloc[-1]}"
            )

            return df

        except Exception as e:
            import traceback
            logger.error(f"Failed to fetch OHLCV data: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    def fetch_historical_data(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        timeframe: str = "1h",
    ) -> pd.DataFrame:
        """Fetch historical data in chunks

        Args:
            symbol: Trading symbol (e.g., "BTC/USDT")
            start_date: Start datetime
            end_date: End datetime
            timeframe: Timeframe

        Returns:
            Complete historical DataFrame
        """
        logger.info(
            f"Fetching {symbol} data from {start_date} to {end_date} ({timeframe})"
        )

        all_data = []
        current_date = start_date
        end_ts = int(end_date.timestamp() * 1000)

        # Calculate chunk size based on timeframe
        timeframe_minutes = self._parse_timeframe(timeframe)
        # Fetch 1000 candles at a time
        chunk_limit = 1000

        while current_date < end_date:
            try:
                df = self.fetch_ohlcv(
                    symbol=symbol,
                    timeframe=timeframe,
                    since=current_date,
                    limit=chunk_limit,
                )

                if df.empty:
                    break

                # Filter data within date range
                df = df[df["timestamp"] <= end_date]
                all_data.append(df)

                # Move to next chunk
                last_ts = int(df["timestamp"].iloc[-1].timestamp() * 1000)
                if last_ts >= end_ts:
                    break

                # Move forward by one timeframe unit
                current_date = df["timestamp"].iloc[-1] + pd.Timedelta(
                    minutes=timeframe_minutes
                )

                logger.debug(f"Fetched {len(all_data)} chunks, total {sum(len(d) for d in all_data)} candles")

            except Exception as e:
                logger.error(f"Error fetching chunk starting at {current_date}: {e}")
                break

        if not all_data:
            raise ValueError("No data fetched")

        # Combine all chunks
        result = pd.concat(all_data, ignore_index=True)

        # Remove duplicates
        result = result.drop_duplicates(subset=["timestamp"], keep="first")

        # Sort by timestamp
        result = result.sort_values("timestamp").reset_index(drop=True)

        logger.info(f"Fetched {len(result)} candles total")

        return result

    def _parse_timeframe(self, timeframe: str) -> int:
        """Parse timeframe to minutes

        Args:
            timeframe: Timeframe string (1m, 5m, 1h, etc.)

        Returns:
            Minutes
        """
        unit = timeframe[-1]
        value = int(timeframe[:-1])

        if unit == "m":
            return value
        elif unit == "h":
            return value * 60
        elif unit == "d":
            return value * 60 * 24
        else:
            raise ValueError(f"Unsupported timeframe: {timeframe}")


class CachedDataFetcher:
    """Data fetcher with file caching"""

    def __init__(self, cache_dir: str = "data/cache", testnet: bool = False, proxy_url: str = ""):
        """Initialize cached data fetcher

        Args:
            cache_dir: Cache directory path
            testnet: Whether to use testnet
            proxy_url: HTTP proxy URL (e.g., "http://127.0.0.1:7890")
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.fetcher = BinanceDataFetcher(testnet=testnet, proxy_url=proxy_url)

    def get_data(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        timeframe: str = "1h",
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        """Get data with caching

        Args:
            symbol: Trading symbol
            start_date: Start datetime
            end_date: End datetime
            timeframe: Timeframe
            force_refresh: Force refresh from API

        Returns:
            Historical data DataFrame
        """
        # Generate cache filename
        cache_file = self._get_cache_filename(symbol, start_date, end_date, timeframe)

        # Check cache
        if not force_refresh and cache_file.exists():
            logger.info(f"Loading cached data from {cache_file}")
            try:
                df = pd.read_pickle(cache_file)
                df["timestamp"] = pd.to_datetime(df["timestamp"])

                # Validate cache
                if self._validate_data(df, start_date, end_date):
                    logger.info(f"Loaded {len(df)} candles from cache")
                    return df
                else:
                    logger.warning("Cached data invalid, fetching fresh data")
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}")

        # Fetch fresh data
        logger.info("Fetching fresh data from Binance")
        df = self.fetcher.fetch_historical_data(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            timeframe=timeframe,
        )

        # Validate fetched data
        if not self._validate_data(df, start_date, end_date):
            logger.error("Fetched data validation failed")
            raise ValueError("Invalid data fetched")

        # Save to cache
        try:
            df.to_pickle(cache_file)
            logger.info(f"Saved {len(df)} candles to cache: {cache_file}")
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")

        return df

    def _get_cache_filename(
        self, symbol: str, start_date: datetime, end_date: datetime, timeframe: str
    ) -> Path:
        """Generate cache filename

        Args:
            symbol: Trading symbol
            start_date: Start datetime
            end_date: End datetime
            timeframe: Timeframe

        Returns:
            Cache file path
        """
        # Convert symbol to safe filename (BTC/USDT -> BTCUSDT)
        safe_symbol = symbol.replace("/", "")

        # Format dates
        start_str = start_date.strftime("%Y%m%d")
        end_str = end_date.strftime("%Y%m%d")

        filename = f"{safe_symbol}_{timeframe}_{start_str}_{end_str}.pkl"
        return self.cache_dir / filename

    def _validate_data(
        self, df: pd.DataFrame, start_date: datetime, end_date: datetime
    ) -> bool:
        """Validate data quality

        Args:
            df: Data DataFrame
            start_date: Expected start date
            end_date: Expected end date

        Returns:
            True if data is valid
        """
        if df.empty:
            logger.error("Data is empty")
            return False

        # Check required columns
        required_cols = ["timestamp", "open", "high", "low", "close", "volume"]
        if not all(col in df.columns for col in required_cols):
            logger.error(f"Missing columns: {set(required_cols) - set(df.columns)}")
            return False

        # Check data range
        data_start = df["timestamp"].iloc[0]
        data_end = df["timestamp"].iloc[-1]

        # Allow some tolerance (1 day)
        tolerance = pd.Timedelta(days=1)

        if data_start > start_date + tolerance:
            logger.warning(
                f"Data starts later than expected: {data_start} > {start_date}"
            )

        if data_end < end_date - tolerance:
            logger.warning(
                f"Data ends earlier than expected: {data_end} < {end_date}"
            )

        # Check for NaN values
        if df[required_cols].isnull().any().any():
            logger.error("Data contains NaN values")
            return False

        # Check OHLC validity
        invalid_ohlc = (
            (df["high"] < df["low"])
            | (df["close"] > df["high"])
            | (df["close"] < df["low"])
            | (df["open"] > df["high"])
            | (df["open"] < df["low"])
        )
        if invalid_ohlc.any():
            logger.error(f"Invalid OHLC data found in {invalid_ohlc.sum()} rows")
            return False

        # Check for zero volume (suspicious)
        zero_volume = (df["volume"] == 0).sum()
        if zero_volume > len(df) * 0.01:  # More than 1% zero volume
            logger.warning(f"High proportion of zero volume: {zero_volume}/{len(df)}")

        logger.debug("Data validation passed")
        return True

    def clear_cache(self, symbol: Optional[str] = None):
        """Clear cache files

        Args:
            symbol: If specified, only clear cache for this symbol
        """
        if symbol:
            safe_symbol = symbol.replace("/", "")
            pattern = f"{safe_symbol}_*.pkl"
        else:
            pattern = "*.pkl"

        cleared = 0
        for cache_file in self.cache_dir.glob(pattern):
            cache_file.unlink()
            cleared += 1

        logger.info(f"Cleared {cleared} cache files")
