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
            # 先尝试精确匹配 action
            if action in ("reduce_leverage", "increase_leverage", "adjust_leverage"):
                return await self._adjust_leverage(detail)
            elif action == "adjust_stop_loss":
                return await self._adjust_param("stop_loss_percent", detail.get("stop_loss_percent"))
            elif action == "adjust_take_profit":
                return await self._adjust_param("take_profit_percent", detail.get("take_profit_percent"))
            elif action == "adjust_weights":
                return await self._adjust_weights(detail)

            # 处理组合 action（如 adjust_stop_loss_take_profit）
            # LLM 可能将多个参数放在 targets 列表或直接放在 detail 中
            if "stop_loss" in action and "take_profit" in action:
                return await self._adjust_combined_sl_tp(detail)

            # 智能路由：根据 detail 中的参数名或 parameter 字段自动识别
            param_name = detail.get("parameter", "")
            # 杠杆相关
            if param_name == "leverage_max" or "leverage_max" in detail:
                val = detail.get("proposed") or detail.get("to") or detail.get("leverage_max")
                if val is not None:
                    detail["leverage_max"] = val
                return await self._adjust_leverage(detail)
            # 止损
            if param_name == "stop_loss_percent" or "stop_loss_percent" in detail:
                val = detail.get("proposed") or detail.get("to") or detail.get("stop_loss_percent")
                return await self._adjust_param("stop_loss_percent", val)
            # 止盈
            if param_name == "take_profit_percent" or "take_profit_percent" in detail:
                val = detail.get("proposed") or detail.get("to") or detail.get("take_profit_percent")
                return await self._adjust_param("take_profit_percent", val)
            # 权重相关
            weight_keys = {"quant_weight", "ai_weight", "sentiment_weight"}
            if param_name in weight_keys or (weight_keys & set(detail.keys())):
                # 将 parameter=xxx, proposed=yyy 格式转为 {xxx: yyy}
                if param_name in weight_keys and "proposed" in detail:
                    detail[param_name] = detail["proposed"]
                elif param_name in weight_keys and "to" in detail:
                    detail[param_name] = detail["to"]
                return await self._adjust_weights(detail)

            # 通用兜底：尝试从 targets 列表逐个解析参数
            targets = detail.get("targets", [])
            if isinstance(targets, list) and targets:
                results = []
                for t in targets:
                    if not isinstance(t, dict):
                        continue
                    p = t.get("parameter", "")
                    v = t.get("proposed") or t.get("to") or t.get("value")
                    if p and v is not None:
                        if "stop_loss" in p:
                            r = await self._adjust_param("stop_loss_percent", v)
                        elif "take_profit" in p:
                            r = await self._adjust_param("take_profit_percent", v)
                        elif "leverage" in p:
                            detail["leverage_max"] = v
                            r = await self._adjust_leverage(detail)
                        elif p in weight_keys:
                            r = await self._adjust_param(p, v)
                        else:
                            continue
                        results.append(r.message)
                        if not r.success:
                            return r
                if results:
                    return ExecutionResult(success=True, message=" | ".join(results))

            return ExecutionResult(success=False, message=f"未知的配置操作: {action}, detail keys: {list(detail.keys())}")
        except Exception as e:
            logger.error(f"Config execution failed: {e}")
            return ExecutionResult(success=False, message=str(e))

    async def _adjust_combined_sl_tp(self, detail: Dict) -> ExecutionResult:
        """处理同时调整止损止盈的组合 action"""
        sl_val = None
        tp_val = None

        # 优先从 targets 列表提取
        targets = detail.get("targets", [])
        if isinstance(targets, list):
            for t in targets:
                if isinstance(t, dict):
                    param = t.get("parameter", "")
                    val = t.get("proposed") or t.get("to") or t.get("value")
                    if "stop_loss" in param:
                        sl_val = val
                    elif "take_profit" in param:
                        tp_val = val

        # 回退：直接从 detail 提取
        if sl_val is None:
            sl_val = detail.get("stop_loss_percent") or detail.get("stop_loss")
        if tp_val is None:
            tp_val = detail.get("take_profit_percent") or detail.get("take_profit")

        results = []
        if sl_val is not None:
            r = await self._adjust_param("stop_loss_percent", sl_val)
            results.append(r.message)
            if not r.success:
                return r
        if tp_val is not None:
            r = await self._adjust_param("take_profit_percent", tp_val)
            results.append(r.message)
            if not r.success:
                return r

        if not results:
            return ExecutionResult(success=False, message="未能从 detail 中提取止损/止盈参数")

        return ExecutionResult(success=True, message=" | ".join(results))

    async def _adjust_leverage(self, detail: Dict) -> ExecutionResult:
        new_max = detail.get("leverage_max")
        # 从 targets 列表中提取
        if new_max is None:
            targets = detail.get("targets", [])
            if isinstance(targets, list):
                for t in targets:
                    if isinstance(t, dict) and "leverage" in t.get("parameter", ""):
                        new_max = t.get("proposed") or t.get("to") or t.get("value")
                        break
        # 从 proposed / to 提取
        if new_max is None:
            new_max = detail.get("proposed") or detail.get("to")
        if new_max is None:
            return ExecutionResult(success=False, message="缺少 leverage_max 参数")
        if not isinstance(new_max, (int, float)) or new_max < 1 or new_max > 20:
            return ExecutionResult(success=False, message=f"非法杠杆倍数: {new_max}，须在 [1, 20] 之间")
        new_max = int(new_max)
        config_data = await self._redis.get("trading:config")
        config = json.loads(config_data) if config_data else {"enabled": True, "decisionInterval": runtime_config.decision_interval // 60 if runtime_config.decision_interval >= 60 else 1}
        config["leverage_max"] = new_max
        await self._redis.set("trading:config", json.dumps(config))
        await self._redis.publish("trading:config:updated", json.dumps(config))
        # 同步更新运行时配置
        runtime_config.leverage_max = new_max
        return ExecutionResult(success=True, message=f"Leverage max 已调整为 {new_max}x", detail={"leverage_max": new_max})

    _PARAM_BOUNDS = {
        "stop_loss_percent": (0.1, 50.0),
        "take_profit_percent": (0.1, 200.0),
    }

    async def _adjust_param(self, param_name: str, value: Any) -> ExecutionResult:
        if value is None:
            return ExecutionResult(success=False, message=f"缺少 {param_name} 参数")
        if not isinstance(value, (int, float)):
            return ExecutionResult(success=False, message=f"{param_name} 必须为数值类型，当前: {type(value).__name__}")
        bounds = self._PARAM_BOUNDS.get(param_name)
        if bounds:
            lo, hi = bounds
            if value < lo or value > hi:
                return ExecutionResult(success=False, message=f"{param_name} 值 {value} 超出允许范围 [{lo}, {hi}]")
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
                val = detail[key]
                if not isinstance(val, (int, float)) or val < 0 or val > 1.0:
                    return ExecutionResult(success=False, message=f"{key} 值 {val} 超出允许范围 [0, 1.0]")
                config[key] = val
                updated[key] = val
                # 同步更新运行时配置
                if hasattr(runtime_config, key):
                    setattr(runtime_config, key, val)
        await self._redis.set("trading:config", json.dumps(config))
        await self._redis.publish("trading:config:updated", json.dumps(config))
        return ExecutionResult(success=True, message=f"权重已调整: {updated}", detail=updated)


class TradeExecutor:
    def __init__(self, order_manager, position_manager):
        self._order_mgr = order_manager
        self._position_mgr = position_manager

    async def execute(self, action: str, target: str, detail: Dict[str, Any]) -> ExecutionResult:
        try:
            if action in ("close_position", "close"):
                return await self._close_position(target)
            elif action in ("reduce_position", "reduce"):
                # 兼容 LLM 用 size_change_percent 代替 reduce_percent
                if "size_change_percent" in detail and "reduce_percent" not in detail:
                    detail["reduce_percent"] = detail["size_change_percent"]
                return await self._reduce_position(target, detail)
            elif action in ("hold", "hold_with_protection", "no_change", "tighten_risk", "monitor"):
                return ExecutionResult(success=True, message=f"保持 {target} 当前仓位不变")
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
        raw_pct = detail.get("reduce_percent", 50)
        if not isinstance(raw_pct, (int, float)) or raw_pct <= 0 or raw_pct > 100:
            return ExecutionResult(success=False, message=f"非法减仓比例: {raw_pct}，须在 (0, 100] 之间")
        reduce_pct = raw_pct / 100
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
            if action in ("add_symbol", "add"):
                return await self._add_symbol(target)
            elif action in ("remove_symbol", "remove"):
                return await self._remove_symbol(target)
            elif action in ("no_change", "hold"):
                return ExecutionResult(success=True, message="交易对列表保持不变")
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
        if len(symbols) <= 1:
            return ExecutionResult(success=False, message=f"无法移除最后一个交易对 {symbol}，至少保留一个")
        symbols.remove(symbol)
        config["trading_symbols"] = ",".join(symbols)
        await self._redis.set("trading:config", json.dumps(config))
        await self._redis.publish("trading:config:updated", json.dumps(config))
        return ExecutionResult(success=True, message=f"已移除交易对: {symbol}")
