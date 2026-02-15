import pytest
from unittest.mock import AsyncMock, MagicMock

from ai_trader.advisory.executors import ConfigExecutor, TradeExecutor, SymbolExecutor, StrategyExecutor, ExecutionResult


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


# ========== LLM 自由格式兼容性测试 ==========

@pytest.mark.asyncio
async def test_trade_executor_reduce_or_close():
    """LLM 返回 reduce_or_close action，从 recommended 提取百分比"""
    mock_order_mgr = AsyncMock()
    mock_position_mgr = AsyncMock()
    mock_position = MagicMock()
    mock_position.size = 1.0
    mock_position.side = "short"
    mock_position.leverage = 3
    mock_position_mgr.get_position = AsyncMock(return_value=mock_position)
    executor = TradeExecutor(order_manager=mock_order_mgr, position_manager=mock_position_mgr)
    result = await executor.execute(
        action="reduce_or_close",
        target="SOL/USDT:USDT",
        detail={
            "urgency": "high",
            "recommended": "立即平掉至少70%，若不想承担逆势风险则直接全平",
            "current_position": "short",
        },
    )
    assert result.success is True


@pytest.mark.asyncio
async def test_trade_executor_protect_profit_scale_out():
    """LLM 返回 protect_profit_and_scale_out，从 scale_out 提取百分比"""
    mock_order_mgr = AsyncMock()
    mock_position_mgr = AsyncMock()
    mock_position = MagicMock()
    mock_position.size = 0.5
    mock_position.side = "long"
    mock_position.leverage = 5
    mock_position_mgr.get_position = AsyncMock(return_value=mock_position)
    executor = TradeExecutor(order_manager=mock_order_mgr, position_manager=mock_position_mgr)
    result = await executor.execute(
        action="protect_profit_and_scale_out",
        target="ETH/USDT:USDT",
        detail={
            "urgency": "medium",
            "scale_out": [{"trigger": "按市价执行", "close_percent": 30}],
            "stop_loss": {"mode": "move_up", "stop_price": 2010},
            "current_position": "long",
        },
    )
    assert result.success is True


@pytest.mark.asyncio
async def test_config_executor_update_config_nested_leverage():
    """LLM 返回 update_config + 嵌套 leverage_max dict"""
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value='{"enabled": true}')
    mock_redis.set = AsyncMock()
    mock_redis.publish = AsyncMock()
    executor = ConfigExecutor(redis_client=mock_redis)
    result = await executor.execute(
        action="update_config",
        target="global",
        detail={
            "urgency": "low",
            "leverage_max": {"to": 5, "from": 10, "reason": "降低杠杆上限"},
        },
    )
    assert result.success is True
    assert "5" in result.message


@pytest.mark.asyncio
async def test_config_executor_unwrap_nested_stop_loss():
    """LLM 返回嵌套 stop_loss_percent dict"""
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value='{}')
    mock_redis.set = AsyncMock()
    mock_redis.publish = AsyncMock()
    executor = ConfigExecutor(redis_client=mock_redis)
    result = await executor.execute(
        action="adjust_stop_loss",
        target="global",
        detail={"stop_loss_percent": {"to": 3.0, "from": 5.0}},
    )
    assert result.success is True


@pytest.mark.asyncio
async def test_trade_executor_close_keyword_fallback():
    """action 含 close 关键词触发平仓"""
    mock_order_mgr = AsyncMock()
    mock_position_mgr = AsyncMock()
    mock_position = MagicMock()
    mock_position.size = 0.1
    mock_position.side = "long"
    mock_position.leverage = 2
    mock_position_mgr.get_position = AsyncMock(return_value=mock_position)
    executor = TradeExecutor(order_manager=mock_order_mgr, position_manager=mock_position_mgr)
    result = await executor.execute(action="close_all_positions", target="BTC/USDT:USDT", detail={"urgency": "high"})
    assert result.success is True
