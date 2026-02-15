"""Advisory 建议执行器 — 全场景 TDD 测试

覆盖所有 4 种建议类型 × 所有 action × 各种 LLM 输出格式，
特别针对实际执行失败的场景。
"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch

from ai_trader.advisory.executors import (
    ConfigExecutor,
    TradeExecutor,
    SymbolExecutor,
    StrategyExecutor,
    ExecutionResult,
)


# ═══════════════════════════════════════════════════
#  Fixtures
# ═══════════════════════════════════════════════════

def _mock_redis(config: dict | None = None):
    """构建 mock redis，可选初始 config"""
    r = AsyncMock()
    if config is not None:
        r.get = AsyncMock(return_value=json.dumps(config))
    else:
        r.get = AsyncMock(return_value='{"enabled": true, "decisionInterval": 1}')
    r.set = AsyncMock()
    r.publish = AsyncMock()
    return r


def _mock_position(side="long", size=1.0, leverage=3):
    p = MagicMock()
    p.side = side
    p.size = size
    p.leverage = leverage
    p.entry_price = 100.0
    return p


def _mock_trade_executor(position=None):
    order_mgr = AsyncMock()
    pos_mgr = AsyncMock()
    pos_mgr.get_position = AsyncMock(return_value=position)
    return TradeExecutor(order_mgr, pos_mgr)


# ═══════════════════════════════════════════════════
#  1. ConfigExecutor — param_adjust 类型
# ═══════════════════════════════════════════════════

class TestConfigExecutorStopLoss:
    """stop_loss_percent 调整 — 包含实际失败场景"""

    @pytest.mark.asyncio
    async def test_adjust_stop_loss_standard(self):
        """标准 action=adjust_stop_loss + detail 含 stop_loss_percent"""
        executor = ConfigExecutor(_mock_redis())
        result = await executor.execute("adjust_stop_loss", "global", {"stop_loss_percent": 2.5})
        assert result.success is True
        assert "2.5" in result.message

    @pytest.mark.asyncio
    async def test_adjust_stop_loss_via_alias_sl(self):
        """detail 用 sl 别名"""
        executor = ConfigExecutor(_mock_redis())
        result = await executor.execute("adjust_stop_loss", "global", {"sl": 2.5})
        assert result.success is True

    @pytest.mark.asyncio
    async def test_adjust_stop_loss_nested_dict(self):
        """LLM 返回嵌套 dict: {"stop_loss_percent": {"to": 3.0, "from": 5.0}}"""
        executor = ConfigExecutor(_mock_redis())
        result = await executor.execute("adjust_stop_loss", "global",
                                        {"stop_loss_percent": {"to": 3.0, "from": 5.0}})
        assert result.success is True
        assert "3.0" in result.message

    @pytest.mark.asyncio
    async def test_action_adjust_target_stop_loss_percent_with_suggested_value(self):
        """【实际失败场景】action=adjust, target=stop_loss_percent,
        detail={"current_value": 3.5, "suggested_value": 2.5}

        LLM 返回通用 action "adjust"，参数在 target 中，值用 suggested_value。
        """
        executor = ConfigExecutor(_mock_redis())
        result = await executor.execute(
            action="adjust",
            target="stop_loss_percent",
            detail={
                "reason": "...",
                "urgency": "medium",
                "current_value": 3.5,
                "suggested_value": 2.5,
            },
        )
        assert result.success is True
        assert "2.5" in result.message

    @pytest.mark.asyncio
    async def test_action_adjust_target_stop_loss_percent_with_to_value(self):
        """action=adjust, target=stop_loss_percent, detail={"to": 2.5, "from": 3.5}"""
        executor = ConfigExecutor(_mock_redis())
        result = await executor.execute(
            action="adjust",
            target="stop_loss_percent",
            detail={"to": 2.5, "from": 3.5},
        )
        assert result.success is True
        assert "2.5" in result.message

    @pytest.mark.asyncio
    async def test_action_adjust_target_stop_loss_with_value(self):
        """action=adjust, target=stop_loss, detail={"value": 2.0}"""
        executor = ConfigExecutor(_mock_redis())
        result = await executor.execute(
            action="adjust",
            target="stop_loss",
            detail={"value": 2.0},
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_action_modify_stop_loss_keyword_in_action(self):
        """action 中含 stop_loss 关键词"""
        executor = ConfigExecutor(_mock_redis())
        result = await executor.execute("modify_stop_loss", "global", {"stop_loss_percent": 4.0})
        assert result.success is True

    @pytest.mark.asyncio
    async def test_stop_loss_out_of_bounds(self):
        """止损值超出范围 [0.1, 50.0]"""
        executor = ConfigExecutor(_mock_redis())
        result = await executor.execute("adjust_stop_loss", "global", {"stop_loss_percent": 0.01})
        assert result.success is False

        result2 = await executor.execute("adjust_stop_loss", "global", {"stop_loss_percent": 60.0})
        assert result2.success is False

    @pytest.mark.asyncio
    async def test_stop_loss_missing_value_completely(self):
        """detail 中完全没有值"""
        executor = ConfigExecutor(_mock_redis())
        result = await executor.execute("adjust_stop_loss", "global", {"urgency": "medium"})
        assert result.success is False
        assert "缺少" in result.message

    @pytest.mark.asyncio
    async def test_action_tighten_target_stop_loss(self):
        """action=tighten, target=stop_loss_percent 通过通用动词路由"""
        executor = ConfigExecutor(_mock_redis())
        result = await executor.execute(
            action="tighten",
            target="stop_loss_percent",
            detail={"suggested_value": 2.0},
        )
        assert result.success is True


class TestConfigExecutorTakeProfit:
    """take_profit_percent 调整"""

    @pytest.mark.asyncio
    async def test_adjust_take_profit_standard(self):
        executor = ConfigExecutor(_mock_redis())
        result = await executor.execute("adjust_take_profit", "global", {"take_profit_percent": 5.0})
        assert result.success is True

    @pytest.mark.asyncio
    async def test_adjust_take_profit_via_alias_tp(self):
        executor = ConfigExecutor(_mock_redis())
        result = await executor.execute("adjust_take_profit", "global", {"tp": 6.0})
        assert result.success is True

    @pytest.mark.asyncio
    async def test_action_adjust_target_take_profit(self):
        """action=adjust, target=take_profit_percent"""
        executor = ConfigExecutor(_mock_redis())
        result = await executor.execute(
            action="adjust",
            target="take_profit_percent",
            detail={"suggested_value": 8.0},
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_take_profit_out_of_bounds(self):
        executor = ConfigExecutor(_mock_redis())
        result = await executor.execute("adjust_take_profit", "global", {"take_profit_percent": 250.0})
        assert result.success is False


class TestConfigExecutorLeverage:
    """leverage 调整"""

    @pytest.mark.asyncio
    async def test_reduce_leverage(self):
        executor = ConfigExecutor(_mock_redis())
        result = await executor.execute("reduce_leverage", "global", {"leverage_max": 3})
        assert result.success is True
        assert "3" in result.message

    @pytest.mark.asyncio
    async def test_increase_leverage(self):
        executor = ConfigExecutor(_mock_redis())
        result = await executor.execute("increase_leverage", "global", {"leverage_max": 10})
        assert result.success is True

    @pytest.mark.asyncio
    async def test_adjust_leverage(self):
        executor = ConfigExecutor(_mock_redis())
        result = await executor.execute("adjust_leverage", "global", {"leverage_max": 5})
        assert result.success is True

    @pytest.mark.asyncio
    async def test_leverage_nested_dict(self):
        """嵌套 leverage: {"leverage_max": {"to": 5, "from": 10}}"""
        executor = ConfigExecutor(_mock_redis())
        result = await executor.execute("update_config", "global",
                                        {"leverage_max": {"to": 5, "from": 10}})
        assert result.success is True
        assert "5" in result.message

    @pytest.mark.asyncio
    async def test_leverage_alias_max_leverage(self):
        """用 max_leverage 别名"""
        executor = ConfigExecutor(_mock_redis())
        result = await executor.execute("reduce_leverage", "global", {"max_leverage": 3})
        assert result.success is True

    @pytest.mark.asyncio
    async def test_leverage_out_of_bounds(self):
        executor = ConfigExecutor(_mock_redis())
        result = await executor.execute("reduce_leverage", "global", {"leverage_max": 0})
        assert result.success is False

        result2 = await executor.execute("reduce_leverage", "global", {"leverage_max": 25})
        assert result2.success is False

    @pytest.mark.asyncio
    async def test_leverage_missing(self):
        executor = ConfigExecutor(_mock_redis())
        result = await executor.execute("reduce_leverage", "global", {"urgency": "low"})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_action_adjust_target_leverage(self):
        """action=adjust, target=leverage"""
        executor = ConfigExecutor(_mock_redis())
        result = await executor.execute("adjust", "leverage", {"suggested_value": 5})
        assert result.success is True


class TestConfigExecutorWeights:
    """策略权重调整"""

    @pytest.mark.asyncio
    async def test_adjust_weights_all(self):
        executor = ConfigExecutor(_mock_redis())
        result = await executor.execute("adjust_weights", "global",
                                        {"quant_weight": 0.4, "ai_weight": 0.3, "sentiment_weight": 0.3})
        assert result.success is True

    @pytest.mark.asyncio
    async def test_adjust_single_weight(self):
        executor = ConfigExecutor(_mock_redis())
        result = await executor.execute("adjust_weights", "global", {"quant_weight": 0.5})
        assert result.success is True

    @pytest.mark.asyncio
    async def test_weight_out_of_bounds(self):
        executor = ConfigExecutor(_mock_redis())
        result = await executor.execute("adjust_weights", "global", {"quant_weight": 1.5})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_weight_via_detail_key_detection(self):
        """detail 中有 quant_weight 但 action 非 adjust_weights"""
        executor = ConfigExecutor(_mock_redis())
        result = await executor.execute("update_config", "global", {"quant_weight": 0.6})
        assert result.success is True


class TestConfigExecutorCombinedSlTp:
    """同时调整止损止盈的组合 action"""

    @pytest.mark.asyncio
    async def test_adjust_stop_loss_take_profit_via_targets(self):
        executor = ConfigExecutor(_mock_redis())
        result = await executor.execute(
            "adjust_stop_loss_take_profit", "global",
            {
                "targets": [
                    {"parameter": "stop_loss_percent", "proposed": 2.5},
                    {"parameter": "take_profit_percent", "proposed": 8.0},
                ]
            },
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_adjust_stop_loss_take_profit_via_direct_keys(self):
        executor = ConfigExecutor(_mock_redis())
        result = await executor.execute(
            "adjust_stop_loss_take_profit", "global",
            {"stop_loss_percent": 3.0, "take_profit_percent": 7.0},
        )
        assert result.success is True


class TestConfigExecutorGenericActions:
    """通用 action + target/detail 推断"""

    @pytest.mark.asyncio
    async def test_update_config_with_parameter_field(self):
        """detail 中有 parameter 字段指示参数名"""
        executor = ConfigExecutor(_mock_redis())
        result = await executor.execute(
            "update_config", "global",
            {"parameter": "stop_loss_percent", "value": 3.0},
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_targets_list_with_multiple_params(self):
        """targets 列表包含多个参数"""
        executor = ConfigExecutor(_mock_redis())
        result = await executor.execute(
            "update_params", "global",
            {
                "targets": [
                    {"parameter": "stop_loss_percent", "proposed": 2.5},
                    {"parameter": "take_profit_percent", "proposed": 6.0},
                ]
            },
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_unknown_action_unknown_detail(self):
        """完全未知的 action 和 detail"""
        executor = ConfigExecutor(_mock_redis())
        result = await executor.execute("do_something", "unknown", {"foo": "bar"})
        assert result.success is False
        assert "未知" in result.message


class TestConfigExecutorRedisInteraction:
    """验证 Redis 交互正确性"""

    @pytest.mark.asyncio
    async def test_config_saved_to_redis(self):
        redis = _mock_redis()
        executor = ConfigExecutor(redis)
        await executor.execute("adjust_stop_loss", "global", {"stop_loss_percent": 3.0})
        redis.set.assert_called_once()
        saved = json.loads(redis.set.call_args[0][1])
        assert saved["stop_loss_percent"] == 3.0

    @pytest.mark.asyncio
    async def test_config_published_to_redis(self):
        redis = _mock_redis()
        executor = ConfigExecutor(redis)
        await executor.execute("adjust_stop_loss", "global", {"stop_loss_percent": 3.0})
        redis.publish.assert_called_once()
        assert redis.publish.call_args[0][0] == "trading:config:updated"


# ═══════════════════════════════════════════════════
#  2. TradeExecutor — position_action 类型
# ═══════════════════════════════════════════════════

class TestTradeExecutorClose:
    """平仓操作"""

    @pytest.mark.asyncio
    async def test_close_long_position(self):
        executor = _mock_trade_executor(_mock_position("long", 0.5, 3))
        result = await executor.execute("close_position", "BTC/USDT:USDT", {})
        assert result.success is True
        assert "平仓" in result.message

    @pytest.mark.asyncio
    async def test_close_short_position(self):
        executor = _mock_trade_executor(_mock_position("short", 1.0, 5))
        result = await executor.execute("close", "ETH/USDT:USDT", {})
        assert result.success is True

    @pytest.mark.asyncio
    async def test_close_no_position(self):
        executor = _mock_trade_executor(None)
        result = await executor.execute("close_position", "BTC/USDT:USDT", {})
        assert result.success is False
        assert "不存在" in result.message

    @pytest.mark.asyncio
    async def test_close_keyword_fallback_exit(self):
        """action=exit_position 通过关键词兜底"""
        executor = _mock_trade_executor(_mock_position())
        result = await executor.execute("exit_position", "BTC/USDT:USDT", {"urgency": "high"})
        assert result.success is True

    @pytest.mark.asyncio
    async def test_close_keyword_liquidate(self):
        executor = _mock_trade_executor(_mock_position())
        result = await executor.execute("liquidate_immediately", "BTC/USDT:USDT", {"urgency": "high"})
        assert result.success is True


class TestTradeExecutorReduce:
    """减仓操作"""

    @pytest.mark.asyncio
    async def test_reduce_position_standard(self):
        executor = _mock_trade_executor(_mock_position("long", 1.0, 3))
        result = await executor.execute("reduce_position", "BTC/USDT:USDT", {"reduce_percent": 50})
        assert result.success is True
        assert "50%" in result.message

    @pytest.mark.asyncio
    async def test_reduce_position_alias_reduce(self):
        executor = _mock_trade_executor(_mock_position())
        result = await executor.execute("reduce", "BTC/USDT:USDT", {"reduce_percent": 30})
        assert result.success is True

    @pytest.mark.asyncio
    async def test_reduce_default_50_percent(self):
        """不提供 reduce_percent 时默认 50%"""
        executor = _mock_trade_executor(_mock_position())
        result = await executor.execute("reduce_position", "BTC/USDT:USDT", {})
        assert result.success is True

    @pytest.mark.asyncio
    async def test_reduce_invalid_percent(self):
        executor = _mock_trade_executor(_mock_position())
        result = await executor.execute("reduce_position", "BTC/USDT:USDT", {"reduce_percent": 0})
        assert result.success is False

        result2 = await executor.execute("reduce_position", "BTC/USDT:USDT", {"reduce_percent": 150})
        assert result2.success is False

    @pytest.mark.asyncio
    async def test_reduce_from_recommended_text(self):
        """从 recommended 文本提取百分比"""
        executor = _mock_trade_executor(_mock_position("short", 1.0))
        result = await executor.execute(
            "reduce_or_close", "SOL/USDT:USDT",
            {
                "urgency": "high",
                "recommended": "立即平掉至少70%，若不想承担逆势风险则直接全平",
            },
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_reduce_from_scale_out_list(self):
        """从 scale_out 列表提取百分比"""
        executor = _mock_trade_executor(_mock_position("long", 0.5))
        result = await executor.execute(
            "protect_profit_and_scale_out", "ETH/USDT:USDT",
            {
                "urgency": "medium",
                "scale_out": [{"trigger": "市价", "close_percent": 30}],
            },
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_reduce_from_size_change_percent_alias(self):
        """detail 中用 size_change_percent 别名"""
        executor = _mock_trade_executor(_mock_position())
        result = await executor.execute("reduce_position", "BTC/USDT:USDT",
                                        {"size_change_percent": 40})
        assert result.success is True

    @pytest.mark.asyncio
    async def test_reduce_no_position(self):
        executor = _mock_trade_executor(None)
        result = await executor.execute("reduce_position", "BTC/USDT:USDT", {"reduce_percent": 50})
        assert result.success is False


class TestTradeExecutorPartialTakeProfit:
    """部分止盈"""

    @pytest.mark.asyncio
    async def test_partial_take_profit_from_targets(self):
        executor = _mock_trade_executor(_mock_position())
        result = await executor.execute(
            "partial_take_profit", "BTC/USDT:USDT",
            {
                "targets": {
                    "take_profit": [{"price": 50000, "size_percent": 30}],
                },
            },
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_partial_take_profit_default(self):
        executor = _mock_trade_executor(_mock_position())
        result = await executor.execute("partial_take_profit", "BTC/USDT:USDT", {})
        assert result.success is True


class TestTradeExecutorTightenOrExit:
    """收紧止损/退出"""

    @pytest.mark.asyncio
    async def test_tighten_high_urgency_closes(self):
        executor = _mock_trade_executor(_mock_position())
        result = await executor.execute("tighten_stop", "BTC/USDT:USDT", {"urgency": "high"})
        assert result.success is True
        assert "平仓" in result.message

    @pytest.mark.asyncio
    async def test_tighten_medium_urgency_reduces(self):
        executor = _mock_trade_executor(_mock_position())
        result = await executor.execute("tighten_stop", "BTC/USDT:USDT", {"urgency": "medium"})
        assert result.success is True


class TestTradeExecutorHold:
    """持仓不动"""

    @pytest.mark.asyncio
    async def test_hold(self):
        executor = _mock_trade_executor()
        result = await executor.execute("hold", "BTC/USDT:USDT", {})
        assert result.success is True
        assert "保持" in result.message

    @pytest.mark.asyncio
    async def test_hold_aliases(self):
        executor = _mock_trade_executor()
        for action in ("monitor", "wait", "observe", "keep", "maintain", "no_change"):
            result = await executor.execute(action, "BTC/USDT:USDT", {})
            assert result.success is True, f"action={action} should succeed"

    @pytest.mark.asyncio
    async def test_hold_keyword_fallback(self):
        """action 含 hold 关键词"""
        executor = _mock_trade_executor()
        result = await executor.execute("hold_with_protection", "BTC/USDT:USDT", {})
        assert result.success is True


class TestTradeExecutorOpenPosition:
    """开仓操作 — open_long / open_short"""

    @pytest.mark.asyncio
    async def test_open_long_standard(self):
        """【实际失败场景】action=open_long，LLM 建议开多"""
        order_mgr = AsyncMock()
        pos_mgr = AsyncMock()
        pos_mgr.get_position = AsyncMock(return_value=None)  # 无现有仓位
        exchange = AsyncMock()
        ticker = MagicMock()
        ticker.last_price = 69500.0
        exchange.get_ticker = AsyncMock(return_value=ticker)
        account = MagicMock()
        account.available_balance = 10000.0
        exchange.get_account = AsyncMock(return_value=account)

        executor = TradeExecutor(order_mgr, pos_mgr, exchange=exchange)
        result = await executor.execute(
            "open_long", "BTC/USDT:USDT",
            {
                "urgency": "medium",
                "stop_loss": 67300,
                "entry_zone": "69200-69500",
                "take_profit": 73500,
                "suggested_leverage": 3,
                "position_size_percent": 15,
            },
        )
        assert result.success is True
        assert "开多" in result.message or "open_long" in result.message.lower()
        order_mgr.execute_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_open_short_standard(self):
        order_mgr = AsyncMock()
        pos_mgr = AsyncMock()
        pos_mgr.get_position = AsyncMock(return_value=None)
        exchange = AsyncMock()
        ticker = MagicMock()
        ticker.last_price = 3500.0
        exchange.get_ticker = AsyncMock(return_value=ticker)
        account = MagicMock()
        account.available_balance = 10000.0
        exchange.get_account = AsyncMock(return_value=account)

        executor = TradeExecutor(order_mgr, pos_mgr, exchange=exchange)
        result = await executor.execute(
            "open_short", "ETH/USDT:USDT",
            {
                "urgency": "medium",
                "stop_loss": 3600,
                "take_profit": 3200,
                "suggested_leverage": 2,
                "position_size_percent": 10,
            },
        )
        assert result.success is True
        order_mgr.execute_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_open_long_already_has_position(self):
        """已有同方向仓位时应拒绝开新仓"""
        order_mgr = AsyncMock()
        pos_mgr = AsyncMock()
        pos_mgr.get_position = AsyncMock(return_value=_mock_position("long", 0.5))
        exchange = AsyncMock()

        executor = TradeExecutor(order_mgr, pos_mgr, exchange=exchange)
        result = await executor.execute(
            "open_long", "BTC/USDT:USDT",
            {"suggested_leverage": 3, "position_size_percent": 15},
        )
        assert result.success is False
        assert "已有" in result.message

    @pytest.mark.asyncio
    async def test_open_long_no_exchange(self):
        """没有 exchange 时无法开仓"""
        order_mgr = AsyncMock()
        pos_mgr = AsyncMock()
        pos_mgr.get_position = AsyncMock(return_value=None)

        executor = TradeExecutor(order_mgr, pos_mgr)  # 不传 exchange
        result = await executor.execute(
            "open_long", "BTC/USDT:USDT",
            {"suggested_leverage": 3, "position_size_percent": 15},
        )
        assert result.success is False

    @pytest.mark.asyncio
    async def test_open_long_order_failure(self):
        """下单返回 None"""
        order_mgr = AsyncMock()
        order_mgr.execute_order = AsyncMock(return_value=None)
        pos_mgr = AsyncMock()
        pos_mgr.get_position = AsyncMock(return_value=None)
        exchange = AsyncMock()
        ticker = MagicMock()
        ticker.last_price = 69500.0
        exchange.get_ticker = AsyncMock(return_value=ticker)
        account = MagicMock()
        account.available_balance = 10000.0
        exchange.get_account = AsyncMock(return_value=account)

        executor = TradeExecutor(order_mgr, pos_mgr, exchange=exchange)
        result = await executor.execute(
            "open_long", "BTC/USDT:USDT",
            {"suggested_leverage": 3, "position_size_percent": 15},
        )
        assert result.success is False
        assert "失败" in result.message

    @pytest.mark.asyncio
    async def test_open_long_keyword_fallback(self):
        """action 含 open 和 long 关键词"""
        order_mgr = AsyncMock()
        pos_mgr = AsyncMock()
        pos_mgr.get_position = AsyncMock(return_value=None)
        exchange = AsyncMock()
        ticker = MagicMock()
        ticker.last_price = 69500.0
        exchange.get_ticker = AsyncMock(return_value=ticker)
        account = MagicMock()
        account.available_balance = 10000.0
        exchange.get_account = AsyncMock(return_value=account)

        executor = TradeExecutor(order_mgr, pos_mgr, exchange=exchange)
        result = await executor.execute(
            "open_long_position", "BTC/USDT:USDT",
            {"suggested_leverage": 3, "position_size_percent": 10},
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_open_with_default_leverage_and_size(self):
        """不提供 leverage 和 size 时使用默认值"""
        order_mgr = AsyncMock()
        pos_mgr = AsyncMock()
        pos_mgr.get_position = AsyncMock(return_value=None)
        exchange = AsyncMock()
        ticker = MagicMock()
        ticker.last_price = 69500.0
        exchange.get_ticker = AsyncMock(return_value=ticker)
        account = MagicMock()
        account.available_balance = 10000.0
        exchange.get_account = AsyncMock(return_value=account)

        executor = TradeExecutor(order_mgr, pos_mgr, exchange=exchange)
        result = await executor.execute("open_long", "BTC/USDT:USDT", {})
        assert result.success is True


class TestTradeExecutorUnknown:

    @pytest.mark.asyncio
    async def test_unknown_action(self):
        executor = _mock_trade_executor()
        result = await executor.execute("do_something_weird", "BTC/USDT:USDT", {})
        assert result.success is False
        assert "未知" in result.message


class TestTradeExecutorOrderFailure:
    """下单失败场景"""

    @pytest.mark.asyncio
    async def test_close_order_returns_none(self):
        order_mgr = AsyncMock()
        order_mgr.execute_order = AsyncMock(return_value=None)
        pos_mgr = AsyncMock()
        pos_mgr.get_position = AsyncMock(return_value=_mock_position())
        executor = TradeExecutor(order_mgr, pos_mgr)
        result = await executor.execute("close_position", "BTC/USDT:USDT", {})
        assert result.success is False
        assert "失败" in result.message

    @pytest.mark.asyncio
    async def test_reduce_order_returns_none(self):
        order_mgr = AsyncMock()
        order_mgr.execute_order = AsyncMock(return_value=None)
        pos_mgr = AsyncMock()
        pos_mgr.get_position = AsyncMock(return_value=_mock_position())
        executor = TradeExecutor(order_mgr, pos_mgr)
        result = await executor.execute("reduce_position", "BTC/USDT:USDT", {"reduce_percent": 50})
        assert result.success is False


# ═══════════════════════════════════════════════════
#  3. SymbolExecutor — symbol_change 类型
# ═══════════════════════════════════════════════════

class TestSymbolExecutorAdd:

    @pytest.mark.asyncio
    async def test_add_symbol_success(self):
        redis = _mock_redis({"enabled": True, "trading_symbols": "BTC/USDT:USDT,ETH/USDT:USDT"})
        executor = SymbolExecutor(redis)
        result = await executor.execute("add_symbol", "SOL/USDT:USDT", {})
        assert result.success is True
        assert "SOL" in result.message

    @pytest.mark.asyncio
    async def test_add_symbol_already_exists(self):
        redis = _mock_redis({"enabled": True, "trading_symbols": "BTC/USDT:USDT,SOL/USDT:USDT"})
        executor = SymbolExecutor(redis)
        result = await executor.execute("add_symbol", "SOL/USDT:USDT", {})
        assert result.success is False
        assert "已在" in result.message

    @pytest.mark.asyncio
    async def test_add_alias(self):
        redis = _mock_redis({"enabled": True, "trading_symbols": "BTC/USDT:USDT"})
        executor = SymbolExecutor(redis)
        result = await executor.execute("add", "ETH/USDT:USDT", {})
        assert result.success is True

    @pytest.mark.asyncio
    async def test_add_keyword_include(self):
        redis = _mock_redis({"enabled": True, "trading_symbols": "BTC/USDT:USDT"})
        executor = SymbolExecutor(redis)
        result = await executor.execute("include_in_watchlist", "ETH/USDT:USDT", {})
        assert result.success is True


class TestSymbolExecutorRemove:

    @pytest.mark.asyncio
    async def test_remove_symbol_success(self):
        redis = _mock_redis({"enabled": True, "trading_symbols": "BTC/USDT:USDT,SOL/USDT:USDT"})
        executor = SymbolExecutor(redis)
        result = await executor.execute("remove_symbol", "SOL/USDT:USDT", {})
        assert result.success is True
        assert "移除" in result.message

    @pytest.mark.asyncio
    async def test_remove_symbol_not_in_list(self):
        """【实际失败场景】交易对不在监控列表中"""
        redis = _mock_redis({"enabled": True, "trading_symbols": "BTC/USDT:USDT,ETH/USDT:USDT"})
        executor = SymbolExecutor(redis)
        result = await executor.execute("remove", "SOL/USDT:USDT", {})
        assert result.success is False
        assert "不在监控列表中" in result.message

    @pytest.mark.asyncio
    async def test_remove_last_symbol_prevented(self):
        """不能移除最后一个交易对"""
        redis = _mock_redis({"enabled": True, "trading_symbols": "BTC/USDT:USDT"})
        executor = SymbolExecutor(redis)
        result = await executor.execute("remove_symbol", "BTC/USDT:USDT", {})
        assert result.success is False
        assert "最后" in result.message

    @pytest.mark.asyncio
    async def test_remove_keyword_exclude(self):
        redis = _mock_redis({"enabled": True, "trading_symbols": "BTC/USDT:USDT,ETH/USDT:USDT"})
        executor = SymbolExecutor(redis)
        result = await executor.execute("exclude_from_trading", "ETH/USDT:USDT", {})
        assert result.success is True


class TestSymbolExecutorPause:

    @pytest.mark.asyncio
    async def test_pause_symbol(self):
        redis = _mock_redis({"enabled": True, "trading_symbols": "BTC/USDT:USDT,SOL/USDT:USDT"})
        executor = SymbolExecutor(redis)
        result = await executor.execute("pause_trading", "SOL/USDT:USDT",
                                        {"duration_hours": 24, "resume_condition": "价格回到 150 以上"})
        assert result.success is True
        assert "暂停" in result.message
        assert "24" in result.message

    @pytest.mark.asyncio
    async def test_pause_not_in_list(self):
        """不在列表中的视为已暂停"""
        redis = _mock_redis({"enabled": True, "trading_symbols": "BTC/USDT:USDT"})
        executor = SymbolExecutor(redis)
        result = await executor.execute("pause_trading", "SOL/USDT:USDT", {})
        assert result.success is True
        assert "已等同暂停" in result.message

    @pytest.mark.asyncio
    async def test_pause_last_symbol_prevented(self):
        redis = _mock_redis({"enabled": True, "trading_symbols": "BTC/USDT:USDT"})
        executor = SymbolExecutor(redis)
        result = await executor.execute("pause_trading", "BTC/USDT:USDT", {})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_pause_keyword_aliases(self):
        for action in ("skip", "avoid", "suspend"):
            redis = _mock_redis({"enabled": True, "trading_symbols": "BTC/USDT:USDT,ETH/USDT:USDT"})
            executor = SymbolExecutor(redis)
            result = await executor.execute(action, "ETH/USDT:USDT", {})
            assert result.success is True, f"action={action} should succeed"

    @pytest.mark.asyncio
    async def test_pause_keyword_fallback(self):
        redis = _mock_redis({"enabled": True, "trading_symbols": "BTC/USDT:USDT,ETH/USDT:USDT"})
        executor = SymbolExecutor(redis)
        result = await executor.execute("stop_trading_temporarily", "ETH/USDT:USDT", {})
        assert result.success is True


class TestSymbolExecutorHold:

    @pytest.mark.asyncio
    async def test_no_change(self):
        redis = _mock_redis()
        executor = SymbolExecutor(redis)
        result = await executor.execute("no_change", "global", {})
        assert result.success is True
        assert "保持不变" in result.message


class TestSymbolExecutorUnknown:

    @pytest.mark.asyncio
    async def test_unknown_action(self):
        redis = _mock_redis()
        executor = SymbolExecutor(redis)
        result = await executor.execute("do_weird_thing", "BTC/USDT:USDT", {})
        assert result.success is False


class TestSymbolExecutorRedisInteraction:

    @pytest.mark.asyncio
    async def test_add_updates_redis(self):
        redis = _mock_redis({"enabled": True, "trading_symbols": "BTC/USDT:USDT"})
        executor = SymbolExecutor(redis)
        await executor.execute("add_symbol", "ETH/USDT:USDT", {})
        saved = json.loads(redis.set.call_args[0][1])
        assert "ETH/USDT:USDT" in saved["trading_symbols"]
        redis.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_remove_updates_redis(self):
        redis = _mock_redis({"enabled": True, "trading_symbols": "BTC/USDT:USDT,ETH/USDT:USDT"})
        executor = SymbolExecutor(redis)
        await executor.execute("remove_symbol", "ETH/USDT:USDT", {})
        saved = json.loads(redis.set.call_args[0][1])
        assert "ETH/USDT:USDT" not in saved["trading_symbols"]


# ═══════════════════════════════════════════════════
#  4. StrategyExecutor — strategy_change 类型
# ═══════════════════════════════════════════════════

def _make_presets():
    return [
        {"id": 1, "name": "steady_trend", "display_name": "稳健趋势",
         "config_json": '{"enabled_strategies": ["trend_following"]}'},
        {"id": 2, "name": "range_harvest", "display_name": "震荡收割",
         "config_json": '{"enabled_strategies": ["mean_reversion"]}'},
        {"id": 3, "name": "aggressive_trend", "display_name": "激进趋势",
         "config_json": '{"enabled_strategies": ["trend_following", "breakout"]}'},
    ]


class TestStrategyExecutorSwitch:

    @pytest.mark.asyncio
    async def test_switch_preset_success(self):
        svc = AsyncMock()
        svc.get_all_presets = AsyncMock(return_value=_make_presets())
        svc.get_active_preset = AsyncMock(return_value=_make_presets()[0])
        svc.activate_preset = AsyncMock(return_value=True)
        executor = StrategyExecutor(svc, _mock_redis())
        result = await executor.execute("switch_preset", "range_harvest", {"preset_name": "range_harvest"})
        assert result.success is True
        assert "震荡收割" in result.message

    @pytest.mark.asyncio
    async def test_switch_preset_not_found(self):
        svc = AsyncMock()
        svc.get_all_presets = AsyncMock(return_value=_make_presets())
        executor = StrategyExecutor(svc, _mock_redis())
        result = await executor.execute("switch_preset", "nonexistent", {"preset_name": "nonexistent"})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_switch_preset_already_active(self):
        svc = AsyncMock()
        svc.get_all_presets = AsyncMock(return_value=_make_presets())
        svc.get_active_preset = AsyncMock(return_value=_make_presets()[0])
        executor = StrategyExecutor(svc, _mock_redis())
        result = await executor.execute("switch_preset", "steady_trend", {"preset_name": "steady_trend"})
        assert result.success is False
        assert "无需切换" in result.message

    @pytest.mark.asyncio
    async def test_switch_preset_activate_fails(self):
        svc = AsyncMock()
        svc.get_all_presets = AsyncMock(return_value=_make_presets())
        svc.get_active_preset = AsyncMock(return_value=_make_presets()[0])
        svc.activate_preset = AsyncMock(return_value=False)
        executor = StrategyExecutor(svc, _mock_redis())
        result = await executor.execute("switch_preset", "range_harvest", {"preset_name": "range_harvest"})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_switch_target_fallback(self):
        """detail 没有 preset_name 时用 target"""
        svc = AsyncMock()
        svc.get_all_presets = AsyncMock(return_value=_make_presets())
        svc.get_active_preset = AsyncMock(return_value=_make_presets()[0])
        svc.activate_preset = AsyncMock(return_value=True)
        executor = StrategyExecutor(svc, _mock_redis())
        result = await executor.execute("switch_preset", "range_harvest", {})
        assert result.success is True

    @pytest.mark.asyncio
    async def test_change_preset_alias(self):
        svc = AsyncMock()
        svc.get_all_presets = AsyncMock(return_value=_make_presets())
        svc.get_active_preset = AsyncMock(return_value=_make_presets()[0])
        svc.activate_preset = AsyncMock(return_value=True)
        executor = StrategyExecutor(svc, _mock_redis())
        result = await executor.execute("change_preset", "range_harvest", {"preset_name": "range_harvest"})
        assert result.success is True


class TestStrategyExecutorHold:

    @pytest.mark.asyncio
    async def test_no_change(self):
        executor = StrategyExecutor(AsyncMock(), _mock_redis())
        result = await executor.execute("no_change", "global", {})
        assert result.success is True

    @pytest.mark.asyncio
    async def test_hold_aliases(self):
        for action in ("hold", "keep", "maintain"):
            executor = StrategyExecutor(AsyncMock(), _mock_redis())
            result = await executor.execute(action, "global", {})
            assert result.success is True


class TestStrategyExecutorKeywordFallback:

    @pytest.mark.asyncio
    async def test_activate_keyword(self):
        svc = AsyncMock()
        svc.get_all_presets = AsyncMock(return_value=_make_presets())
        svc.get_active_preset = AsyncMock(return_value=_make_presets()[0])
        svc.activate_preset = AsyncMock(return_value=True)
        executor = StrategyExecutor(svc, _mock_redis())
        result = await executor.execute("activate_aggressive", "aggressive_trend",
                                        {"preset_name": "aggressive_trend"})
        assert result.success is True

    @pytest.mark.asyncio
    async def test_stay_keyword(self):
        executor = StrategyExecutor(AsyncMock(), _mock_redis())
        result = await executor.execute("stay_current", "global", {})
        assert result.success is True


class TestStrategyExecutorUnknown:

    @pytest.mark.asyncio
    async def test_unknown_action(self):
        executor = StrategyExecutor(AsyncMock(), _mock_redis())
        result = await executor.execute("weird_thing", "global", {})
        assert result.success is False


# ═══════════════════════════════════════════════════
#  5. Scheduler 级集成测试 — _execute_advisory_suggestion
# ═══════════════════════════════════════════════════

class TestSchedulerSuggestionExecution:
    """模拟 scheduler 从 Redis 队列收到的 task dict，验证端到端流程"""

    @pytest.mark.asyncio
    async def test_param_adjust_stop_loss_with_adjust_action(self):
        """【实际失败场景还原】

        task = {
            "suggestion_id": "...",
            "type": "param_adjust",
            "target": "stop_loss_percent",
            "action": "adjust",
            "detail": {
                "reason": "...",
                "urgency": "medium",
                "current_value": 3.5,
                "suggested_value": 2.5,
            }
        }
        """
        redis = _mock_redis()
        executor = ConfigExecutor(redis)
        result = await executor.execute(
            action="adjust",
            target="stop_loss_percent",
            detail={
                "reason": "近期SOL 3x杠杆交易出现-2.48%的较大单笔亏损",
                "urgency": "medium",
                "current_value": 3.5,
                "suggested_value": 2.5,
            },
        )
        assert result.success is True, f"Expected success but got: {result.message}"
        assert "2.5" in result.message

    @pytest.mark.asyncio
    async def test_symbol_change_remove_not_in_list(self):
        """【实际失败场景还原】

        task = {
            "type": "symbol_change",
            "target": "SOL/USDT:USDT",
            "action": "remove",
            "detail": {"reason": "..."}
        }
        当 SOL 已不在监控列表中时返回失败
        """
        redis = _mock_redis({"enabled": True, "trading_symbols": "BTC/USDT:USDT,ETH/USDT:USDT"})
        executor = SymbolExecutor(redis)
        result = await executor.execute("remove", "SOL/USDT:USDT", {"reason": "..."})
        assert result.success is False
        assert "不在监控列表中" in result.message

    @pytest.mark.asyncio
    async def test_param_adjust_with_standard_keys(self):
        """标准 adjust_stop_loss + 标准 key"""
        redis = _mock_redis()
        executor = ConfigExecutor(redis)
        result = await executor.execute(
            action="adjust_stop_loss",
            target="global",
            detail={"stop_loss_percent": 2.5},
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_position_action_close(self):
        executor = _mock_trade_executor(_mock_position())
        result = await executor.execute("close_position", "BTC/USDT:USDT", {})
        assert result.success is True

    @pytest.mark.asyncio
    async def test_strategy_change(self):
        svc = AsyncMock()
        svc.get_all_presets = AsyncMock(return_value=_make_presets())
        svc.get_active_preset = AsyncMock(return_value=_make_presets()[0])
        svc.activate_preset = AsyncMock(return_value=True)
        executor = StrategyExecutor(svc, _mock_redis())
        result = await executor.execute("switch_preset", "range_harvest", {"preset_name": "range_harvest"})
        assert result.success is True


# ═══════════════════════════════════════════════════
#  6. _extract_value 和辅助方法单元测试
# ═══════════════════════════════════════════════════

class TestConfigExecutorHelpers:

    def test_extract_value_to(self):
        assert ConfigExecutor._extract_value({"to": 5}) == 5

    def test_extract_value_proposed(self):
        assert ConfigExecutor._extract_value({"proposed": 3.0}) == 3.0

    def test_extract_value_suggested(self):
        assert ConfigExecutor._extract_value({"suggested": 2.5}) == 2.5

    def test_extract_value_value(self):
        assert ConfigExecutor._extract_value({"value": 4}) == 4

    def test_extract_value_new_value(self):
        assert ConfigExecutor._extract_value({"new_value": 1.5}) == 1.5

    def test_extract_value_target_value(self):
        assert ConfigExecutor._extract_value({"target_value": 6}) == 6

    def test_extract_value_suggested_value(self):
        """suggested_value 目前不在提取列表中 — 这是 bug 的根因"""
        result = ConfigExecutor._extract_value({"suggested_value": 2.5})
        # 这个测试应该发现 suggested_value 不被识别
        # 如果返回 None 说明需要修复
        assert result == 2.5

    def test_extract_value_none(self):
        assert ConfigExecutor._extract_value({"foo": "bar"}) is None

    def test_extract_value_string_ignored(self):
        """字符串值应被忽略"""
        assert ConfigExecutor._extract_value({"to": "some text"}) is None

    def test_unwrap_nested(self):
        d = {"leverage_max": {"to": 5, "from": 10}}
        ConfigExecutor._unwrap_nested_values(d)
        assert d["leverage_max"] == 5

    def test_detect_param_from_detail(self):
        executor = ConfigExecutor(AsyncMock())
        assert executor._detect_param_from_detail({"stop_loss_percent": 3.0}) == "stop_loss_percent"
        assert executor._detect_param_from_detail({"sl": 3.0}) == "stop_loss_percent"
        assert executor._detect_param_from_detail({"leverage": 5}) == "leverage_max"
        assert executor._detect_param_from_detail({"foo": "bar"}) is None

    def test_detect_param_from_target(self):
        executor = ConfigExecutor(AsyncMock())
        assert executor._detect_param_from_target("stop_loss_percent") == "stop_loss_percent"
        assert executor._detect_param_from_target("stop_loss") == "stop_loss_percent"
        assert executor._detect_param_from_target("leverage") == "leverage_max"
        assert executor._detect_param_from_target("take_profit") == "take_profit_percent"
        assert executor._detect_param_from_target("unknown") is None


class TestTradeExecutorNormalizeReducePercent:

    def test_standard_reduce_percent(self):
        d = {"reduce_percent": 50}
        TradeExecutor._normalize_reduce_percent(d)
        assert d["reduce_percent"] == 50

    def test_alias_size_change_percent(self):
        d = {"size_change_percent": 40}
        TradeExecutor._normalize_reduce_percent(d)
        assert d["reduce_percent"] == 40

    def test_from_recommended_text(self):
        d = {"recommended": "减仓70%以控制风险"}
        TradeExecutor._normalize_reduce_percent(d)
        assert d["reduce_percent"] == 70

    def test_from_scale_out(self):
        d = {"scale_out": [{"close_percent": 30}, {"close_percent": 20}]}
        TradeExecutor._normalize_reduce_percent(d)
        assert d["reduce_percent"] == 50

    def test_no_percent_found(self):
        d = {"urgency": "high"}
        TradeExecutor._normalize_reduce_percent(d)
        assert "reduce_percent" not in d
