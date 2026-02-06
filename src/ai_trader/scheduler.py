"""调度器模块"""

import asyncio
import json
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

import redis.asyncio as redis

from .config import config


@dataclass
class TradeResult:
    """交易结果数据类"""
    exit_price: float
    pnl: float
    pnl_percent: float
from .utils.logger import logger
from .exchange import create_exchange_client
from .exchange.order import OrderManager
from .exchange.position import PositionManager
from .data.market_data import MarketDataManager
from .ai.client import LLMClient
from .ai.decision import DecisionEngine
from .ai.hybrid_decision import HybridDecisionEngine
from .persistence import DatabaseManager, DecisionPersistenceService
from .reporter import Reporter
from .memory import TradeMemoryCollector
from .ai.usage_tracker import get_usage_tracker
from .reflection.service import ReflectionClient
from .optimization import ParameterRegistry, ShadowRunner


class Scheduler:
    """任务调度器"""

    def __init__(self):
        # Use factory function to create exchange client based on config
        self.exchange = create_exchange_client()
        self.llm = LLMClient()

        self.market_mgr = MarketDataManager(self.exchange)
        self.order_mgr = OrderManager(self.exchange)
        self.position_mgr = PositionManager(self.exchange)

        # Use HybridDecisionEngine for enhanced features (quant, sentiment, persistence)
        self.decision_engine = HybridDecisionEngine(self.llm)
        self.reporter = Reporter()

        # Position persistence
        self.db_manager: Optional[DatabaseManager] = None
        self.persistence_service: Optional[DecisionPersistenceService] = None
        self._persistence_initialized = False

        # Track current position for persistence
        self._current_position_id: Optional[UUID] = None

        # Memory and optimization system
        self.memory_collector: Optional[TradeMemoryCollector] = None
        self.reflection_client: Optional[ReflectionClient] = None
        self.shadow_runner: Optional[ShadowRunner] = None
        self.parameter_registry = ParameterRegistry()

        self.running = False

        # Redis for dynamic config
        self._redis: Optional[redis.Redis] = None
        self._trading_enabled = True
        self._decision_interval = config.decision_interval

    async def _init_persistence(self):
        """初始化仓位持久化服务"""
        if self._persistence_initialized:
            return

        if not config.enable_decision_persistence:
            return

        if not config.dashboard_database_url:
            logger.warning("Dashboard database URL not configured, persistence disabled")
            return

        try:
            self.db_manager = DatabaseManager(config.dashboard_database_url)
            await self.db_manager.connect()
            self.persistence_service = DecisionPersistenceService(self.db_manager)
            self._persistence_initialized = True
            logger.info("Position persistence service initialized")

            # Initialize usage tracker with PostgreSQL
            usage_tracker = get_usage_tracker()
            usage_tracker.set_persistence_service(self.persistence_service)
            logger.info("LLM usage tracker connected to PostgreSQL")

            # Initialize memory and optimization system if enabled
            if config.enable_auto_optimization:
                self.memory_collector = TradeMemoryCollector(self.db_manager)
                redis_url = config.redis_url if hasattr(config, "redis_url") else "redis://redis:6379"
                self.reflection_client = ReflectionClient(redis_url)
                await self.reflection_client.connect()
                self.shadow_runner = ShadowRunner(self.db_manager)
                logger.info("Memory and optimization system initialized (async mode)")
        except Exception as e:
            logger.error(f"Failed to initialize persistence service: {e}")
            self.db_manager = None
            self.persistence_service = None

    async def _init_redis(self):
        """初始化 Redis 连接"""
        try:
            self._redis = redis.from_url(config.redis_url, decode_responses=True)
            await self._redis.ping()
            logger.info("Redis connected for dynamic config")

            # Load initial config from Redis
            await self._load_trading_config()

            # Start config listener in background
            asyncio.create_task(self._config_listener())
            asyncio.create_task(self._manual_trigger_listener())
            asyncio.create_task(self._backtest_task_listener())
        except Exception as e:
            logger.warning(f"Redis not available, using static config: {e}")
            self._redis = None

    async def _load_trading_config(self):
        """从 Redis 加载交易配置"""
        if not self._redis:
            return

        try:
            data = await self._redis.get("trading:config")
            if data:
                cfg = json.loads(data)
                self._trading_enabled = cfg.get("enabled", True)
                # Convert minutes to seconds
                interval_minutes = cfg.get("decisionInterval", 1)
                self._decision_interval = interval_minutes * 60
                logger.info(f"Loaded trading config: enabled={self._trading_enabled}, interval={interval_minutes}m")
        except Exception as e:
            logger.error(f"Failed to load trading config: {e}")

    async def _config_listener(self):
        """监听配置更新"""
        if not self._redis:
            return

        try:
            pubsub = self._redis.pubsub()
            await pubsub.subscribe("trading:config:updated")

            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        cfg = json.loads(message["data"])
                        self._trading_enabled = cfg.get("enabled", True)
                        interval_minutes = cfg.get("decisionInterval", 1)
                        self._decision_interval = interval_minutes * 60
                        logger.info(f"Config updated: enabled={self._trading_enabled}, interval={interval_minutes}m")
                    except Exception as e:
                        logger.error(f"Failed to parse config update: {e}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Config listener error: {e}")

    async def _manual_trigger_listener(self):
        """监听手动触发事件"""
        if not self._redis:
            return

        try:
            pubsub = self._redis.pubsub()
            await pubsub.subscribe("trading:manual_trigger")

            async for message in pubsub.listen():
                if message["type"] == "message":
                    logger.info("Received manual trigger")
                    try:
                        await self.run_cycle()
                    except Exception as e:
                        logger.error(f"Manual trigger cycle error: {e}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Manual trigger listener error: {e}")

    async def _backtest_task_listener(self):
        """监听回测任务队列"""
        if not self._redis:
            return

        logger.info("Backtest task listener started")
        try:
            while self.running:
                # 从队列中阻塞读取任务 (timeout 5秒)
                result = await self._redis.brpop("backtest:tasks", timeout=5)
                if result is None:
                    continue

                _, task_json = result
                try:
                    task = json.loads(task_json)
                    logger.info(f"Received backtest task: {task.get('task_id')}")
                    await self._run_backtest_task(task)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse backtest task: {e}")
                except Exception as e:
                    logger.error(f"Backtest task error: {e}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Backtest task listener error: {e}")

    async def _run_backtest_task(self, task: dict):
        """执行回测任务"""
        from datetime import datetime
        from .backtest.engine import BacktestEngine, BacktestConfig
        from .strategies.market_classifier import MarketClassifier
        from .strategies.strategy_selector import StrategySelector
        from .data.fetcher import CachedDataFetcher
        import pandas as pd

        task_id = task.get("task_id", "unknown")
        symbol = task.get("symbol", "BTCUSDT")
        start_date = task.get("start_date")
        end_date = task.get("end_date")
        interval = task.get("interval", "1h")
        capital = task.get("capital", 10000)

        logger.info(f"Running backtest {task_id}: {symbol} {start_date} - {end_date}")

        try:
            # 更新任务状态
            if self._redis:
                await self._redis.hset(f"backtest:status:{task_id}", mapping={
                    "status": "running",
                    "started_at": datetime.now().isoformat(),
                })

            # 获取数据
            # 转换 symbol 格式: BTCUSDT -> BTC/USDT
            if "/" not in symbol:
                fetch_symbol = f"{symbol[:-4]}/{symbol[-4:]}"
            else:
                fetch_symbol = symbol

            # 使用 testnet 获取数据（避免代理问题）
            use_testnet = config.trading_mode == "testnet"
            fetcher = CachedDataFetcher(
                cache_dir="data/cache",
                testnet=use_testnet,
                proxy_url=config.proxy_url if not use_testnet else ""
            )
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")
            df = fetcher.get_data(
                symbol=fetch_symbol,
                start_date=start,
                end_date=end,
                timeframe=interval,
            )

            logger.info(f"Loaded {len(df)} candles for backtest")

            # 生成信号
            market_classifier = MarketClassifier()
            strategy_selector = StrategySelector(config.enabled_strategies)

            signals = []
            for i in range(len(df)):
                window_df = df.iloc[max(0, i - 100) : i + 1]
                if len(window_df) < 50:
                    signals.append({"action": "hold", "confidence": 0.0})
                    continue

                market_class = market_classifier.classify(window_df)
                signal = strategy_selector.aggregate_signals(window_df, market_class)

                action_map = {
                    "long": "open_long",
                    "short": "open_short",
                    "close_long": "close_long",
                    "close_short": "close_short",
                    "hold": "hold",
                }
                action = action_map.get(signal.action.value, "hold")

                # Confidence filter
                if signal.confidence < 0.55:
                    action = "hold"

                signals.append({
                    "action": action,
                    "confidence": signal.confidence,
                    "entry_price": signal.entry_price,
                    "stop_loss": signal.stop_loss,
                    "take_profit": signal.take_profit,
                })

            signals_df = pd.DataFrame(signals)

            # 运行回测
            bt_config = BacktestConfig(
                initial_capital=capital,
                commission_rate=0.0002,
                slippage_rate=0.001,
                max_position_size=0.5,
                enable_stop_loss=True,
                enable_take_profit=True,
            )

            engine = BacktestEngine(bt_config)
            result = engine.run(df, signals_df)

            # 保存结果
            result_data = {
                "status": "completed",
                "completed_at": datetime.now().isoformat(),
                "final_capital": result.final_capital,
                "total_pnl": result.total_pnl,
                "return_pct": result.return_pct,
                "total_trades": result.total_trades,
                "winning_trades": result.winning_trades,
                "win_rate": result.win_rate,
                "max_drawdown": result.max_drawdown,
                "max_drawdown_pct": result.max_drawdown_pct,
                "sharpe_ratio": result.sharpe_ratio,
            }

            if self._redis:
                await self._redis.hset(f"backtest:status:{task_id}", mapping={
                    k: str(v) for k, v in result_data.items()
                })
                # 设置过期时间 (24小时)
                await self._redis.expire(f"backtest:status:{task_id}", 86400)

            logger.info(f"Backtest {task_id} completed: return={result.return_pct:.2f}%")

            # 保存到数据库
            if self.persistence_service:
                try:
                    backtest_id = await self.persistence_service.create_backtest(
                        mode="single",
                        symbol=symbol,
                        start_date=start_date,
                        end_date=end_date,
                        initial_capital=capital,
                    )
                    await self.persistence_service.complete_backtest(
                        backtest_id=backtest_id,
                        final_capital=result.final_capital,
                        total_pnl=result.total_pnl,
                        total_trades=result.total_trades,
                        winning_trades=result.winning_trades,
                        max_drawdown=result.max_drawdown,
                        sharpe_ratio=result.sharpe_ratio,
                    )
                    logger.info(f"Backtest saved to database: {backtest_id}")
                except Exception as e:
                    logger.error(f"Failed to save backtest to database: {e}")

        except Exception as e:
            logger.error(f"Backtest {task_id} failed: {e}")
            if self._redis:
                await self._redis.hset(f"backtest:status:{task_id}", mapping={
                    "status": "failed",
                    "error": str(e),
                    "failed_at": datetime.now().isoformat(),
                })
                await self._redis.expire(f"backtest:status:{task_id}", 86400)

    async def start(self):
        """启动调度器"""
        self.running = True
        symbols = config.symbols_list
        logger.info(f"Scheduler started for {len(symbols)} symbol(s): {', '.join(symbols)}")

        # Initialize persistence if enabled
        await self._init_persistence()

        # Initialize Redis for dynamic config
        await self._init_redis()

        while self.running:
            # Check if trading is enabled
            if not self._trading_enabled:
                logger.debug("Trading paused, waiting...")
                await asyncio.sleep(5)
                continue

            try:
                # Run cycle for each symbol
                for symbol in symbols:
                    try:
                        await self.run_cycle_for_symbol(symbol)
                    except Exception as e:
                        logger.error(f"Error in cycle for {symbol}: {e}")
            except Exception as e:
                logger.error(f"Error in main cycle: {e}")

            logger.info(f"Waiting {self._decision_interval}s...")
            await asyncio.sleep(self._decision_interval)

    async def stop(self):
        """停止调度器"""
        self.running = False
        if hasattr(self, "exchange") and self.exchange:
            await self.exchange.close()
        if hasattr(self, "llm") and self.llm:
            await self.llm.close()
        if hasattr(self, "db_manager") and self.db_manager:
            await self.db_manager.close()
        if self._redis:
            await self._redis.close()
        logger.info("Scheduler stopped")

    async def _publish_account_state(self, symbol: str, account, position, current_price: float):
        """发布账户和持仓状态到 Redis（供 Dashboard 获取）"""
        if not self._redis:
            return

        try:
            import datetime
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()

            # 构建持仓数据
            position_data = None
            if position and position.size > 0:
                position_data = {
                    "symbol": position.symbol,
                    "side": position.side,
                    "size": position.size,
                    "entry_price": position.entry_price,
                    "mark_price": position.mark_price,
                    "liquidation_price": position.liquidation_price,
                    "leverage": position.leverage,
                    "margin": position.margin,
                    "unrealized_pnl": position.unrealized_pnl,
                    "roi": position.roi,
                }

            # 构建账户状态
            state = {
                "updated_at": now,
                "account": {
                    "total_equity": account.total_equity,
                    "available_balance": account.available_balance,
                    "margin_used": account.margin_used,
                    "unrealized_pnl": account.unrealized_pnl,
                },
                "positions": {symbol: position_data} if position_data else {},
                "current_prices": {symbol: current_price},
            }

            # 存储到 Redis（Hash 结构便于单独更新）
            await self._redis.set("trading:account_state", json.dumps(state))
            # 设置 5 分钟过期（如果 trader 停止，状态会自动过期）
            await self._redis.expire("trading:account_state", 300)

            logger.debug(f"Published account state to Redis: equity={account.total_equity}")
        except Exception as e:
            logger.warning(f"Failed to publish account state: {e}")

    async def _persist_position_change(
        self,
        action: str,
        symbol: str,
        price: float,
        size: float,
        leverage: float,
        position,
        decision=None,
        technical=None,
        market_state: str = "unknown",
    ):
        """持久化仓位变化

        Args:
            action: 决策动作 (long, short, close_long, close_short, etc.)
            symbol: 交易对
            price: 成交价格
            size: 成交数量
            leverage: 杠杆
            position: 当前仓位信息
            decision: 决策信息（用于记忆收集）
            technical: 技术分析结果（用于记忆收集）
            market_state: 市场状态（用于记忆收集）
        """
        if not self.persistence_service:
            return

        try:
            if action in ["long", "short", "add_long", "add_short", "open_long", "open_short"]:
                # 开仓或加仓
                side = "long" if action in ["long", "add_long", "open_long"] else "short"
                position_id = await self.persistence_service.save_position_open(
                    symbol=symbol,
                    side=side,
                    entry_price=price,
                    entry_size=size,
                    leverage=leverage,
                )
                self._current_position_id = position_id
                logger.info(f"Position opened and persisted: {position_id}")

            elif action in ["close_long", "close_short"]:
                # 平仓
                if self._current_position_id and position:
                    # 计算盈亏
                    entry_price = position.entry_price
                    pnl = (price - entry_price) * size
                    if action == "close_short":
                        pnl = -pnl  # 空仓盈亏反向
                    pnl_percent = (pnl / (entry_price * size)) * 100

                    await self.persistence_service.save_position_close(
                        position_id=self._current_position_id,
                        exit_price=price,
                        realized_pnl=pnl,
                        pnl_percent=pnl_percent,
                        fee_total=None,
                    )

                    # 更新每日统计
                    await self.persistence_service.update_daily_stats(
                        symbol=symbol,
                        pnl=pnl,
                        is_win=pnl > 0,
                    )

                    logger.info(f"Position closed and persisted: {self._current_position_id}, pnl={pnl:.2f}")
                    self._current_position_id = None

                    # Collect trade memory and submit reflection task (async)
                    if self.memory_collector and decision:
                        result = TradeResult(
                            exit_price=price,
                            pnl=pnl,
                            pnl_percent=pnl_percent,
                        )
                        await self.memory_collector.collect(
                            position=position,
                            result=result,
                            decision=decision,
                            technical=technical,
                            market_state=market_state,
                        )
                        # 检查是否需要触发复盘（异步提交到队列）
                        if self.reflection_client:
                            count = await self.memory_collector.get_count_since_last_reflection()
                            if count >= config.reflection_trade_count:
                                from uuid import uuid4
                                task_id = str(uuid4())
                                await self.reflection_client.submit_task(task_id, count)
                                logger.info(f"已提交复盘任务到队列: {task_id}, 交易数: {count}")
                else:
                    logger.warning("No position ID tracked for close action")

            elif action in ["reduce_long", "reduce_short"]:
                # 部分平仓 - 记录为新的平仓记录
                if position:
                    entry_price = position.entry_price
                    pnl = (price - entry_price) * size
                    if action == "reduce_short":
                        pnl = -pnl
                    pnl_percent = (pnl / (entry_price * size)) * 100

                    # 更新每日统计
                    await self.persistence_service.update_daily_stats(
                        symbol=symbol,
                        pnl=pnl,
                        is_win=pnl > 0,
                    )
                    logger.info(f"Partial position close persisted, pnl={pnl:.2f}")

        except Exception as e:
            logger.error(f"Failed to persist position change: {e}")

    async def run_cycle(self):
        """执行单次交易循环（兼容旧版单 symbol）"""
        await self.run_cycle_for_symbol(config.trading_symbol)

    async def run_cycle_for_symbol(self, symbol: str):
        """执行指定 symbol 的交易循环"""
        logger.info(f"Starting cycle for {symbol}")

        # 1. 获取数据
        market_data = await self.market_mgr.get_market_data(
            symbol, interval=f"{config.analysis_interval}m"
        )
        if not market_data:
            return

        # For testnet mode, use simulated account/position data
        # CCXT no longer supports Binance Futures Testnet private API
        if config.trading_mode == "testnet":
            from .exchange.base import AccountInfo, Position
            # Simulated account with 10,000 USDT
            account = AccountInfo(
                total_equity=10000.0,
                available_balance=10000.0,
                margin_used=0.0,
                unrealized_pnl=0.0,
            )
            position = None  # No position in simulation
            logger.info("Using simulated account data for testnet (CCXT deprecated private API)")
        else:
            position = await self.position_mgr.get_position(symbol)
            account = await self.exchange.get_account()  # Now returns AccountInfo model

        # Extract account balance from AccountInfo
        balance = account.available_balance
        equity = account.total_equity

        # Debug: Log account data
        logger.debug(
            f"Account data: equity={equity}, balance={balance}, "
            f"margin_used={account.margin_used}, unrealized_pnl={account.unrealized_pnl}"
        )

        if balance <= 0 or equity <= 0:
            logger.warning(
                f"Insufficient balance or failed to parse account: balance={balance}, equity={equity}"
            )
            return

        # 2. 决策
        try:
            decision, tech, risk = await self.decision_engine.analyze_and_decide(
                market_data, position, balance, equity
            )
        except Exception as e:
            logger.error(f"Decision engine failed: {e}")
            return

        # 3. 执行
        order_id = None
        quantity = 0.0
        if decision.action != "hold":
            # Determine quantity based on action type
            if decision.action in ["close_long", "close_short"]:
                # Full close: use entire position size
                if position and position.size > 0:
                    quantity = position.size
                else:
                    logger.warning(
                        f"Decision is {decision.action} but no position found."
                    )
            elif decision.action in ["reduce_long", "reduce_short"]:
                # Partial close: reduce by 50% (default strategy for now)
                if position and position.size > 0:
                    quantity = position.size * 0.5
                else:
                    logger.warning(
                        f"Decision is {decision.action} but no position found."
                    )
            else:
                # Open/Add: calculate based on balance percent
                # amount_usdt = balance * (decision.position_size_percent / 100) * decision.leverage
                # Simplification:
                amount_usdt = (
                    balance * (decision.position_size_percent / 100) * decision.leverage
                )
                if amount_usdt > 0:
                    quantity = amount_usdt / market_data.current_price

            # Final check and execution
            if quantity > 0:
                # WeEx requires stepSize of 0.1 for cmt_bnbusdt
                # Round to 1 decimal place to match exchange requirement
                quantity = round(quantity, 1)

                # For testnet mode, skip actual order execution (CCXT deprecated private API)
                if config.trading_mode == "testnet":
                    order_id = f"SIM-{symbol}-{decision.action}"
                    logger.info(f"[SIMULATED] Order: {decision.action} {quantity} {symbol}")
                else:
                    order_id = await self.order_mgr.execute_order(
                        decision, symbol, quantity
                    )

                # Persist position changes
                if self.persistence_service and order_id:
                    await self._persist_position_change(
                        action=decision.action,
                        symbol=symbol,
                        price=market_data.current_price,
                        size=quantity,
                        leverage=decision.leverage,
                        position=position,
                        decision=decision,
                        technical=tech,
                        market_state=tech.trend if tech else "unknown",
                    )

        # 4. 报告
        # Get position after trade (wait a bit? or just report 'submitted')
        # We pass None for position_after for now as it takes time to fill
        self.reporter.generate(market_data, tech, decision, position, None, 0.0)

        # 5. 发布账户状态到 Redis（供 Dashboard 获取）
        await self._publish_account_state(symbol, account, position, market_data.current_price)
