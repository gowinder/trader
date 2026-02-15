"""Advisory 建议执行器"""

import json
import re
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

from ..config import config as runtime_config
from ..utils.logger import logger


@dataclass
class ExecutionResult:
    success: bool
    message: str
    detail: Optional[Dict[str, Any]] = field(default=None)


# ──────────────────────────── ConfigExecutor ────────────────────────────

class ConfigExecutor:
    def __init__(self, redis_client):
        self._redis = redis_client

    # detail 中可能出现的参数名别名 → 统一标准名
    _PARAM_ALIASES: Dict[str, str] = {
        "leverage_max": "leverage_max", "leverage": "leverage_max", "max_leverage": "leverage_max",
        "leverage_level": "leverage_max",
        "stop_loss_percent": "stop_loss_percent", "stop_loss": "stop_loss_percent",
        "sl": "stop_loss_percent", "sl_percent": "stop_loss_percent",
        "take_profit_percent": "take_profit_percent", "take_profit": "take_profit_percent",
        "tp": "take_profit_percent", "tp_percent": "take_profit_percent",
        "quant_weight": "quant_weight", "ai_weight": "ai_weight", "sentiment_weight": "sentiment_weight",
    }

    _WEIGHT_KEYS = frozenset({"quant_weight", "ai_weight", "sentiment_weight"})

    # ── 辅助方法 ──

    @staticmethod
    def _extract_value(detail: Dict) -> Any:
        """从 detail 中按优先级提取数值"""
        for k in ("to", "proposed", "suggested", "value", "new_value", "target_value", "suggested_value"):
            v = detail.get(k)
            if v is not None and isinstance(v, (int, float)):
                return v
        return None

    @staticmethod
    def _unwrap_nested_values(detail: Dict) -> None:
        """解包嵌套 dict 值：将 {"leverage_max": {"to": 5, "from": 10}} 转为 {"leverage_max": 5}"""
        for key in list(detail.keys()):
            val = detail[key]
            if isinstance(val, dict):
                extracted = val.get("to") or val.get("proposed") or val.get("suggested") or val.get("value")
                if isinstance(extracted, (int, float)):
                    detail[key] = extracted

    def _detect_param_from_detail(self, detail: Dict) -> Optional[str]:
        """从 detail 的 key 中检测标准参数名"""
        for key in detail:
            std = self._PARAM_ALIASES.get(key)
            if std:
                return std
        return None

    def _detect_param_from_target(self, target: str) -> Optional[str]:
        """从 target 字段推断参数名"""
        t = target.lower()
        if "leverage" in t:
            return "leverage_max"
        if "stop_loss" in t or t in ("sl", "sl_percent"):
            return "stop_loss_percent"
        if "take_profit" in t or t in ("tp", "tp_percent"):
            return "take_profit_percent"
        if t in self._WEIGHT_KEYS:
            return t
        return None

    async def _route_by_param(self, param: str, detail: Dict) -> ExecutionResult:
        """根据标准参数名路由到对应处理方法"""
        if param == "leverage_max":
            if "leverage_max" not in detail:
                for alias in ("leverage", "max_leverage", "leverage_level"):
                    if alias in detail:
                        detail["leverage_max"] = detail[alias]
                        break
                else:
                    val = self._extract_value(detail)
                    if val is not None:
                        detail["leverage_max"] = val
            return await self._adjust_leverage(detail)
        if param == "stop_loss_percent":
            val = detail.get("stop_loss_percent") or detail.get("stop_loss") or detail.get("sl") or self._extract_value(detail)
            return await self._adjust_param("stop_loss_percent", val)
        if param == "take_profit_percent":
            val = detail.get("take_profit_percent") or detail.get("take_profit") or detail.get("tp") or self._extract_value(detail)
            return await self._adjust_param("take_profit_percent", val)
        if param in self._WEIGHT_KEYS:
            if param not in detail:
                val = self._extract_value(detail)
                if val is not None:
                    detail[param] = val
            return await self._adjust_weights(detail)
        return ExecutionResult(success=False, message=f"无法处理参数: {param}")

    # ── 主入口 ──

    async def execute(self, action: str, target: str, detail: Dict[str, Any]) -> ExecutionResult:
        try:
            # 预处理：解包嵌套 dict 值
            self._unwrap_nested_values(detail)

            # 1. 精确匹配 action
            if action in ("reduce_leverage", "increase_leverage", "adjust_leverage"):
                return await self._adjust_leverage(detail)
            elif action in ("adjust_stop_loss",):
                return await self._route_by_param("stop_loss_percent", detail)
            elif action in ("adjust_take_profit",):
                return await self._route_by_param("take_profit_percent", detail)
            elif action in ("adjust_weights",):
                return await self._adjust_weights(detail)

            # 2. 组合 action（如 adjust_stop_loss_take_profit）
            if "stop_loss" in action and "take_profit" in action:
                return await self._adjust_combined_sl_tp(detail)

            # 3. 从 detail["parameter"] 字段识别
            param_name = detail.get("parameter", "")
            std_param = self._PARAM_ALIASES.get(param_name)
            if std_param:
                return await self._route_by_param(std_param, detail)

            # 4. 从 detail key 中检测参数
            detected = self._detect_param_from_detail(detail)
            if detected:
                return await self._route_by_param(detected, detail)

            # 5. 从 targets 列表逐个解析
            targets = detail.get("targets", [])
            if isinstance(targets, list) and targets:
                results = []
                for t in targets:
                    if not isinstance(t, dict):
                        continue
                    p = t.get("parameter", "")
                    v = t.get("proposed") or t.get("suggested") or t.get("to") or t.get("value") or t.get("new_value")
                    if not p or v is None:
                        continue
                    std_p = self._PARAM_ALIASES.get(p)
                    if not std_p:
                        # 模糊匹配
                        if "stop_loss" in p:
                            std_p = "stop_loss_percent"
                        elif "take_profit" in p:
                            std_p = "take_profit_percent"
                        elif "leverage" in p:
                            std_p = "leverage_max"
                        else:
                            continue
                    if std_p == "leverage_max":
                        detail["leverage_max"] = v
                        r = await self._adjust_leverage(detail)
                    elif std_p == "stop_loss_percent":
                        r = await self._adjust_param("stop_loss_percent", v)
                    elif std_p == "take_profit_percent":
                        r = await self._adjust_param("take_profit_percent", v)
                    elif std_p in self._WEIGHT_KEYS:
                        r = await self._adjust_param(std_p, v)
                    else:
                        continue
                    results.append(r.message)
                    if not r.success:
                        return r
                if results:
                    return ExecutionResult(success=True, message=" | ".join(results))

            # 6. action 关键词匹配参数类型
            action_lower = action.lower()
            if "leverage" in action_lower:
                return await self._adjust_leverage(detail)
            if "stop_loss" in action_lower:
                return await self._route_by_param("stop_loss_percent", detail)
            if "take_profit" in action_lower:
                return await self._route_by_param("take_profit_percent", detail)
            if "weight" in action_lower:
                return await self._adjust_weights(detail)

            # 7. action 含通用动词时，从 target 推断
            _GENERIC_VERBS = ("update", "config", "adjust", "modify", "change", "set",
                              "increase", "decrease", "enable", "disable", "reset",
                              "reduce", "lower", "raise", "tighten", "loosen")
            if any(kw in action_lower for kw in _GENERIC_VERBS):
                target_param = self._detect_param_from_target(target)
                if target_param:
                    return await self._route_by_param(target_param, detail)

            return ExecutionResult(success=False, message=f"未知的配置操作: {action}, target: {target}, detail keys: {list(detail.keys())}")
        except Exception as e:
            logger.error(f"Config execution failed: {e}")
            return ExecutionResult(success=False, message=str(e))

    # ── 具体执行方法 ──

    async def _adjust_combined_sl_tp(self, detail: Dict) -> ExecutionResult:
        """处理同时调整止损止盈的组合 action"""
        sl_val = None
        tp_val = None

        targets = detail.get("targets", [])
        if isinstance(targets, list):
            for t in targets:
                if isinstance(t, dict):
                    param = t.get("parameter", "")
                    val = t.get("proposed") or t.get("suggested") or t.get("to") or t.get("value")
                    if "stop_loss" in param:
                        sl_val = val
                    elif "take_profit" in param:
                        tp_val = val

        if sl_val is None:
            sl_val = detail.get("stop_loss_percent") or detail.get("stop_loss") or detail.get("sl")
        if tp_val is None:
            tp_val = detail.get("take_profit_percent") or detail.get("take_profit") or detail.get("tp")

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
        new_max = detail.get("leverage_max") or detail.get("leverage") or detail.get("max_leverage")
        # 从 targets 列表中提取
        if new_max is None:
            targets = detail.get("targets", [])
            if isinstance(targets, list):
                for t in targets:
                    if isinstance(t, dict) and "leverage" in t.get("parameter", ""):
                        new_max = t.get("proposed") or t.get("to") or t.get("value")
                        break
        # 从通用值字段提取
        if new_max is None:
            new_max = self._extract_value(detail)
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
                if hasattr(runtime_config, key):
                    setattr(runtime_config, key, val)
        await self._redis.set("trading:config", json.dumps(config))
        await self._redis.publish("trading:config:updated", json.dumps(config))
        return ExecutionResult(success=True, message=f"权重已调整: {updated}", detail=updated)


# ──────────────────────────── TradeExecutor ────────────────────────────

class TradeExecutor:
    def __init__(self, order_manager, position_manager, exchange=None):
        self._order_mgr = order_manager
        self._position_mgr = position_manager
        self._exchange = exchange

    async def execute(self, action: str, target: str, detail: Dict[str, Any]) -> ExecutionResult:
        try:
            # 提取 reduce_percent：兼容多种 LLM 输出格式
            self._normalize_reduce_percent(detail)

            # 1. 精确匹配 action
            if action in ("open_long", "open_short"):
                side = "long" if action == "open_long" else "short"
                return await self._open_position(target, side, detail)
            elif action in ("close_position", "close"):
                return await self._close_position(target)
            elif action in ("reduce_position", "reduce"):
                return await self._reduce_position(target, detail)
            elif action in ("take_profit_partial_and_move_stop", "partial_take_profit"):
                return await self._partial_take_profit(target, detail)
            elif action in ("tighten_stop_or_exit_if_breaks_level", "tighten_stop", "exit_if_breaks"):
                return await self._tighten_or_exit(target, detail)
            elif action in ("hold", "hold_with_protection", "no_change", "tighten_risk", "monitor",
                            "wait", "observe", "keep", "maintain"):
                return ExecutionResult(success=True, message=f"保持 {target} 当前仓位不变")

            # 2. 智能兜底：根据 action 关键词推断意图
            action_lower = action.lower()

            # 开仓类关键词
            _OPEN_LONG_KW = ("open_long", "buy", "go_long", "long_entry")
            _OPEN_SHORT_KW = ("open_short", "sell", "go_short", "short_entry")

            if any(kw in action_lower for kw in _OPEN_LONG_KW):
                return await self._open_position(target, "long", detail)
            if any(kw in action_lower for kw in _OPEN_SHORT_KW):
                return await self._open_position(target, "short", detail)

            # 平仓类关键词
            _CLOSE_KW = ("close", "exit", "liquidate", "flatten", "unwind", "cut")
            # 减仓类关键词
            _REDUCE_KW = ("reduce", "scale_out", "scale-out", "partial", "trim", "decrease")
            # 止盈/保护类关键词
            _PROTECT_KW = ("protect", "profit", "tighten", "lock_in", "lock-in", "take_profit", "tp")
            # 持仓不动类关键词
            _HOLD_KW = ("hold", "wait", "observe", "keep", "maintain", "monitor", "watch", "stay")

            # 含平仓关键词 + urgency=high → 直接平仓
            if any(kw in action_lower for kw in _CLOSE_KW) and detail.get("urgency") == "high":
                return await self._close_position(target)

            # 含减仓关键词
            if any(kw in action_lower for kw in _REDUCE_KW):
                return await self._reduce_position(target, detail)

            # close + reduce 组合（reduce_or_close）
            if any(kw in action_lower for kw in _CLOSE_KW) and any(kw in action_lower for kw in _REDUCE_KW):
                if detail.get("reduce_percent"):
                    return await self._reduce_position(target, detail)
                return await self._close_position(target)

            # 含平仓关键词（低 urgency 也平）
            if any(kw in action_lower for kw in _CLOSE_KW):
                return await self._close_position(target)

            # 含保护/止盈关键词
            if any(kw in action_lower for kw in _PROTECT_KW):
                return await self._partial_take_profit(target, detail)

            # 含持仓不动关键词
            if any(kw in action_lower for kw in _HOLD_KW):
                return ExecutionResult(success=True, message=f"保持 {target} 当前仓位不变")

            return ExecutionResult(success=False, message=f"未知的仓位操作: {action}")
        except Exception as e:
            logger.error(f"Trade execution failed: {e}")
            return ExecutionResult(success=False, message=str(e))

    @staticmethod
    def _normalize_reduce_percent(detail: Dict) -> None:
        """从各种 LLM 输出格式中提取 reduce_percent 到 detail 中"""
        if "reduce_percent" in detail and isinstance(detail["reduce_percent"], (int, float)):
            return
        # 别名字段
        for key in ("size_change_percent", "close_percent", "reduction_percent",
                     "reduce_pct", "reduce_ratio", "scale_out_percent"):
            if key in detail and isinstance(detail[key], (int, float)):
                detail["reduce_percent"] = detail[key]
                return
        # recommended 中包含百分比文本（如 "立即平掉至少70%"）
        recommended = detail.get("recommended", "")
        if isinstance(recommended, str):
            m = re.search(r'(\d+)\s*%', recommended)
            if m:
                detail.setdefault("reduce_percent", int(m.group(1)))
                return
        # scale_out 列表: [{"close_percent": 30, ...}]
        scale_out = detail.get("scale_out", [])
        if isinstance(scale_out, list):
            total_pct = 0
            for item in scale_out:
                if isinstance(item, dict):
                    total_pct += item.get("close_percent", 0)
            if total_pct > 0:
                detail.setdefault("reduce_percent", total_pct)
                return

    async def _open_position(self, symbol: str, side: str, detail: Dict) -> ExecutionResult:
        """开仓：根据 detail 中的参数计算仓位大小并下单"""
        if not self._exchange:
            return ExecutionResult(success=False, message="Exchange 未初始化，无法开仓")

        # 检查是否已有仓位
        existing = await self._position_mgr.get_position(symbol)
        if existing:
            return ExecutionResult(success=False, message=f"{symbol} 已有 {existing.side} 仓位，无法开新仓")

        # 获取当前价格和余额
        ticker = await self._exchange.get_ticker(symbol)
        if not ticker or not ticker.last_price:
            return ExecutionResult(success=False, message=f"无法获取 {symbol} 当前价格")

        account = await self._exchange.get_account()
        if not account or not account.available_balance or account.available_balance <= 0:
            return ExecutionResult(success=False, message="可用余额不足")

        current_price = ticker.last_price
        leverage = detail.get("suggested_leverage") or detail.get("leverage") or 1
        position_size_pct = detail.get("position_size_percent", 10)
        stop_loss = detail.get("stop_loss")
        take_profit = detail.get("take_profit")

        # 计算下单数量
        amount_usdt = account.available_balance * (position_size_pct / 100) * leverage
        quantity = amount_usdt / current_price
        if quantity <= 0:
            return ExecutionResult(success=False, message="计算的开仓数量为 0")

        from ..models.decision import TradingDecision
        action_str = f"open_{side}"
        decision = TradingDecision(
            action=action_str,
            confidence=80,
            leverage=int(leverage),
            position_size_percent=position_size_pct,
            stop_loss_price=stop_loss,
            take_profit_price=take_profit,
            reasoning="Advisory system recommended open position",
            reasoning_zh=f"AI顾问系统建议开{'多' if side == 'long' else '空'}",
        )
        result = await self._order_mgr.execute_order(decision, symbol, quantity)
        if result is None:
            return ExecutionResult(success=False, message=f"开仓下单失败: {symbol}")

        side_zh = "多" if side == "long" else "空"
        return ExecutionResult(
            success=True,
            message=f"已开{side_zh} {symbol} (杠杆 {leverage}x, 仓位 {position_size_pct}%)",
            detail={"side": side, "leverage": leverage, "quantity": quantity, "price": current_price},
        )

    async def _close_position(self, symbol: str) -> ExecutionResult:
        position = await self._position_mgr.get_position(symbol)
        if not position:
            return ExecutionResult(success=False, message=f"仓位不存在(可能已被主循环平仓): {symbol}")
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
            return ExecutionResult(success=False, message=f"仓位不存在(可能已被主循环平仓): {symbol}")
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

    async def _partial_take_profit(self, symbol: str, detail: Dict) -> ExecutionResult:
        """部分止盈：提取 take_profit 中的 size_percent 执行减仓"""
        targets = detail.get("targets", {})
        tp_list = targets.get("take_profit", []) if isinstance(targets, dict) else []
        reduce_pct = None
        if isinstance(tp_list, list):
            for tp in tp_list:
                if isinstance(tp, dict):
                    reduce_pct = tp.get("size_percent") or tp.get("reduce_percent")
                    break
        if reduce_pct is None:
            reduce_pct = detail.get("reduce_percent", detail.get("size_percent", 50))
        return await self._reduce_position(symbol, {"reduce_percent": reduce_pct})

    async def _tighten_or_exit(self, symbol: str, detail: Dict) -> ExecutionResult:
        """收紧止损/平仓：根据紧急程度执行平仓或减仓"""
        urgency = detail.get("urgency", "medium")
        targets = detail.get("targets", {})
        if urgency == "high":
            return await self._close_position(symbol)
        else:
            reduce_pct = 50
            if isinstance(targets, dict):
                reduce_pct = targets.get("reduce_size_percent", 50)
            return await self._reduce_position(symbol, {"reduce_percent": reduce_pct})


# ──────────────────────────── StrategyExecutor ────────────────────────────

class StrategyExecutor:
    """策略预设切换执行器"""

    def __init__(self, strategy_service, redis_client):
        self._strategy_service = strategy_service
        self._redis = redis_client

    async def execute(self, action: str, target: str, detail: Dict[str, Any]) -> ExecutionResult:
        try:
            # 精确匹配
            if action in ("switch_preset", "change_preset", "switch"):
                return await self._switch_preset(target, detail)
            elif action in ("no_change", "hold", "keep", "maintain"):
                return ExecutionResult(success=True, message="策略预设保持不变")

            # 关键词兜底
            action_lower = action.lower()
            if any(kw in action_lower for kw in ("switch", "change", "activate", "apply", "use", "enable", "select")):
                return await self._switch_preset(target, detail)
            if any(kw in action_lower for kw in ("hold", "keep", "maintain", "no_change", "stay")):
                return ExecutionResult(success=True, message="策略预设保持不变")

            return ExecutionResult(success=False, message=f"未知的策略操作: {action}")
        except Exception as e:
            logger.error(f"Strategy execution failed: {e}")
            return ExecutionResult(success=False, message=str(e))

    async def _switch_preset(self, target: str, detail: Dict) -> ExecutionResult:
        preset_name = detail.get("preset_name") or target
        all_presets = await self._strategy_service.get_all_presets()
        target_preset = next((p for p in all_presets if p["name"] == preset_name), None)
        if not target_preset:
            return ExecutionResult(success=False, message=f"未找到策略预设: {preset_name}")
        active = await self._strategy_service.get_active_preset()
        if active and active["id"] == target_preset["id"]:
            return ExecutionResult(success=False, message=f"当前已在使用 {target_preset.get('display_name', preset_name)}，无需切换")
        success = await self._strategy_service.activate_preset(target_preset["id"])
        if not success:
            return ExecutionResult(success=False, message="策略切换失败")
        if self._redis:
            config_json = target_preset.get("config_json", "{}")
            config_data = json.loads(config_json) if isinstance(config_json, str) else config_json
            await self._redis.set("strategy:active_preset", json.dumps({
                "name": target_preset["name"],
                "config": config_data,
            }))
            await self._redis.publish("strategy:preset:updated", json.dumps({
                "preset_id": target_preset["id"],
                "name": target_preset["name"],
            }))
        return ExecutionResult(
            success=True,
            message=f"策略已切换到: {target_preset.get('display_name', preset_name)}",
            detail={"preset_name": target_preset["name"], "display_name": target_preset.get("display_name", "")},
        )


# ──────────────────────────── SymbolExecutor ────────────────────────────

class SymbolExecutor:
    def __init__(self, redis_client):
        self._redis = redis_client

    async def execute(self, action: str, target: str, detail: Dict[str, Any]) -> ExecutionResult:
        try:
            # 精确匹配
            if action in ("add_symbol", "add"):
                return await self._add_symbol(target)
            elif action in ("remove_symbol", "remove"):
                return await self._remove_symbol(target)
            elif action in ("pause_trading", "pause", "skip", "avoid", "suspend"):
                return await self._pause_symbol(target, detail)
            elif action in ("no_change", "hold", "keep", "maintain"):
                return ExecutionResult(success=True, message="交易对列表保持不变")

            # 关键词兜底
            action_lower = action.lower()
            if any(kw in action_lower for kw in ("pause", "skip", "avoid", "suspend", "stop_trading",
                                                   "disable", "deactivate", "blacklist", "block")):
                return await self._pause_symbol(target, detail)
            if any(kw in action_lower for kw in ("add", "include", "enable", "activate", "whitelist")):
                return await self._add_symbol(target)
            if any(kw in action_lower for kw in ("remove", "exclude", "drop", "delete")):
                return await self._remove_symbol(target)
            if any(kw in action_lower for kw in ("hold", "keep", "maintain", "no_change", "stay")):
                return ExecutionResult(success=True, message="交易对列表保持不变")

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

    async def _pause_symbol(self, symbol: str, detail: Dict) -> ExecutionResult:
        """暂停某交易对：从监控列表中移除，并记录恢复条件供用户参考"""
        config_data = await self._redis.get("trading:config")
        config = json.loads(config_data) if config_data else {"enabled": True, "decisionInterval": runtime_config.decision_interval // 60 if runtime_config.decision_interval >= 60 else 1}
        symbols = await self._get_current_symbols(config)
        if symbol not in symbols:
            return ExecutionResult(success=True, message=f"{symbol} 不在监控列表中，已等同暂停")
        if len(symbols) <= 1:
            return ExecutionResult(success=False, message=f"无法暂停最后一个交易对 {symbol}，至少保留一个")
        symbols.remove(symbol)
        config["trading_symbols"] = ",".join(symbols)
        await self._redis.set("trading:config", json.dumps(config))
        await self._redis.publish("trading:config:updated", json.dumps(config))
        duration = detail.get("duration_hours", "")
        resume_cond = detail.get("resume_condition", "")
        msg = f"已暂停 {symbol} 交易（从监控列表移除）"
        if duration:
            msg += f"，建议 {duration} 小时后恢复"
        if resume_cond:
            msg += f"，恢复条件: {resume_cond}"
        return ExecutionResult(success=True, message=msg)

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
