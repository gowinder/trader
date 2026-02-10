"""Advisory 建议执行器"""

import json
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

from ..config import config as runtime_config
from ..utils.logger import logger


@dataclass
class ExecutionResult:
    success: bool
    message: str
    detail: Optional[Dict[str, Any]] = field(default=None)


class ConfigExecutor:
    def __init__(self, redis_client):
        self._redis = redis_client

    async def execute(self, action: str, target: str, detail: Dict[str, Any]) -> ExecutionResult:
        try:
            if action == "reduce_leverage":
                return await self._adjust_leverage(detail)
            elif action == "increase_leverage":
                return await self._adjust_leverage(detail)
            elif action == "adjust_stop_loss":
                return await self._adjust_param("stop_loss_percent", detail.get("stop_loss_percent"))
            elif action == "adjust_take_profit":
                return await self._adjust_param("take_profit_percent", detail.get("take_profit_percent"))
            elif action == "adjust_weights":
                return await self._adjust_weights(detail)
            else:
                return ExecutionResult(success=False, message=f"未知的配置操作: {action}")
        except Exception as e:
            logger.error(f"Config execution failed: {e}")
            return ExecutionResult(success=False, message=str(e))

    async def _adjust_leverage(self, detail: Dict) -> ExecutionResult:
        new_max = detail.get("leverage_max")
        if new_max is None:
            return ExecutionResult(success=False, message="缺少 leverage_max 参数")
        config_data = await self._redis.get("trading:config")
        config = json.loads(config_data) if config_data else {"enabled": True, "decisionInterval": runtime_config.decision_interval // 60 if runtime_config.decision_interval >= 60 else 1}
        config["leverage_max"] = new_max
        await self._redis.set("trading:config", json.dumps(config))
        await self._redis.publish("trading:config:updated", json.dumps(config))
        # 同步更新运行时配置
        runtime_config.leverage_max = new_max
        return ExecutionResult(success=True, message=f"Leverage max 已调整为 {new_max}x", detail={"leverage_max": new_max})

    async def _adjust_param(self, param_name: str, value: Any) -> ExecutionResult:
        if value is None:
            return ExecutionResult(success=False, message=f"缺少 {param_name} 参数")
        config_data = await self._redis.get("trading:config")
        config = json.loads(config_data) if config_data else {"enabled": True, "decisionInterval": runtime_config.decision_interval // 60 if runtime_config.decision_interval >= 60 else 1}
        config[param_name] = value
        await self._redis.set("trading:config", json.dumps(config))
        await self._redis.publish("trading:config:updated", json.dumps(config))
        # 同步更新运行时配置
        if hasattr(runtime_config, param_name):
            setattr(runtime_config, param_name, value)
        return ExecutionResult(success=True, message=f"{param_name} 已调整为 {value}", detail={param_name: value})

    async def _adjust_weights(self, detail: Dict) -> ExecutionResult:
        config_data = await self._redis.get("trading:config")
        config = json.loads(config_data) if config_data else {"enabled": True, "decisionInterval": runtime_config.decision_interval // 60 if runtime_config.decision_interval >= 60 else 1}
        updated = {}
        for key in ["quant_weight", "ai_weight", "sentiment_weight"]:
            if key in detail:
                config[key] = detail[key]
                updated[key] = detail[key]
                # 同步更新运行时配置
                if hasattr(runtime_config, key):
                    setattr(runtime_config, key, detail[key])
        await self._redis.set("trading:config", json.dumps(config))
        await self._redis.publish("trading:config:updated", json.dumps(config))
        return ExecutionResult(success=True, message=f"权重已调整: {updated}", detail=updated)


class TradeExecutor:
    def __init__(self, order_manager, position_manager):
        self._order_mgr = order_manager
        self._position_mgr = position_manager

    async def execute(self, action: str, target: str, detail: Dict[str, Any]) -> ExecutionResult:
        try:
            if action == "close_position":
                return await self._close_position(target)
            elif action == "reduce_position":
                return await self._reduce_position(target, detail)
            else:
                return ExecutionResult(success=False, message=f"未知的仓位操作: {action}")
        except Exception as e:
            logger.error(f"Trade execution failed: {e}")
            return ExecutionResult(success=False, message=str(e))

    async def _close_position(self, symbol: str) -> ExecutionResult:
        position = await self._position_mgr.get_position(symbol)
        if not position:
            return ExecutionResult(success=False, message=f"仓位不存在: {symbol}")
        from ..models.decision import TradingDecision
        close_action = "close_long" if position.side == "long" else "close_short"
        decision = TradingDecision(
            action=close_action,
            confidence=100,
            leverage=position.leverage or 1,
            position_size_percent=100,
            reasoning="Advisory system recommended close",
            reasoning_zh="AI顾问系统建议平仓",
        )
        result = await self._order_mgr.execute_order(decision, symbol, position.size)
        if result is None:
            return ExecutionResult(success=False, message=f"平仓下单失败: {symbol}")
        return ExecutionResult(success=True, message=f"已平仓 {symbol} ({position.side}, {position.size})")

    async def _reduce_position(self, symbol: str, detail: Dict) -> ExecutionResult:
        position = await self._position_mgr.get_position(symbol)
        if not position:
            return ExecutionResult(success=False, message=f"仓位不存在: {symbol}")
        reduce_pct = detail.get("reduce_percent", 50) / 100
        reduce_size = position.size * reduce_pct
        from ..models.decision import TradingDecision
        reduce_action = "reduce_long" if position.side == "long" else "reduce_short"
        decision = TradingDecision(
            action=reduce_action,
            confidence=100,
            leverage=position.leverage or 1,
            position_size_percent=reduce_pct * 100,
            reasoning="Advisory system recommended reduce",
            reasoning_zh="AI顾问系统建议减仓",
        )
        result = await self._order_mgr.execute_order(decision, symbol, reduce_size)
        if result is None:
            return ExecutionResult(success=False, message=f"减仓下单失败: {symbol}")
        return ExecutionResult(success=True, message=f"已减仓 {symbol} {reduce_pct*100:.0f}% ({reduce_size})")


class SymbolExecutor:
    def __init__(self, redis_client):
        self._redis = redis_client

    async def execute(self, action: str, target: str, detail: Dict[str, Any]) -> ExecutionResult:
        try:
            if action == "add_symbol":
                return await self._add_symbol(target)
            elif action == "remove_symbol":
                return await self._remove_symbol(target)
            else:
                return ExecutionResult(success=False, message=f"未知的交易对操作: {action}")
        except Exception as e:
            logger.error(f"Symbol execution failed: {e}")
            return ExecutionResult(success=False, message=str(e))

    async def _get_current_symbols(self, config: Dict) -> list:
        """获取当前交易对列表，优先从 Redis config，回退到运行时配置"""
        symbols_str = config.get("trading_symbols", "")
        symbols = [s.strip() for s in symbols_str.split(",") if s.strip()]
        if not symbols:
            symbols = list(runtime_config.symbols_list)
        return symbols

    async def _add_symbol(self, symbol: str) -> ExecutionResult:
        config_data = await self._redis.get("trading:config")
        config = json.loads(config_data) if config_data else {"enabled": True, "decisionInterval": runtime_config.decision_interval // 60 if runtime_config.decision_interval >= 60 else 1}
        symbols = await self._get_current_symbols(config)
        if symbol in symbols:
            return ExecutionResult(success=False, message=f"{symbol} 已在监控列表中")
        symbols.append(symbol)
        config["trading_symbols"] = ",".join(symbols)
        await self._redis.set("trading:config", json.dumps(config))
        await self._redis.publish("trading:config:updated", json.dumps(config))
        return ExecutionResult(success=True, message=f"已添加交易对: {symbol}")

    async def _remove_symbol(self, symbol: str) -> ExecutionResult:
        config_data = await self._redis.get("trading:config")
        config = json.loads(config_data) if config_data else {"enabled": True, "decisionInterval": runtime_config.decision_interval // 60 if runtime_config.decision_interval >= 60 else 1}
        symbols = await self._get_current_symbols(config)
        if symbol not in symbols:
            return ExecutionResult(success=False, message=f"{symbol} 不在监控列表中")
        symbols.remove(symbol)
        config["trading_symbols"] = ",".join(symbols)
        await self._redis.set("trading:config", json.dumps(config))
        await self._redis.publish("trading:config:updated", json.dumps(config))
        return ExecutionResult(success=True, message=f"已移除交易对: {symbol}")
