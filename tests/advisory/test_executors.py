import pytest
from unittest.mock import AsyncMock, MagicMock

from ai_trader.advisory.executors import ConfigExecutor, TradeExecutor, SymbolExecutor, ExecutionResult


@pytest.mark.asyncio
async def test_config_executor_reduce_leverage():
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value='{"enabled": true, "decisionInterval": 1}')
    mock_redis.set = AsyncMock()
    mock_redis.publish = AsyncMock()
    executor = ConfigExecutor(redis_client=mock_redis)
    result = await executor.execute(action="reduce_leverage", target="global", detail={"leverage_max": 5})
    assert result.success is True
    assert "leverage" in result.message.lower()


@pytest.mark.asyncio
async def test_config_executor_adjust_stop_loss():
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value='{}')
    mock_redis.set = AsyncMock()
    mock_redis.publish = AsyncMock()
    executor = ConfigExecutor(redis_client=mock_redis)
    result = await executor.execute(action="adjust_stop_loss", target="global", detail={"stop_loss_percent": 3.0})
    assert result.success is True


@pytest.mark.asyncio
async def test_trade_executor_close_position():
    mock_order_mgr = AsyncMock()
    mock_position_mgr = AsyncMock()
    mock_position = MagicMock()
    mock_position.size = 0.001
    mock_position.side = "long"
    mock_position.leverage = 5
    mock_position_mgr.get_position = AsyncMock(return_value=mock_position)
    executor = TradeExecutor(order_manager=mock_order_mgr, position_manager=mock_position_mgr)
    result = await executor.execute(action="close_position", target="BTC/USDT:USDT", detail={})
    assert result.success is True


@pytest.mark.asyncio
async def test_trade_executor_no_position():
    mock_order_mgr = AsyncMock()
    mock_position_mgr = AsyncMock()
    mock_position_mgr.get_position = AsyncMock(return_value=None)
    executor = TradeExecutor(order_manager=mock_order_mgr, position_manager=mock_position_mgr)
    result = await executor.execute(action="close_position", target="BTC/USDT:USDT", detail={})
    assert result.success is False
