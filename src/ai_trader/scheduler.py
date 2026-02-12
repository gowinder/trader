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
from .persistence import DatabaseManager, DecisionPersistenceService, StrategyPresetService
from .reporter import Reporter
from .memory import TradeMemoryCollector
from .ai.usage_tracker import get_usage_tracker
from .reflection.service import ReflectionClient
from .optimization import ParameterRegistry, ShadowRunner
from .advisory.service import AdvisoryService
from .advisory.engine import AdvisoryEngine
from .advisory.llm_client import AdvisoryLLMClient
from .advisory.persistence import AdvisoryPersistenceService
from .advisory.context import AdvisoryContextBuilder
from .advisory.triggers import TriggerManager, TriggerConfig
from .advisory.telegram import TelegramBot
from .notification import NotificationManager


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

        # Track current position for persistence (per symbol)
        self._current_position_ids: dict = {}  # symbol -> UUID

        # Memory and optimization system
        self.memory_collector: Optional[TradeMemoryCollector] = None
        self.reflection_client: Optional[ReflectionClient] = None
        self.shadow_runner: Optional[ShadowRunner] = None
        self.parameter_registry = ParameterRegistry()

        self.running = False

        # Symbol-level locks to prevent concurrent advisory execution and main loop
        self._symbol_locks: dict = {}

        # Advisory system
        self._advisory_service: Optional[AdvisoryService] = None
        self._advisory_tasks: list = []
        self._price_history: dict = {}
        self._consecutive_losses: int = 0

        # Notification manager
        self._notification_manager: Optional[NotificationManager] = None

        # Redis for dynamic config
        self._redis: Optional[redis.Redis] = None
        self._trading_enabled = True
        self._decision_interval = config.decision_interval

        # Strategy preset
        self._active_preset_name: Optional[str] = None
        self._strategy_preset_service: Optional[StrategyPresetService] = None

    def _get_symbol_lock(self, symbol: str) -> asyncio.Lock:
        """获取 symbol 级别的锁，防止 advisory 执行与主循环并发操作同一 symbol"""
        if symbol not in self._symbol_locks:
            self._symbol_locks[symbol] = asyncio.Lock()
        return self._symbol_locks[symbol]

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

            # Initialize strategy preset service
            self._strategy_preset_service = StrategyPresetService(self.db_manager)
            await self._strategy_preset_service.init_system_presets()
            await self._strategy_preset_service.ensure_default_active()
            await self._load_active_preset()
        except Exception as e:
            logger.error(f"Failed to initialize persistence service: {e}")
            self.db_manager = None
            self.persistence_service = None

    async def _init_advisory(self):
        """初始化 Advisory 系统"""
        if not config.advisory_enabled:
            return
        if not self._persistence_initialized:
            logger.warning("Advisory requires persistence, but persistence not initialized")
            return
        try:
            # 从 Redis 读取 Advisory LLM 配置（配置由 Dashboard 管理）
            llm_cfg = None
            if self._redis:
                try:
                    llm_data = await self._redis.get("advisory:llm_config")
                    if not llm_data:
                        # 兼容旧 key
                        llm_data = await self._redis.get("llm:advisory:config")
                    if llm_data:
                        llm_cfg = json.loads(llm_data)
                except Exception:
                    pass

            if not llm_cfg or not llm_cfg.get("provider") or not llm_cfg.get("model"):
                logger.warning(
                    "Advisory LLM 未配置，请在 Dashboard Advisory Settings 中配置 LLM 路由。"
                    " Advisory 系统将跳过初始化。"
                )
                return

            # 从 providers pool 中获取 api_key 和 base_url（如果 llm_cfg 中没有）
            api_key = llm_cfg.get("api_key", "")
            base_url = llm_cfg.get("base_url", "")
            if self._redis and (not api_key or not base_url):
                try:
                    pool_data = await self._redis.get("llm:providers:pool")
                    if pool_data:
                        pool = json.loads(pool_data)
                        provider_info = pool.get(llm_cfg["provider"], {})
                        if not api_key:
                            api_key = provider_info.get("api_key", "")
                        if not base_url:
                            base_url = provider_info.get("base_url", "")
                except Exception:
                    pass

            llm_client = AdvisoryLLMClient(
                provider=llm_cfg["provider"],
                model=llm_cfg["model"],
                api_key=api_key,
                base_url=base_url,
                timeout=llm_cfg.get("timeout", 120.0),
            )
            persistence = AdvisoryPersistenceService(self.db_manager) if self.db_manager else None
            context_builder = AdvisoryContextBuilder(db=self.db_manager)
            engine = AdvisoryEngine(llm_client, persistence, context_builder)

            trigger_config = TriggerConfig(interval_minutes=config.advisory_interval_minutes)
            if self._redis:
                try:
                    data = await self._redis.get("advisory:trigger_config")
                    if data:
                        cfg = json.loads(data)
                        trigger_config = TriggerConfig(**cfg)
                except Exception:
                    pass

            trigger_mgr = TriggerManager(trigger_config)

            # 初始化 Telegram Bot（统一管理 polling + 推送 + 命令）
            self._telegram_bot = TelegramBot(
                bot_token=config.telegram_bot_token,
                chat_id=config.telegram_chat_id,
                redis=self._redis,
                db=self.db_manager,
                persistence=self.persistence_service,
                strategy_service=self._strategy_preset_service,
                advisory_persistence=persistence,
            )
            notifier = self._telegram_bot.notifier

            # 初始化通知管理器
            self._notification_manager = NotificationManager(
                notifier=notifier, redis_client=self._redis,
            )
            await self._notification_manager.load_config()

            self._advisory_service = AdvisoryService(
                engine=engine, trigger_manager=trigger_mgr,
                notifier=notifier, persistence=persistence,
            )
            # 在 advisory_service 就绪后启动执行队列监听
            if self._redis:
                self._advisory_tasks.append(asyncio.create_task(self._advisory_execute_listener()))
                self._advisory_tasks.append(asyncio.create_task(self._telegram_actions_listener()))
            # 启动 Telegram Bot（polling + 命令处理，替代原 callback handler）
            if self._telegram_bot.enabled:
                await self._telegram_bot.start()
            # 启动手动触发监听
            if self._redis:
                self._advisory_tasks.append(asyncio.create_task(self._advisory_manual_trigger_listener()))
            logger.info("Advisory system initialized")
        except Exception as e:
            logger.error(f"Failed to initialize advisory system: {e}")

    async def _init_redis(self):
        """初始化 Redis 连接"""
        try:
            self._redis = redis.from_url(config.redis_url, decode_responses=True)
            await self._redis.ping()
            logger.info("Redis connected for dynamic config")

            # Load initial config from Redis
            await self._load_trading_config()
            await self._load_llm_providers_config()

            # Start config listener in background
            asyncio.create_task(self._config_listener())
            asyncio.create_task(self._manual_trigger_listener())
            asyncio.create_task(self._backtest_task_listener())
        except Exception as e:
            logger.warning(f"Redis not available, using static config: {e}")
            self._redis = None

    async def _load_active_preset(self):
        """从 Redis 或 PG 加载活跃策略预设并应用到配置"""
        preset_data = None

        # 优先从 Redis 读取
        if self._redis:
            try:
                data = await self._redis.get("strategy:active_preset")
                if data:
                    preset_data = json.loads(data)
            except Exception as e:
                logger.error(f"Failed to load preset from Redis: {e}")

        # Redis 没有则从 PG 读取
        if preset_data is None and self._strategy_preset_service:
            active = await self._strategy_preset_service.get_active_preset()
            if active:
                preset_config = active["config_json"]
                if isinstance(preset_config, str):
                    preset_config = json.loads(preset_config)
                preset_data = {"name": active["name"], "config": preset_config}
                self._active_preset_name = active["name"]
                # 写入 Redis 缓存
                if self._redis:
                    try:
                        await self._redis.set(
                            "strategy:active_preset",
                            json.dumps(preset_data),
                        )
                    except Exception:
                        pass

        if preset_data:
            preset_config = preset_data.get("config", preset_data)
            self._active_preset_name = preset_data.get("name", self._active_preset_name)
            config.apply_preset(preset_config)

            # 重建决策引擎
            self.decision_engine = HybridDecisionEngine(self.llm)
            self.decision_engine.active_preset_name = self._active_preset_name

            # 更新信号过滤器间隔
            interval_sec = preset_config.get("min_trade_interval_seconds", 21600)
            if hasattr(self.decision_engine, "signal_filter") and self.decision_engine.signal_filter:
                self.decision_engine.signal_filter.min_interval_hours = interval_sec / 3600

            logger.info(f"Applied strategy preset: {self._active_preset_name}")

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

    async def _load_llm_providers_config(self):
        """从 Redis 加载 LLM provider 优先级配置"""
        if not self._redis:
            return

        try:
            data = await self._redis.get("llm:providers:config")
            if data:
                cfg = json.loads(data)
                providers = cfg.get("providers", [])
                if providers:
                    from .ai.llm_manager import get_llm_manager
                    manager = get_llm_manager()
                    manager.update_providers(providers)
                    logger.info(f"Loaded LLM providers config: {[p.get('name') for p in providers]}")
        except Exception as e:
            logger.error(f"Failed to load LLM providers config: {e}")

    async def _config_listener(self):
        """监听配置更新"""
        if not self._redis:
            return

        try:
            pubsub = self._redis.pubsub()
            await pubsub.subscribe("trading:config:updated", "strategy:preset:updated", "llm:providers:updated", "advisory:config:updated", "advisory:llm_config:updated", "llm:config:updated", "notification:config:updated", "notification:test")

            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        channel = message.get("channel", b"").decode() if isinstance(message.get("channel"), bytes) else message.get("channel", "")
                        if channel == "strategy:preset:updated":
                            logger.info("Strategy preset update received")
                            await self._load_active_preset()
                        elif channel == "llm:providers:updated":
                            cfg = json.loads(message["data"])
                            providers = cfg.get("providers", [])
                            if providers:
                                from .ai.llm_manager import get_llm_manager
                                manager = get_llm_manager()
                                manager.update_providers(providers)
                                logger.info(f"LLM providers updated: {[p.get('name') for p in providers]}")
                        elif channel == "advisory:config:updated":
                            cfg = json.loads(message["data"])
                            if self._advisory_service:
                                new_trigger_cfg = TriggerConfig(**cfg)
                                self._advisory_service.trigger_mgr.update_config(new_trigger_cfg)
                                logger.info(f"Advisory trigger config updated: {cfg}")
                        elif channel == "advisory:llm_config:updated":
                            llm_cfg = json.loads(message["data"])
                            provider = llm_cfg.get("provider", "")
                            model = llm_cfg.get("model", "")
                            api_key = llm_cfg.get("api_key", "")
                            base_url = llm_cfg.get("base_url", "")
                            # 从 providers pool 补全 api_key/base_url
                            if self._redis and (not api_key or not base_url):
                                try:
                                    pool_data = await self._redis.get("llm:providers:pool")
                                    if pool_data:
                                        pool = json.loads(pool_data)
                                        pinfo = pool.get(provider, {})
                                        if not api_key:
                                            api_key = pinfo.get("api_key", "")
                                        if not base_url:
                                            base_url = pinfo.get("base_url", "")
                                except Exception:
                                    pass
                            if self._advisory_service and provider and model:
                                old_client = self._advisory_service.engine.llm
                                new_client = AdvisoryLLMClient(
                                    provider=provider,
                                    model=model,
                                    api_key=api_key,
                                    base_url=base_url,
                                    timeout=llm_cfg.get("timeout", 120.0),
                                )
                                self._advisory_service.engine.llm = new_client
                                if old_client:
                                    try:
                                        await old_client.close()
                                    except Exception:
                                        pass
                                logger.info(f"Advisory LLM config updated: provider={provider}, model={model}")
                            elif not self._advisory_service and provider and model:
                                # Advisory 之前因缺少配置未初始化，现在尝试初始化
                                logger.info("Advisory LLM config received, attempting to initialize advisory system")
                                await self._init_advisory()
                        elif channel == "llm:config:updated":
                            cfg = json.loads(message["data"])
                            update_type = cfg.get("type", "")
                            if update_type == "routing" and cfg.get("scope") == "main":
                                from .ai.llm_manager import get_llm_manager
                                manager = get_llm_manager()
                                config_data = cfg.get("config", {})
                                providers_pool = config_data.get("providers", {})
                                routing = config_data.get("routing", [])
                                strategy = config_data.get("strategy")
                                manager.update_providers(routing, providers_pool=providers_pool, strategy=strategy)
                                logger.info("LLM full config updated via llm:config:updated")
                            elif update_type == "providers":
                                from .ai.llm_manager import get_llm_manager
                                manager = get_llm_manager()
                                providers_pool = cfg.get("providers", {})
                                manager._providers_pool = providers_pool
                                manager._providers.clear()
                                logger.info("LLM providers pool refreshed")
                        elif channel == "notification:config:updated":
                            cfg = json.loads(message["data"])
                            if self._notification_manager:
                                self._notification_manager.update_config(cfg)
                                logger.info("Notification config updated")
                        elif channel == "notification:test":
                            if self._notification_manager:
                                await self._notification_manager.send_test_message()
                                logger.info("Notification test message sent")
                        else:
                            cfg = json.loads(message["data"])
                            self._trading_enabled = cfg.get("enabled", True)
                            interval_minutes = cfg.get("decisionInterval", 1)
                            self._decision_interval = interval_minutes * 60
                            # 同步交易对配置变更
                            if "trading_symbols" in cfg:
                                config.trading_symbols = cfg["trading_symbols"]
                                logger.info(f"Trading symbols updated: {config.symbols_list}")
                            # 同步其他运行时参数
                            for param in ["stop_loss_percent", "take_profit_percent", "leverage_max", "quant_weight", "ai_weight"]:
                                if param in cfg:
                                    setattr(config, param, cfg[param])
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

            # 发送回测完成通知
            if self._notification_manager:
                await self._notification_manager.notify_backtest(
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date,
                    return_pct=result.return_pct,
                    win_rate=result.win_rate,
                    max_drawdown_pct=result.max_drawdown_pct,
                    sharpe_ratio=result.sharpe_ratio,
                    total_trades=result.total_trades,
                )

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
        logger.info(f"Scheduler started for {len(config.symbols_list)} symbol(s): {', '.join(config.symbols_list)}")

        # Initialize persistence if enabled
        await self._init_persistence()

        # Initialize Redis for dynamic config
        await self._init_redis()

        # Initialize Advisory system
        await self._init_advisory()

        while self.running:
            # Check if trading is enabled
            if not self._trading_enabled:
                logger.debug("Trading paused, waiting...")
                await asyncio.sleep(5)
                continue

            try:
                # Run cycle for each symbol (re-read from config for hot-reload)
                for symbol in config.symbols_list:
                    try:
                        await self.run_cycle_for_symbol(symbol)
                    except Exception as e:
                        logger.error(f"Error in cycle for {symbol}: {e}")

                # Run advisory check (后台执行，不阻塞主循环)
                if self._advisory_service:
                    task = asyncio.create_task(self._run_advisory_check())
                    self._advisory_tasks.append(task)
                    # 清理已完成的 tasks 避免列表无限增长
                    self._advisory_tasks = [t for t in self._advisory_tasks if not t.done()]
            except Exception as e:
                logger.error(f"Error in main cycle: {e}")

            logger.info(f"Waiting {self._decision_interval}s...")
            await asyncio.sleep(self._decision_interval)

    async def stop(self):
        """停止调度器"""
        self.running = False
        # 取消 advisory 后台 tasks
        for task in self._advisory_tasks:
            if not task.done():
                task.cancel()
        self._advisory_tasks.clear()
        # 停止 Telegram Bot
        if hasattr(self, '_telegram_bot') and self._telegram_bot:
            await self._telegram_bot.stop()
        # 停止 advisory 相关资源
        if self._advisory_service:
            if hasattr(self._advisory_service, 'engine') and self._advisory_service.engine and hasattr(self._advisory_service.engine, 'llm'):
                try:
                    await self._advisory_service.engine.llm.close()
                except Exception:
                    pass
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

    async def _check_stop_loss_take_profit(
        self, symbol: str, position, current_price: float
    ) -> Optional[str]:
        """检查当前持仓是否触发止损或止盈，返回平仓 action 或 None。"""
        if not position or position.size <= 0:
            return None

        entry_price = position.entry_price
        side = position.side.lower()

        # 尝试从 decisions 表获取开仓决策的止损止盈
        stop_loss = None
        take_profit = None
        if self.db_manager and self._current_position_ids.get(symbol):
            row = await self.db_manager.fetchrow(
                """
                SELECT d.stop_loss, d.take_profit
                FROM position_history ph
                JOIN decisions d ON d.id = ph.entry_decision_id
                WHERE ph.id = $1
                """,
                self._current_position_ids.get(symbol),
            )
            if row:
                stop_loss = float(row["stop_loss"]) if row["stop_loss"] else None
                take_profit = float(row["take_profit"]) if row["take_profit"] else None

        # 如果数据库没有，用配置百分比计算
        if stop_loss is None:
            sl_pct = config.stop_loss_percent / 100.0
            if side == "long":
                stop_loss = entry_price * (1 - sl_pct)
            else:
                stop_loss = entry_price * (1 + sl_pct)

        if take_profit is None:
            tp_pct = config.take_profit_percent / 100.0
            if side == "long":
                take_profit = entry_price * (1 + tp_pct)
            else:
                take_profit = entry_price * (1 - tp_pct)

        # 检查触发条件
        if side == "long":
            if current_price <= stop_loss:
                logger.info(
                    f"[SL TRIGGERED] {symbol} LONG: price={current_price} <= stop_loss={stop_loss}"
                )
                return "close_long"
            if current_price >= take_profit:
                logger.info(
                    f"[TP TRIGGERED] {symbol} LONG: price={current_price} >= take_profit={take_profit}"
                )
                return "close_long"
        else:  # short
            if current_price >= stop_loss:
                logger.info(
                    f"[SL TRIGGERED] {symbol} SHORT: price={current_price} >= stop_loss={stop_loss}"
                )
                return "close_short"
            if current_price <= take_profit:
                logger.info(
                    f"[TP TRIGGERED] {symbol} SHORT: price={current_price} <= take_profit={take_profit}"
                )
                return "close_short"

        return None

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
                self._current_position_ids[symbol] = position_id
                logger.info(f"Position opened and persisted: {position_id}")

                # 发送开仓/加仓通知
                if self._notification_manager:
                    await self._notification_manager.notify_trade(
                        symbol=symbol, action=action, price=price,
                        size=size, leverage=leverage,
                        stop_loss=decision.stop_loss_price if decision else None,
                        take_profit=decision.take_profit_price if decision else None,
                    )

            elif action in ["close_long", "close_short"]:
                # 平仓
                if not self._current_position_ids.get(symbol) and self.db_manager:
                    row = await self.db_manager.fetchrow(
                        """
                        SELECT id
                        FROM position_history
                        WHERE symbol = $1
                          AND status = 'open'
                          AND entry_size > 0
                        ORDER BY entry_time DESC
                        LIMIT 1
                        """,
                        symbol,
                    )
                    if row:
                        self._current_position_ids[symbol] = row["id"]

                if self._current_position_ids.get(symbol) and position:
                    # 计算盈亏
                    entry_price = position.entry_price
                    pnl = (price - entry_price) * size
                    if action == "close_short":
                        pnl = -pnl  # 空仓盈亏反向
                    pnl_percent = (pnl / (entry_price * size)) * 100

                    await self.persistence_service.save_position_close(
                        position_id=self._current_position_ids.get(symbol),
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

                    logger.info(f"Position closed and persisted: {self._current_position_ids.get(symbol)}, pnl={pnl:.2f}")
                    self._current_position_ids.pop(symbol, None)

                    # 发送平仓通知
                    if self._notification_manager:
                        await self._notification_manager.notify_trade(
                            symbol=symbol, action=action, price=price,
                            size=size, leverage=leverage,
                        )

                    # 更新连续亏损计数
                    if pnl < 0:
                        self._consecutive_losses += 1
                    else:
                        self._consecutive_losses = 0

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

                    # 发送减仓通知
                    if self._notification_manager:
                        await self._notification_manager.notify_trade(
                            symbol=symbol, action=action, price=price,
                            size=size, leverage=leverage,
                        )

        except Exception as e:
            logger.error(f"Failed to persist position change: {e}")

    async def _telegram_actions_listener(self):
        """监听 Telegram 操作队列，将按钮操作同步到数据库"""
        if not self._redis or not self._advisory_service:
            return
        persistence = self._advisory_service.persistence
        if not persistence:
            return
        logger.info("Telegram actions listener started")
        while self.running:
            try:
                result = await self._redis.brpop("advisory:telegram_actions", timeout=5)
                if result:
                    _, action_json = result
                    action_data = json.loads(action_json)
                    advisory_id = action_data.get("advisory_id")
                    idx = action_data.get("index", 0)
                    action_type = action_data.get("action")

                    # 定向查询建议（按 advisory_id + sort_order）
                    from uuid import UUID as _UUID
                    suggestion = await persistence.get_suggestion_by_advisory_and_index(
                        _UUID(advisory_id), idx
                    )
                    if not suggestion:
                        logger.warning(f"Telegram action: suggestion not found for advisory={advisory_id} idx={idx}")
                        continue

                    sid = suggestion["id"]

                    if action_type == "accept":
                        await persistence.update_suggestion_status_if(sid, "accepted", "pending")
                    elif action_type == "reject":
                        # reject 可以从 pending 或 accepted 状态触发
                        ok = await persistence.update_suggestion_status_if(sid, "rejected", "pending")
                        if not ok:
                            ok = await persistence.update_suggestion_status_if(sid, "rejected", "accepted")
                        if ok:
                            await persistence.try_resolve_advisory_for_suggestion(sid)
                    elif action_type == "confirm":
                        # 原子校验: 仅 accepted -> confirmed，防止重复执行
                        ok = await persistence.update_suggestion_status_if(sid, "confirmed", "accepted")
                        if ok:
                            try:
                                await self._redis.lpush("advisory:execute_tasks", json.dumps({
                                    "suggestion_id": str(sid),
                                    "type": suggestion.get("type"),
                                    "target": suggestion.get("target"),
                                    "action": suggestion.get("action"),
                                    "detail": suggestion.get("detail"),
                                }))
                            except Exception as queue_err:
                                # 入队失败，回滚状态
                                await persistence.update_suggestion_status_if(sid, "accepted", "confirmed")
                                logger.error(f"Telegram confirm queue failed, rolled back: {queue_err}")
                        else:
                            logger.warning(f"Telegram confirm skipped: suggestion {sid} not in 'accepted' state")
                    elif action_type == "cancel":
                        # cancel 从 accepted 回退到 pending
                        await persistence.update_suggestion_status_if(sid, "pending", "accepted")

                    logger.info(f"Telegram action processed: {action_type} advisory={advisory_id} idx={idx}")
            except Exception as e:
                if self.running:
                    logger.error(f"Telegram actions listener error: {e}")
                await asyncio.sleep(5)

    async def _advisory_execute_listener(self):
        """监听 advisory 执行队列"""
        if not self._redis or not self._advisory_service:
            return
        logger.info("Advisory execution queue listener started")
        while self.running:
            try:
                result = await self._redis.brpop("advisory:execute_tasks", timeout=5)
                if result:
                    _, task_json = result
                    task = json.loads(task_json)
                    await self._execute_advisory_suggestion(task)
            except Exception as e:
                if self.running:
                    logger.error(f"Advisory execution error: {e}")
                await asyncio.sleep(5)

    async def _execute_advisory_suggestion(self, task: dict):
        """执行单条 advisory suggestion"""
        from .advisory.executors import ConfigExecutor, TradeExecutor, SymbolExecutor, ExecutionResult

        suggestion_id = task.get("suggestion_id")
        suggestion_type = task.get("type")
        target = task.get("target", "")
        action = task.get("action", "")
        detail = task.get("detail", {})

        try:
            if suggestion_type == "param_adjust":
                executor = ConfigExecutor(self._redis)
                result = await executor.execute(action, target, detail)
            elif suggestion_type == "position_action":
                if not self.position_mgr:
                    result = ExecutionResult(success=False, message="Position manager not initialized")
                else:
                    # 使用 symbol 锁防止与主交易循环并发操作同一 symbol
                    async with self._get_symbol_lock(target):
                        executor = TradeExecutor(self.order_mgr, self.position_mgr)
                        # 执行前获取仓位信息用于持久化
                        pre_position = await self.position_mgr.get_position(target)
                        result = await executor.execute(action, target, detail)
                        # 执行成功后同步持仓持久化（在锁内避免与主循环竞态）
                        if result.success and pre_position and self.persistence_service:
                            try:
                                persist_action = action
                                if action == "close_position":
                                    persist_action = f"close_{pre_position.side}"
                                elif action == "reduce_position":
                                    persist_action = f"reduce_{pre_position.side}"
                                ticker = await self.exchange.get_ticker(target) if hasattr(self, "exchange") and self.exchange else None
                                current_price = ticker.last_price if ticker else (pre_position.entry_price or 0)
                                persist_size = pre_position.size
                                if action == "reduce_position":
                                    raw_pct = detail.get("reduce_percent", 50) if isinstance(detail, dict) else 50
                                    persist_size = pre_position.size * (raw_pct / 100)
                                await self._persist_position_change(
                                    action=persist_action,
                                    symbol=target,
                                    price=current_price,
                                    size=persist_size,
                                    leverage=pre_position.leverage or 1,
                                    position=pre_position,
                                    market_state="advisory",
                                )
                            except Exception as persist_err:
                                logger.error(f"Advisory position persist failed: {persist_err}")
            elif suggestion_type == "symbol_change":
                executor = SymbolExecutor(self._redis)
                result = await executor.execute(action, target, detail)
            else:
                result = ExecutionResult(success=False, message=f"未知类型: {suggestion_type}")

            if self._advisory_service and self._advisory_service.persistence and suggestion_id:
                from uuid import UUID
                sid = UUID(suggestion_id) if isinstance(suggestion_id, str) else suggestion_id
                status = "executed" if result.success else "failed"
                await self._advisory_service.persistence.update_suggestion_status(
                    sid, status,
                    execution_result={"success": result.success, "message": result.message},
                )
                # 检查是否所有建议都已终态，自动 resolve advisory
                await self._advisory_service.persistence.try_resolve_advisory_for_suggestion(sid)

            logger.info(f"Advisory suggestion executed: {suggestion_id} -> {result.success}: {result.message}")
        except Exception as e:
            logger.error(f"Advisory suggestion execution failed: {e}")
            if self._advisory_service and self._advisory_service.persistence and suggestion_id:
                from uuid import UUID
                sid = UUID(suggestion_id) if isinstance(suggestion_id, str) else suggestion_id
                await self._advisory_service.persistence.update_suggestion_status(
                    sid,
                    "failed",
                    execution_result={"error": str(e)},
                )
                # 异常路径也需要检查 advisory 收敛
                await self._advisory_service.persistence.try_resolve_advisory_for_suggestion(sid)

    async def _advisory_manual_trigger_listener(self):
        """监听手动触发 advisory 分析"""
        if not self._redis or not self._advisory_service:
            return
        try:
            pubsub = self._redis.pubsub()
            await pubsub.subscribe("advisory:manual_trigger")
            logger.info("Advisory manual trigger listener started")
            async for message in pubsub.listen():
                if message["type"] == "message":
                    logger.info("Received manual advisory trigger")
                    try:
                        await self._run_advisory_check(force=True)
                    except Exception as e:
                        logger.error(f"Manual advisory trigger error: {e}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Advisory manual trigger listener error: {e}")

    async def _run_advisory_check(self, force: bool = False):
        """运行 advisory 检查"""
        if not self._advisory_service:
            return
        try:
            symbols = config.symbols_list
            positions = []
            market_data = {}
            price_context = {}

            is_testnet = config.trading_mode == "testnet"

            for symbol in symbols:
                try:
                    ticker = await self.exchange.get_ticker(symbol)
                    current_price = ticker.last_price if ticker else 0
                    market_data[symbol] = {
                        "current_price": current_price,
                        "change_24h": ticker.change_24h if ticker else 0,
                    }
                    previous = self._price_history.get(symbol)
                    if previous:
                        price_context[symbol] = {"current": current_price, "previous": previous}
                    self._price_history[symbol] = current_price

                    # testnet 用虚拟仓位，live 用交易所仓位
                    if is_testnet:
                        pos = await self._load_testnet_virtual_position(symbol, current_price)
                    else:
                        pos = await self.position_mgr.get_position(symbol)
                    if pos and pos.size > 0:
                        positions.append({
                            "symbol": pos.symbol, "side": pos.side,
                            "size": pos.size, "entry_price": pos.entry_price,
                            "unrealized_pnl": pos.unrealized_pnl,
                            "roi": pos.roi, "leverage": pos.leverage,
                        })
                except Exception as e:
                    logger.debug(f"Advisory data collection error for {symbol}: {e}")

            current_config = {
                "stop_loss_percent": config.stop_loss_percent,
                "take_profit_percent": config.take_profit_percent,
                "leverage_max": config.leverage_max,
                "quant_weight": config.quant_weight,
                "ai_weight": config.ai_weight,
            }

            # 收集账户信息
            account_summary = None
            try:
                if is_testnet:
                    # testnet 构建虚拟账户（汇总所有 symbol 的仓位信息）
                    total_margin = 0.0
                    total_upnl = 0.0
                    for p in positions:
                        entry = p.get("entry_price", 0)
                        size = p.get("size", 0)
                        lev = p.get("leverage", 1) or 1
                        total_margin += (entry * size) / lev
                        total_upnl += p.get("unrealized_pnl", 0) or 0
                    base_equity = 10000.0
                    account_summary = {
                        "total_equity": base_equity + total_upnl,
                        "available_balance": max(base_equity + total_upnl - total_margin, 0),
                        "margin_used": total_margin,
                    }
                else:
                    account = await self.exchange.get_account()
                    if account:
                        account_summary = {
                            "total_equity": account.total_equity,
                            "available_balance": account.available_balance,
                            "margin_used": getattr(account, 'margin_used', None),
                        }
            except Exception:
                pass

            if force:
                await self._advisory_service.force_run(
                    symbols=symbols, positions=positions,
                    market_data=market_data, sentiment=None,
                    current_config=current_config,
                    account_summary=account_summary,
                )
            else:
                await self._advisory_service.check_and_run(
                    symbols=symbols, positions=positions,
                    market_data=market_data, sentiment=None,
                    current_config=current_config,
                    consecutive_losses=self._consecutive_losses,
                    price_context=price_context,
                    account_summary=account_summary,
                )
        except Exception as e:
            logger.error(f"Advisory check error: {e}")

    async def run_cycle(self):
        """执行单次交易循环（兼容旧版单 symbol）"""
        await self.run_cycle_for_symbol(config.trading_symbol)

    async def _load_testnet_virtual_position(self, symbol: str, mark_price: float):
        """在 testnet 模式下从数据库恢复当前持仓，形成闭环。"""
        if not self.db_manager:
            self._current_position_ids.pop(symbol, None)
            return None

        rows = await self.db_manager.fetch(
            """
            SELECT
                id,
                symbol,
                side,
                entry_price,
                entry_size,
                COALESCE(leverage, 1) AS leverage
            FROM position_history
            WHERE symbol = $1
              AND status = 'open'
              AND entry_size > 0
            ORDER BY entry_time DESC
            """,
            symbol,
        )

        if not rows:
            self._current_position_ids.pop(symbol, None)
            return None

        if len(rows) > 1:
            logger.warning(
                f"Found {len(rows)} open positions for {symbol} in testnet, using latest one"
            )

        row = rows[0]
        side = str(row["side"]).lower()
        entry_price = float(row["entry_price"])
        size = float(row["entry_size"])
        leverage = max(1, int(float(row["leverage"])))

        if side == "long":
            unrealized_pnl = (mark_price - entry_price) * size
        else:
            unrealized_pnl = (entry_price - mark_price) * size

        margin = (entry_price * size) / leverage if leverage > 0 else 0.0
        roi = (unrealized_pnl / margin * 100) if margin > 0 else 0.0

        from .exchange.base import Position

        position = Position(
            symbol=str(row["symbol"]),
            side=side,
            size=size,
            entry_price=entry_price,
            mark_price=mark_price,
            unrealized_pnl=unrealized_pnl,
            leverage=leverage,
            margin_mode="isolated",
            liquidation_price=None,
            margin=margin,
            roi=roi,
        )

        self._current_position_ids[symbol] = row["id"]
        return position

    async def _build_testnet_account_state(self, symbol: str, current_price: float):
        """构建 testnet 虚拟账户状态（含本地持仓）。"""
        from .exchange.base import AccountInfo

        position = await self._load_testnet_virtual_position(symbol, current_price)
        base_equity = 10000.0

        margin_used = position.margin if position else 0.0
        unrealized_pnl = position.unrealized_pnl if position else 0.0
        total_equity = base_equity + unrealized_pnl
        available_balance = max(total_equity - margin_used, 0.0)

        account = AccountInfo(
            total_equity=total_equity,
            available_balance=available_balance,
            margin_used=margin_used,
            unrealized_pnl=unrealized_pnl,
        )
        return account, position

    async def run_cycle_for_symbol(self, symbol: str):
        """执行指定 symbol 的交易循环"""
        async with self._get_symbol_lock(symbol):
            await self._run_cycle_for_symbol_impl(symbol)

    async def _run_cycle_for_symbol_impl(self, symbol: str):
        """执行指定 symbol 的交易循环（内部实现，已持有 symbol 锁）"""
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
            account, position = await self._build_testnet_account_state(
                symbol, market_data.current_price
            )
            logger.info(
                "Using simulated account data for testnet with virtual position tracking"
            )
        else:
            position = await self.position_mgr.get_position(symbol)
            account = await self.exchange.get_account()  # Now returns AccountInfo model

            # Live 模式：重启后从数据库恢复 _current_position_ids
            if position and position.size > 0 and not self._current_position_ids.get(symbol) and self.db_manager:
                row = await self.db_manager.fetchrow(
                    """
                    SELECT id FROM position_history
                    WHERE symbol = $1 AND status = 'open' AND entry_size > 0
                    ORDER BY entry_time DESC LIMIT 1
                    """,
                    symbol,
                )
                if row:
                    self._current_position_ids[symbol] = row["id"]
                    logger.info(f"Recovered position_id {self._current_position_ids[symbol]} for {symbol} from database")
                else:
                    logger.warning(f"Position exists in exchange but not found in database for {symbol}")

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

        # 1.5 止损止盈自动检查（在 LLM 决策之前）
        if position and position.size > 0 and self._current_position_ids.get(symbol):
            sl_tp_action = await self._check_stop_loss_take_profit(
                symbol, position, market_data.current_price
            )
            if sl_tp_action:
                from .models.decision import TradingDecision

                # 发送止损/止盈通知
                if self._notification_manager:
                    side = position.side.lower()
                    entry_price = position.entry_price
                    pnl_pct = ((market_data.current_price - entry_price) / entry_price) * 100
                    if side == "short":
                        pnl_pct = -pnl_pct
                    is_sl = ("close_long" == sl_tp_action and market_data.current_price < entry_price) or \
                            ("close_short" == sl_tp_action and market_data.current_price > entry_price)
                    await self._notification_manager.notify_stop_loss_take_profit(
                        symbol=symbol,
                        side=side,
                        trigger_type="stop_loss" if is_sl else "take_profit",
                        entry_price=entry_price,
                        trigger_price=market_data.current_price,
                        pnl_percent=pnl_pct,
                    )

                quantity = position.size
                if config.trading_mode == "testnet":
                    quantity = round(quantity, 6)
                else:
                    quantity = round(quantity, 1)

                if quantity > 0:
                    if config.trading_mode == "testnet":
                        order_id = f"SIM-{symbol}-{sl_tp_action}"
                        logger.info(f"[SL/TP AUTO] Order: {sl_tp_action} {quantity} {symbol}")
                    else:
                        sl_decision = TradingDecision(
                            action=sl_tp_action,
                            confidence=100.0,
                            leverage=position.leverage,
                            position_size_percent=0,
                            reasoning=f"Auto {sl_tp_action}: SL/TP triggered at {market_data.current_price}",
                            execution_urgency="immediate",
                        )
                        order_id = await self.order_mgr.execute_order(
                            sl_decision, symbol, quantity
                        )

                    if self.persistence_service and order_id:
                        await self._persist_position_change(
                            action=sl_tp_action,
                            symbol=symbol,
                            price=market_data.current_price,
                            size=quantity,
                            leverage=position.leverage,
                            position=position,
                        )

                    await self._publish_account_state(symbol, account, position, market_data.current_price)
                    return

        # 2. 决策
        try:
            decision, tech, risk = await self.decision_engine.analyze_and_decide(
                market_data, position, balance, equity
            )
        except Exception as e:
            logger.error(f"Decision engine failed: {e}")
            return

        # 发送决策通知
        if self._notification_manager:
            await self._notification_manager.notify_decision(
                symbol=symbol,
                action=decision.action,
                confidence=decision.confidence,
                reasoning=decision.reasoning_zh or decision.reasoning,
            )

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
                if config.trading_mode == "testnet":
                    # testnet 仿真保留更高精度，避免小仓位被 round 到 0
                    quantity = round(quantity, 6)
                else:
                    # WeEx 生产环境沿用现有 0.1 步长假设
                    quantity = round(quantity, 1)

                if quantity <= 0:
                    logger.warning(
                        f"Quantity became non-positive after rounding: action={decision.action}, symbol={symbol}"
                    )
                else:
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
