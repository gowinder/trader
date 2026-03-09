"""Exchange abstraction base classes and models"""

from abc import ABC, abstractmethod
from typing import List, Optional
from enum import Enum
from pydantic import BaseModel


class OrderSide(str, Enum):
    """Order side enumeration"""

    OPEN_LONG = "open_long"
    OPEN_SHORT = "open_short"
    CLOSE_LONG = "close_long"
    CLOSE_SHORT = "close_short"


class OrderType(str, Enum):
    """Order type enumeration"""

    MARKET = "market"
    LIMIT = "limit"


class Position(BaseModel):
    """Position model compatible with models.order.Position"""

    symbol: str
    side: str  # long / short (lowercase)
    size: float
    entry_price: float
    mark_price: float
    unrealized_pnl: float
    leverage: int
    margin_mode: str  # cross / isolated
    liquidation_price: Optional[float] = None
    margin: float = 0.0  # Margin used for this position
    roi: float = 0.0  # Return on investment percentage


class AccountInfo(BaseModel):
    """Account information model"""

    total_equity: float
    available_balance: float
    margin_used: float
    unrealized_pnl: float


class Ticker(BaseModel):
    """Market ticker snapshot"""

    symbol: str
    last_price: float
    bid_price: float
    ask_price: float
    high_24h: float
    low_24h: float
    volume_24h: float
    change_24h: float
    timestamp: Optional[int] = None


class BaseExchange(ABC):
    """Base exchange abstract class - all exchange implementations must inherit from this"""

    @abstractmethod
    async def get_account(self) -> AccountInfo:
        """Get account information"""
        pass

    @abstractmethod
    async def get_klines(
        self, symbol: str, interval: str = "15m", limit: int = 100
    ) -> List:
        """Get kline/candlestick data

        Returns:
            List of kline data (format defined by implementation)
        """
        pass

    @abstractmethod
    async def get_ticker(self, symbol: str) -> Ticker:
        """Get real-time market ticker"""
        pass

    @abstractmethod
    async def get_positions(self, symbol: str) -> List[Position]:
        """Get position information"""
        pass

    @abstractmethod
    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        """Set leverage multiplier"""
        pass

    @abstractmethod
    async def create_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        size: float,
        price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> dict:
        """Create order

        Returns:
            Order creation result dict
        """
        pass

    @abstractmethod
    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """Cancel order"""
        pass

    async def get_available_symbols(self) -> List[str]:
        """Get all available USDT perpetual contract symbols from the exchange.

        Returns:
            List of symbol strings (e.g., ['BTC/USDT:USDT', 'ETH/USDT:USDT'])
        """
        return []

    @abstractmethod
    async def close(self):
        """Close connection and cleanup resources"""
        pass

    async def __aenter__(self) -> "BaseExchange":
        """Async context manager entry"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()
