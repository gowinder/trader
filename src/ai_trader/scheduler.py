"""调度器模块"""

import asyncio
import json
import time as _time
from dataclasses import dataclass
from datetime import datetime as _dt, timedelta as _td
from typing import Optional
from uuid import UUID

import pandas as pd
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
from .optimization.orchestrator import OptimizationOrchestrator
from .prompts.enricher import PromptContextEnricher
from .strategies.signal_filter import SignalFilter
from .strategies.strategy_base import SignalAction
from .advisory.service import AdvisoryService
from .advisory.engine import AdvisoryEngine
from .advisory.llm_client import AdvisoryLLMClient
from .advisory.persistence import AdvisoryPersistenceService
from .advisory.context import AdvisoryContextBuilder
from .advisory.triggers import TriggerManager, TriggerConfig
from .advisory.telegram import TelegramBot
from .notification import NotificationManager
from .events.detector import EventDetector
from .events.config import DEFAULT_EVENT_TRIGGER_CONFIG


class Scheduler:
    """任务调度器"""

    def __init__(self):
        # Use factory function to create exchange client based on config
        self.exchange = create_exchange_client()
        self.llm = LLMClient()

        self.market_mgr = MarketDataManager(self.exchange)
        self.order_mgr = OrderManager(self.exchange)
        self.position_mgr = PositionManager(self.exchange)

        # Phase 1: Multi-timeframe analysis
        from .data.multi_timeframe import MultiTimeframeManager
        self.mtf_manager = MultiTimeframeManager(self.exchange)

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
        self._optimization_orchestrator: Optional[OptimizationOrchestrator] = None

        # Phase 2: Strategy weight optimizer
        self._weight_optimizer = None
        self._last_weight_update: str = ""

        self.running = False

        # Symbol-level locks to prevent concurrent advisory execution and main loop
        self._symbol_locks: dict = {}

        # Advisory system
        self._advisory_service: Optional[AdvisoryService] = None
        self._advisory_tasks: list = []
        self._advisory_auto_execute: bool = False
        self._price_history: dict = {}
        self._consecutive_losses: int = 0
        self._trades_today: int = 0
        self._trades_today_date: str = ""

        # Notification manager
        self._notification_manager: Optional[NotificationManager] = None

        # Redis for dynamic config
        self._redis: Optional[redis.Redis] = None
        self._trading_enabled = True
        self._decision_interval = config.decision_interval

        # Event-driven trigger system (per-symbol isolation)
        self._event_detectors: dict[str, EventDetector] = {}  # per-symbol
        self._event_trigger_config: dict = dict(DEFAULT_EVENT_TRIGGER_CONFIG)
        self._decision_timers: dict[str, float] = {}  # per-symbol
        self._scan_interval: int = DEFAULT_EVENT_TRIGGER_CONFIG.get("scan_interval_seconds", 30)

        # Strategy preset
        self._active_preset_name: Optional[str] = None
        self._strategy_preset_service: Optional[StrategyPresetService] = None

        # Config lock for atomic config updates
        self._config_lock = asyncio.Lock()

        # Signal filters per symbol (anti-overtrade)
        self._signal_filters: dict[str, SignalFilter] = {}

        # Daily PnL tracking for loss-limit circuit breaker
        self._daily_pnl: dict[str, float] = {}  # symbol -> cumulative PnL today
        self._daily_pnl_date: str = ""  # current trading day YYYY-MM-DD
        self._trading_halted: bool = False  # set True when daily loss limit hit
        self._halt_until: Optional[str] = None  # ISO date string for forced-break end
        self._halt_consecutive_days: int = 0  # consecutive days that hit loss limit

    def _get_symbol_lock(self, symbol: str) -> asyncio.Lock:
        """获取 symbol 级别的锁，防止 advisory 执行与主循环并发操作同一 symbol"""
        if symbol not in self._symbol_locks:
            self._symbol_locks[symbol] = asyncio.Lock()
        return self._symbol_locks[symbol]

    def _get_emotional_state(self) -> str:
        """Return emotional state label based on recent trading performance."""
        if self._consecutive_losses >= 5:
            return "fearful"
        elif self._consecutive_losses >= 3:
            return "cautious"
        elif self._trading_halted:
            return "restricted"
        return "calm"

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
                self._optimization_orchestrator = OptimizationOrchestrator(
                    db=self.db_manager,
                    shadow_runner=self.shadow_runner,
                    parameter_registry=self.parameter_registry,
                    redis_client=self._redis,
                )
                logger.info("Memory and optimization system initialized (async mode)")

            # Phase 2: 初始化策略权重优化器
            if self.decision_engine.strategy_selector:
                from .optimization.weight_optimizer import StrategyWeightOptimizer
                self._weight_optimizer = StrategyWeightOptimizer(self.db_manager)
                logger.info("Strategy weight optimizer initialized")

            # 注入 Prompt 上下文增强器到决策引擎
            self.decision_engine.prompt_enricher = PromptContextEnricher(self.db_manager)

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
            persistence = AdvisoryPersistenceService(self.db_manager) if self.db_manager else None

            # 先初始化 Telegram Bot（不依赖 Advisory LLM 配置）
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

            # 启动 Telegram Bot（polling + 命令处理）
            if self._telegram_bot.enabled:
                await self._telegram_bot.start()

            # 启动 Telegram actions 监听
            if self._redis:
                self._advisory_tasks.append(asyncio.create_task(self._telegram_actions_listener()))

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
                    " Advisory 分析功能不可用，但 Telegram Bot 命令已启动。"
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
                timeout=llm_cfg.get("timeout", 180.0),
            )
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

            self._advisory_service = AdvisoryService(
                engine=engine, trigger_manager=trigger_mgr,
                notifier=notifier, persistence=persistence,
                db=self.db_manager,
            )
            # 读取自动执行配置
            if self._redis:
                try:
                    auto_exec = await self._redis.get("advisory:auto_execute")
                    if auto_exec is not None:
                        self._advisory_auto_execute = json.loads(auto_exec)
                        config.advisory_auto_execute = self._advisory_auto_execute
                        logger.info(f"Advisory auto-execute: {self._advisory_auto_execute}")
                except Exception:
                    pass
            # 在 advisory_service 就绪后启动执行队列监听
            if self._redis:
                self._advisory_tasks.append(asyncio.create_task(self._advisory_execute_listener()))
            # 启动手动触发监听
            if self._redis:
                self._advisory_tasks.append(asyncio.create_task(self._advisory_manual_trigger_listener()))
                self._advisory_tasks.append(asyncio.create_task(self._strategy_suggest_listener()))
            logger.info("Advisory system initialized")
        except Exception as e:
            logger.error(f"Failed to initialize advisory system: {e}")

    async def _init_redis(self):
        """初始化 Redis 连接"""
        try:
            self._redis = redis.from_url(config.redis_url, decode_responses=True)
            await self._redis.ping()
            logger.info("Redis connected for dynamic config")

            # 补设 orchestrator 的 redis 引用（_init_persistence 先于 _init_redis）
            if self._optimization_orchestrator:
                self._optimization_orchestrator._redis = self._redis

            # Load initial config from Redis
            await self._load_trading_config()
            await self._load_llm_providers_config()

            # Load event trigger config from Redis
            try:
                raw = await self._redis.get("trading:event_trigger_config")
                if raw:
                    self._event_trigger_config = json.loads(raw)
                    self._scan_interval = self._event_trigger_config.get("scan_interval_seconds", 30)
                    logger.info(f"Loaded event trigger config from Redis")
                else:
                    # Initialize default config in Redis
                    await self._redis.set(
                        "trading:event_trigger_config",
                        json.dumps(DEFAULT_EVENT_TRIGGER_CONFIG),
                    )
                    logger.info("Initialized default event trigger config in Redis")
            except Exception as e:
                logger.warning(f"Failed to load event trigger config: {e}")

            # Initialize per-symbol EventDetectors
            for symbol in config.symbols_list:
                self._event_detectors[symbol] = EventDetector(
                    event_config=self._event_trigger_config,
                    enabled_strategies=config.enabled_strategies,
                )
            logger.info(f"EventDetector initialized for {len(config.symbols_list)} symbol(s)")

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
                preset_data = {
                    "name": active["name"],
                    "config": preset_config,
                    "is_locked": active.get("is_locked", False),
                }
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

            # 重建决策引擎（保留 prompt_enricher 引用）
            old_enricher = getattr(self.decision_engine, "prompt_enricher", None)
            self.decision_engine = HybridDecisionEngine(self.llm)
            self.decision_engine.active_preset_name = self._active_preset_name
            self.decision_engine.prompt_enricher = old_enricher

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
                # 自动优化开关（Dashboard 优先，其次 env）
                if "enableAutoOptimization" in cfg:
                    await self._sync_auto_optimization(cfg["enableAutoOptimization"])
                logger.info(f"Loaded trading config: enabled={self._trading_enabled}, interval={interval_minutes}m")
        except Exception as e:
            logger.error(f"Failed to load trading config: {e}")

    async def _sync_auto_optimization(self, enabled: bool) -> None:
        """动态启用/停用自动优化系统"""
        was_enabled = self._optimization_orchestrator is not None

        if enabled and not was_enabled and self._persistence_initialized:
            # 启用：初始化 Orchestrator
            try:
                redis_url = config.redis_url if hasattr(config, "redis_url") else "redis://redis:6379"
                if not self.reflection_client:
                    self.reflection_client = ReflectionClient(redis_url)
                    await self.reflection_client.connect()
                if not self.shadow_runner:
                    self.shadow_runner = ShadowRunner(self.db_manager)
                if not self.memory_collector:
                    self.memory_collector = TradeMemoryCollector(self.db_manager)
                self._optimization_orchestrator = OptimizationOrchestrator(
                    db=self.db_manager,
                    shadow_runner=self.shadow_runner,
                    parameter_registry=self.parameter_registry,
                    redis_client=self._redis,
                )
                config.enable_auto_optimization = True
                logger.info("Auto optimization enabled via Dashboard")
            except Exception as e:
                logger.error(f"Failed to enable auto optimization: {e}")
        elif not enabled and was_enabled:
            # 停用：清除 Orchestrator（保留子组件以便再次启用）
            self._optimization_orchestrator = None
            config.enable_auto_optimization = False
            logger.info("Auto optimization disabled via Dashboard")

    async def _load_llm_providers_config(self):
        """从 Redis 加载 LLM provider 优先级配置"""
        if not self._redis:
            return

        try:
            data = await self._redis.get("llm:providers:config")
            if data:
                cfg = json.loads(data)
                # Dashboard 写入的格式:
                # { "providers": {name: {api_key, base_url, ...}},  -- pool map
                #   "routing": [{provider, model, priority}, ...],  -- 路由列表
                #   "strategy": "priority" }
                routing = cfg.get("routing", [])
                providers_pool = cfg.get("providers", {})
                strategy = cfg.get("strategy")

                # 兼容旧格式: providers 是列表而非 dict 时当作 routing
                if isinstance(providers_pool, list):
                    routing = providers_pool
                    providers_pool = {}

                if routing:
                    from .ai.llm_manager import get_llm_manager
                    manager = get_llm_manager()
                    manager.update_providers(routing, providers_pool=providers_pool, strategy=strategy)
                    logger.info(f"Loaded LLM providers config: {[p.get('provider') or p.get('name') for p in routing]}")
        except Exception as e:
            logger.error(f"Failed to load LLM providers config: {e}")

    async def _config_listener(self):
        """监听配置更新"""
        if not self._redis:
            return

        try:
            pubsub = self._redis.pubsub()
            await pubsub.subscribe("trading:config:updated", "strategy:preset:updated", "llm:providers:updated", "advisory:config:updated", "advisory:llm_config:updated", "advisory:auto_execute:updated", "llm:config:updated", "notification:config:updated", "notification:test", "trading:event_trigger_config:updated")

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
                                # 旧格式事件只有 [{name, model}]，从 Redis 补全 pool 信息
                                providers_pool = {}
                                if self._redis:
                                    try:
                                        pool_data = await self._redis.get("llm:providers:pool")
                                        if pool_data:
                                            providers_pool = json.loads(pool_data)
                                    except Exception:
                                        pass
                                manager.update_providers(providers, providers_pool=providers_pool)
                                logger.info(f"LLM providers updated: {[p.get('name') for p in providers]}")
                        elif channel == "advisory:config:updated":
                            cfg = json.loads(message["data"])
                            if self._advisory_service:
                                new_trigger_cfg = TriggerConfig(**cfg)
                                self._advisory_service.trigger_mgr.update_config(new_trigger_cfg)
                                logger.info(f"Advisory trigger config updated: {cfg}")
                        elif channel == "advisory:auto_execute:updated":
                            val = json.loads(message["data"])
                            self._advisory_auto_execute = bool(val)
                            config.advisory_auto_execute = self._advisory_auto_execute
                            logger.info(f"Advisory auto-execute updated: {self._advisory_auto_execute}")
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
                                    timeout=llm_cfg.get("timeout", 180.0),
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
                        elif channel == "trading:event_trigger_config:updated":
                            try:
                                raw = await self._redis.get("trading:event_trigger_config")
                                if raw:
                                    self._event_trigger_config = json.loads(raw)
                                    self._scan_interval = self._event_trigger_config.get("scan_interval_seconds", 30)
                                    for sym, det in self._event_detectors.items():
                                        det.update_config(
                                            self._event_trigger_config, config.enabled_strategies
                                        )
                                    logger.info("Event trigger config updated from Redis")
                            except Exception as e:
                                logger.error(f"Failed to update event trigger config: {e}")
                        else:
                            cfg = json.loads(message["data"])
                            # optimization 模块发布的参数变更事件，不含交易配置字段，跳过
                            if cfg.get("source") == "optimization":
                                logger.info(f"Optimization config update received: {list(cfg.get('changes', {}).keys())}")
                                continue
                            self._trading_enabled = cfg.get("enabled", True)
                            interval_minutes = cfg.get("decisionInterval", 1)
                            self._decision_interval = interval_minutes * 60
                            # 自动优化开关动态切换
                            if "enableAutoOptimization" in cfg:
                                await self._sync_auto_optimization(cfg["enableAutoOptimization"])
                            # 同步交易对配置变更和运行时参数（加锁保证原子性）
                            async with self._config_lock:
                                if "trading_symbols" in cfg:
                                    config.trading_symbols = cfg["trading_symbols"]
                                    logger.info(f"Trading symbols updated: {config.symbols_list}")
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

    async def _reflection_results_listener(self):
        """监听复盘结果队列，驱动 优化编排器"""
        if not self._redis or not self._optimization_orchestrator:
            return

        logger.info("Reflection results listener started")
        try:
            while self.running:
                result = await self._redis.brpop("reflection:results", timeout=5)
                if result is None:
                    continue
                _, data = result
                try:
                    reflection_result = json.loads(data)
                    started = await self._optimization_orchestrator.handle_reflection_result(
                        reflection_result
                    )
                    if started:
                        logger.info("从复盘结果启动了影子运行")
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse reflection result: {e}")
                except Exception as e:
                    logger.error(f"Reflection result handling error: {e}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Reflection results listener error: {e}")

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
                    # 保存交易记录和权益曲线到数据库
                    await self._save_backtest_details(backtest_id, symbol, engine, df)
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

    async def _save_backtest_details(self, backtest_id, symbol, engine, df):
        """保存回测交易记录和权益曲线到数据库"""
        import pandas as pd
        if not self.persistence_service:
            return
        # 保存交易记录
        for bt_t in engine.trades:
            try:
                _pp = None
                if bt_t.pnl and bt_t.entry_price and bt_t.size:
                    _pp = bt_t.pnl / (bt_t.entry_price * bt_t.size) * 100
                await self.persistence_service.save_backtest_trade(
                    backtest_id=backtest_id, symbol=symbol,
                    side=bt_t.side, entry_time=bt_t.timestamp,
                    entry_price=bt_t.entry_price,
                    exit_time=bt_t.timestamp if bt_t.exit_price else None,
                    exit_price=bt_t.exit_price,
                    pnl=bt_t.pnl, pnl_percent=_pp,
                )
            except Exception as e:
                logger.error(f"Save backtest trade error: {e}")
        # 保存权益曲线（采样最多500点）
        eq = engine.equity_curve
        step = max(1, len(eq) // 500)
        for i in range(0, len(eq), step):
            try:
                ts = df.index[min(i, len(df) - 1)] if i < len(df) else df.index[-1]
                if isinstance(ts, pd.Timestamp):
                    ts = ts.to_pydatetime()
                await self.persistence_service.save_backtest_equity(
                    backtest_id=backtest_id, timestamp=ts, total_equity=eq[i],
                )
            except Exception as e:
                logger.error(f"Save equity point error: {e}")
        logger.info(f"Backtest details saved: {len(engine.trades)} trades, {len(eq)} equity points")

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

        # Start reflection results listener for optimization loop
        if self._optimization_orchestrator and self._redis:
            asyncio.create_task(self._reflection_results_listener())

        while self.running:
            # ── Daily PnL reset ──
            today_str = _dt.utcnow().strftime("%Y-%m-%d")
            if today_str != self._daily_pnl_date:
                # 如果昨天没有触发 halt，重置连续天数
                if not self._trading_halted:
                    self._halt_consecutive_days = 0
                self._daily_pnl = {}
                self._daily_pnl_date = today_str
                self._trading_halted = False
                self._trades_today = 0
                self._trades_today_date = today_str
                logger.info(f"新交易日: {today_str}, 每日盈亏统计已重置")

            # ── 每小时更新策略权重 ──
            current_hour = _dt.utcnow().strftime("%Y-%m-%d %H")
            if current_hour != self._last_weight_update:
                self._last_weight_update = current_hour
                await self._update_strategy_weights()

            # Check if trading is enabled
            if not self._trading_enabled:
                logger.debug("Trading paused, waiting...")
                await asyncio.sleep(5)
                continue

            try:
                # Run cycle for each symbol (re-read from config for hot-reload)
                for symbol in config.symbols_list:
                    try:
                        trigger_events = []

                        # Event detection (per-symbol EventDetector)
                        event_detector = self._event_detectors.get(symbol)
                        if event_detector and self._event_trigger_config.get("enabled", True):
                            try:
                                md = await self.market_mgr.get_market_data(
                                    symbol, interval=f"{config.analysis_interval}m"
                                )
                                if md:
                                    # Get market state for MarketStateChangeDetector
                                    market_state_str = None
                                    if self.decision_engine.market_classifier:
                                        klines_data = [k.model_dump() for k in md.klines]
                                        df = pd.DataFrame(klines_data)
                                        mc = self.decision_engine.market_classifier.classify(df)
                                        market_state_str = mc.state.value

                                    # Get position for PositionPnLDetector
                                    position = None
                                    if config.trading_mode == "testnet":
                                        if hasattr(self, '_testnet_positions') and symbol in self._testnet_positions:
                                            position = self._testnet_positions[symbol]
                                    else:
                                        position = await self.position_mgr.get_position(symbol)

                                    trigger_events = event_detector.scan(
                                        symbol, md, position, market_state=market_state_str
                                    )
                            except Exception as e:
                                logger.warning(f"Event detection failed for {symbol}: {e}")

                        now = _time.monotonic()
                        should_run_llm = False
                        trigger_context = None

                        # Case 1: Events triggered
                        if trigger_events:
                            should_run_llm = True
                            trigger_context = trigger_events
                            logger.info(f"Event-driven LLM trigger for {symbol}: {[e.event_type for e in trigger_events]}")
                            # 异步持久化事件到数据库
                            if self.db_manager:
                                from .events.detector import persist_trigger_events
                                await persist_trigger_events(self.db_manager, symbol, trigger_events)

                        # Case 2: Per-symbol decision timer expired
                        symbol_timer = self._decision_timers.get(symbol, 0.0)
                        if not should_run_llm and (now - symbol_timer) >= self._decision_interval:
                            should_run_llm = True

                        if should_run_llm:
                            await self.run_cycle_for_symbol(symbol, trigger_context=trigger_context)
                            self._decision_timers[symbol] = _time.monotonic()

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

            logger.info(f"Waiting {self._scan_interval}s...")
            await asyncio.sleep(self._scan_interval)

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

                    # 累加每日盈亏（用于 daily loss limit 断路器）
                    self._daily_pnl[symbol] = self._daily_pnl.get(symbol, 0) + pnl

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

                    # 影子运行记录（如有进行中的影子验证）
                    # NOTE: 当前候选参数使用相同实盘结果作为近似（无独立模拟引擎）
                    # 完整的候选参数模拟需要 Phase 3 策略权重优化器支持
                    if self.shadow_runner and self.shadow_runner.is_running:
                        is_win = pnl > 0
                        self.shadow_runner.record_current_result(is_win, pnl)
                        self.shadow_runner.record_candidate_result(is_win, pnl)
                        # 评估是否达到切换条件
                        if self._optimization_orchestrator:
                            await self._optimization_orchestrator.evaluate_and_apply()

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

                    # 累加每日盈亏（用于 daily loss limit 断路器）
                    self._daily_pnl[symbol] = self._daily_pnl.get(symbol, 0) + pnl

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
        from .advisory.executors import ConfigExecutor, TradeExecutor, SymbolExecutor, StrategyExecutor, ExecutionResult

        suggestion_id = task.get("suggestion_id")
        suggestion_type = task.get("type")
        target = task.get("target", "")
        action = task.get("action", "")
        detail = task.get("detail", {})

        try:
            # 冲突检测：position_action 类型在执行前检查与主循环决策的冲突
            if suggestion_type == "position_action" and self._advisory_service:
                conflict = await self._advisory_service.check_decision_conflict(
                    {"action": action}, target
                )
                if conflict:
                    logger.info(f"Advisory suggestion skipped due to conflict: {target} {action}")
                    if self.persistence_service:
                        try:
                            await self.persistence_service.update_suggestion_status(
                                suggestion_id, "skipped", "与主循环决策冲突，冷却期内跳过"
                            )
                        except Exception:
                            pass
                    return

            if suggestion_type == "param_adjust":
                # 中低紧急度 + Orchestrator 可用 → 转发到影子验证
                urgency = detail.get("urgency", "medium")
                routed_to_shadow = False

                if urgency != "high" and self._optimization_orchestrator:
                    tmp_executor = ConfigExecutor(self._redis)
                    tmp_executor._unwrap_nested_values(detail)
                    param_name = tmp_executor._detect_param_from_detail(detail)
                    if not param_name:
                        param_name = tmp_executor._detect_param_from_target(target)
                    if param_name:
                        value = detail.get(param_name) or tmp_executor._extract_value(detail)
                        if value is not None and isinstance(value, (int, float)):
                            routed_to_shadow = await self._optimization_orchestrator.handle_advisory_suggestion(
                                param_name, float(value), reason=f"advisory:{action}"
                            )
                            if routed_to_shadow:
                                result = ExecutionResult(
                                    success=True,
                                    message=f"{param_name}={value} 已提交影子验证，验证通过后自动应用",
                                )

                if not routed_to_shadow:
                    executor = ConfigExecutor(self._redis)
                    result = await executor.execute(action, target, detail)
            elif suggestion_type == "position_action":
                if not self.position_mgr:
                    result = ExecutionResult(success=False, message="Position manager not initialized")
                else:
                    # 使用 symbol 锁防止与主交易循环并发操作同一 symbol
                    async with self._get_symbol_lock(target):
                        executor = TradeExecutor(self.order_mgr, self.position_mgr, exchange=self.exchange)
                        # 执行前获取仓位信息用于持久化
                        pre_position = await self.position_mgr.get_position(target)
                        result = await executor.execute(action, target, detail)
                        # 开仓操作的持久化
                        if result.success and not pre_position and self.persistence_service and result.detail and result.detail.get("side"):
                            try:
                                open_side = result.detail["side"]
                                open_price = result.detail.get("price", 0)
                                open_size = result.detail.get("quantity", 0)
                                open_leverage = result.detail.get("leverage", 1)
                                await self._persist_position_change(
                                    action=f"open_{open_side}",
                                    symbol=target,
                                    price=open_price,
                                    size=open_size,
                                    leverage=open_leverage,
                                    position=None,
                                    market_state="advisory",
                                )
                            except Exception as persist_err:
                                logger.error(f"Advisory open position persist failed: {persist_err}")
                        # 平仓/减仓操作的持久化
                        if result.success and pre_position and self.persistence_service:
                            try:
                                persist_action = action
                                # 判断是平仓还是减仓类操作
                                close_actions = {"close_position", "close"}
                                reduce_actions = {"reduce_position", "reduce", "take_profit_partial_and_move_stop", "partial_take_profit"}
                                # tighten_stop_or_exit_if_breaks_level: 高紧急度平仓，否则减仓
                                if action in ("tighten_stop_or_exit_if_breaks_level", "tighten_stop", "exit_if_breaks"):
                                    if detail.get("urgency") == "high":
                                        close_actions.add(action)
                                    else:
                                        reduce_actions.add(action)
                                if action in close_actions:
                                    persist_action = f"close_{pre_position.side}"
                                elif action in reduce_actions:
                                    persist_action = f"reduce_{pre_position.side}"
                                ticker = await self.exchange.get_ticker(target) if hasattr(self, "exchange") and self.exchange else None
                                current_price = ticker.last_price if ticker else (pre_position.entry_price or 0)
                                persist_size = pre_position.size
                                if persist_action.startswith("reduce_"):
                                    raw_pct = detail.get("reduce_percent", 50) if isinstance(detail, dict) else 50
                                    # take_profit_partial_and_move_stop 从 targets.take_profit 提取
                                    if action in ("take_profit_partial_and_move_stop", "partial_take_profit") and isinstance(detail, dict):
                                        targets = detail.get("targets", {})
                                        tp_list = targets.get("take_profit", []) if isinstance(targets, dict) else []
                                        if isinstance(tp_list, list):
                                            for tp in tp_list:
                                                if isinstance(tp, dict) and (tp.get("size_percent") or tp.get("reduce_percent")):
                                                    raw_pct = tp.get("size_percent") or tp.get("reduce_percent")
                                                    break
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
            elif suggestion_type == "strategy_change":
                if not self._strategy_preset_service:
                    result = ExecutionResult(success=False, message="Strategy service not initialized")
                else:
                    executor = StrategyExecutor(self._strategy_preset_service, self._redis)
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

    async def _strategy_suggest_listener(self):
        """Listen for strategy suggestion requests via Redis list (BLPOP)"""
        if not self._redis or not self._advisory_service:
            return
        try:
            # Set heartbeat flag so dashboard knows consumer is online
            await self._redis.set("strategy:suggest:consumer_alive", "1", ex=30)
            logger.info("Strategy suggest listener started (BLPOP queue)")
            while True:
                try:
                    # Refresh heartbeat every BLPOP cycle
                    await self._redis.set("strategy:suggest:consumer_alive", "1", ex=30)
                    result = await self._redis.blpop("strategy:suggest_queue", timeout=5)
                    if result is None:
                        continue
                    _, raw = result
                    data = json.loads(raw)
                    task_id = data.get("task_id", "")
                    if task_id:
                        task = asyncio.create_task(self._run_strategy_suggest(task_id))
                        self._advisory_tasks.append(task)
                        self._advisory_tasks = [t for t in self._advisory_tasks if not t.done()]
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(f"Strategy suggest listener error: {e}")
                    await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Strategy suggest listener error: {e}")
        finally:
            # Clear heartbeat on exit
            try:
                if self._redis:
                    await self._redis.delete("strategy:suggest:consumer_alive")
            except Exception:
                pass

    async def _collect_advisory_data(self) -> dict:
        """Collect market data, positions, config, and account info for advisory/suggestion use."""
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

                pos = (
                    await self._load_testnet_virtual_position(symbol, current_price)
                    if is_testnet
                    else await self.position_mgr.get_position(symbol)
                )
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

        # Inject strategy preset info
        if self._strategy_preset_service:
            try:
                active_preset = await self._strategy_preset_service.get_active_preset()
                all_presets = await self._strategy_preset_service.get_all_presets()
                current_config["_strategy_preset_info"] = {
                    "active_preset": {
                        "name": active_preset["name"],
                        "display_name": active_preset["display_name"],
                        "description": active_preset.get("description", ""),
                        "risk_level": active_preset.get("risk_level", ""),
                    } if active_preset else None,
                    "all_presets": [
                        {
                            "name": p["name"],
                            "display_name": p["display_name"],
                            "description": p.get("description", ""),
                            "risk_level": p.get("risk_level", ""),
                            "category": p.get("category", ""),
                        }
                        for p in all_presets
                    ],
                }
            except Exception as e:
                logger.debug(f"Failed to collect strategy preset info: {e}")

        # Inject market classifications
        try:
            from .strategies.market_classifier import MarketClassifier
            classifier = MarketClassifier()
            market_classifications = {}
            for symbol in symbols:
                try:
                    klines = await self.exchange.get_klines(symbol, interval="1h", limit=100)
                    if klines:
                        import pandas as pd
                        df = pd.DataFrame([k.model_dump() for k in klines])
                        cls_result = classifier.classify(df)
                        market_classifications[symbol] = {
                            "state": cls_result.state.value,
                            "confidence": cls_result.confidence,
                            "adx_value": cls_result.adx_value,
                            "volatility": cls_result.volatility,
                            "trend_direction": cls_result.trend_direction,
                        }
                except Exception as e:
                    logger.debug(f"Failed to classify market for {symbol}: {e}")
            if market_classifications:
                current_config["_market_classifications"] = market_classifications
        except Exception as e:
            logger.debug(f"Failed to collect market classifications: {e}")

        # Account summary
        account_summary = None
        try:
            if is_testnet:
                total_margin = sum(
                    (p.get("entry_price", 0) * p.get("size", 0)) / (p.get("leverage", 1) or 1)
                    for p in positions
                )
                total_upnl = sum(p.get("unrealized_pnl", 0) or 0 for p in positions)
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

        return {
            "symbols": symbols,
            "positions": positions,
            "market_data": market_data,
            "price_context": price_context,
            "current_config": current_config,
            "account_summary": account_summary,
        }

    async def _run_strategy_suggest(self, task_id: str):
        """Run strategy suggestion and store result in Redis"""
        if not self._redis or not self._advisory_service:
            return
        result_key = f"strategy:suggest:result:{task_id}"
        try:
            ctx = await self._collect_advisory_data()
            result = await self._advisory_service.engine.suggest_strategy(
                symbols=ctx["symbols"],
                positions=ctx["positions"],
                market_data=ctx["market_data"],
                sentiment=None,
                current_config=ctx["current_config"],
                account_summary=ctx["account_summary"],
            )
            result["status"] = "completed"
            await self._redis.set(result_key, json.dumps(result, ensure_ascii=False), ex=300)
            logger.info(f"Strategy suggestion completed: task_id={task_id}, preset={result.get('recommended_preset')}")
        except Exception as e:
            logger.error(f"Strategy suggestion failed: {e}")
            error_result = {"status": "error", "error": str(e)}
            await self._redis.set(result_key, json.dumps(error_result, ensure_ascii=False), ex=300)

    async def _update_strategy_weights(self):
        """定期更新策略权重（基于历史表现）"""
        if not self._weight_optimizer or not self.decision_engine.strategy_selector:
            return
        try:
            updated = await self._weight_optimizer.update_strategy_selector(
                self.decision_engine.strategy_selector
            )
            if updated > 0:
                logger.info(f"策略权重已更新: {updated} 个市场状态")
            else:
                logger.debug("权重优化: 样本不足或无更新")
        except Exception as e:
            logger.error(f"Strategy weight update failed: {e}")

    async def _run_advisory_check(self, force: bool = False):
        """运行 advisory 检查"""
        if not self._advisory_service:
            return
        try:
            ctx = await self._collect_advisory_data()
            symbols = ctx["symbols"]
            positions = ctx["positions"]
            market_data = ctx["market_data"]
            price_context = ctx["price_context"]
            current_config = ctx["current_config"]
            account_summary = ctx["account_summary"]

            # Update price history for volatility trigger
            for symbol in symbols:
                if symbol in market_data:
                    self._price_history[symbol] = market_data[symbol].get("current_price", 0)

            if force:
                advisory_id = await self._advisory_service.force_run(
                    symbols=symbols, positions=positions,
                    market_data=market_data, sentiment=None,
                    current_config=current_config,
                    account_summary=account_summary,
                )
            else:
                advisory_id = await self._advisory_service.check_and_run(
                    symbols=symbols, positions=positions,
                    market_data=market_data, sentiment=None,
                    current_config=current_config,
                    consecutive_losses=self._consecutive_losses,
                    price_context=price_context,
                    account_summary=account_summary,
                )

            # 自动执行：跳过手动确认，直接入队执行
            if advisory_id and self._advisory_auto_execute:
                await self._auto_execute_advisory(advisory_id)
        except Exception as e:
            logger.error(f"Advisory check error: {e}")

    async def _auto_execute_advisory(self, advisory_id: str):
        """自动执行 advisory 的所有 pending suggestions，跳过手动确认"""
        if not self._advisory_service or not self._advisory_service.persistence or not self._redis:
            return
        try:
            from uuid import UUID
            aid = UUID(advisory_id)
            rows = await self.db_manager.pool.fetch(
                """
                SELECT id, type, target, action, detail, status
                FROM advisory_suggestions
                WHERE advisory_id = $1 AND status = 'pending'
                ORDER BY sort_order
                """,
                aid,
            )
            if not rows:
                return

            for row in rows:
                sid = row["id"]
                # 原子更新：pending → confirmed
                updated = await self._advisory_service.persistence.update_suggestion_status_if(
                    sid, "confirmed", "pending"
                )
                if not updated:
                    continue
                detail = row["detail"]
                if isinstance(detail, str):
                    detail = json.loads(detail)
                task = {
                    "suggestion_id": str(sid),
                    "type": row["type"],
                    "target": row["target"],
                    "action": row["action"],
                    "detail": detail,
                }
                await self._redis.lpush("advisory:execute_tasks", json.dumps(task))

            logger.info(f"Advisory {advisory_id} auto-executed: {len(rows)} suggestions queued")
        except Exception as e:
            logger.error(f"Advisory auto-execute failed: {e}")

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
        """构建 testnet 虚拟账户状态（汇总所有交易对仓位）。"""
        from .exchange.base import AccountInfo

        position = await self._load_testnet_virtual_position(symbol, current_price)
        base_equity = config.testnet_initial_equity

        # 汇总所有 open 仓位的保证金和未实现盈亏
        total_margin = 0.0
        total_unrealized_pnl = 0.0

        if self.db_manager:
            try:
                all_positions = await self.db_manager.fetch(
                    "SELECT symbol, side, entry_price, entry_size, "
                    "COALESCE(leverage, 1) AS leverage "
                    "FROM position_history WHERE status='open' AND entry_size > 0"
                )
                for row in all_positions:
                    pos_symbol = row["symbol"]
                    entry_price = float(row["entry_price"])
                    size = float(row["entry_size"])
                    leverage = max(1, int(float(row["leverage"])))
                    side = str(row["side"]).lower()

                    if pos_symbol == symbol:
                        mark_price = current_price
                    else:
                        try:
                            ticker = await self.exchange.get_ticker(pos_symbol)
                            mark_price = ticker.last_price
                        except Exception:
                            mark_price = entry_price

                    if side == "long":
                        unrealized = (mark_price - entry_price) * size
                    else:
                        unrealized = (entry_price - mark_price) * size

                    margin = (entry_price * size) / leverage if leverage > 0 else 0.0
                    total_margin += margin
                    total_unrealized_pnl += unrealized
            except Exception as e:
                logger.warning(f"Failed to aggregate testnet positions: {e}")
                total_margin = position.margin if position else 0.0
                total_unrealized_pnl = position.unrealized_pnl if position else 0.0
        else:
            total_margin = position.margin if position else 0.0
            total_unrealized_pnl = position.unrealized_pnl if position else 0.0

        realized_pnl = await self._get_total_realized_pnl()
        total_equity = base_equity + realized_pnl + total_unrealized_pnl
        available_balance = max(total_equity - total_margin, 0.0)

        account = AccountInfo(
            total_equity=total_equity,
            available_balance=available_balance,
            margin_used=total_margin,
            unrealized_pnl=total_unrealized_pnl,
        )
        return account, position

    async def _get_total_realized_pnl(self) -> float:
        """获取 testnet 所有已实现盈亏总和"""
        if not self.db_manager:
            return 0.0
        try:
            row = await self.db_manager.fetchrow(
                "SELECT COALESCE(SUM(realized_pnl), 0) AS total "
                "FROM position_history WHERE status='closed' AND realized_pnl IS NOT NULL"
            )
            return float(row["total"]) if row else 0.0
        except Exception as e:
            logger.warning(f"Failed to get total realized PnL: {e}")
            return 0.0

    async def run_cycle_for_symbol(self, symbol: str, trigger_context: list | None = None):
        """执行指定 symbol 的交易循环"""
        async with self._get_symbol_lock(symbol):
            await self._run_cycle_for_symbol_impl(symbol, trigger_context=trigger_context)

    async def _run_cycle_for_symbol_impl(self, symbol: str, trigger_context: list | None = None):
        """执行指定 symbol 的交易循环（内部实现，已持有 symbol 锁）"""
        logger.info(f"Starting cycle for {symbol}")

        # ── 配置快照（防止决策过程中配置被并发修改）──
        async with self._config_lock:
            _cfg = {
                "analysis_interval": config.analysis_interval,
                "stop_loss_percent": config.stop_loss_percent,
                "take_profit_percent": config.take_profit_percent,
                "leverage_max": config.leverage_max,
                "leverage_min": config.leverage_min,
                "default_leverage": config.default_leverage,
                "ai_weight": config.ai_weight,
                "quant_weight": config.quant_weight,
                "daily_loss_limit_percent": config.daily_loss_limit_percent,
                "signal_min_interval_hours": config.signal_min_interval_hours,
                "signal_reverse_cooldown_hours": config.signal_reverse_cooldown_hours,
                "min_confidence_to_trade": config.min_confidence_to_trade,
                "min_confluence_to_trade": config.min_confluence_to_trade,
            }

        # 1. 获取数据
        market_data = await self.market_mgr.get_market_data(
            symbol, interval=f"{config.analysis_interval}m"
        )
        if not market_data:
            return

        # 1.1 获取多时间框架数据（失败时降级为单时间框架）
        mtf_data = None
        try:
            mtf_data = await self.mtf_manager.get_multi_timeframe_data(symbol)
            if mtf_data:
                logger.info(
                    f"MTF [{symbol}]: trend={mtf_data.overall_trend.value}, "
                    f"confluence={mtf_data.confluence_score:.2f}, "
                    f"action={mtf_data.recommended_action}"
                )
        except Exception as e:
            logger.warning(f"MTF analysis failed for {symbol}, continuing without: {e}")

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

        # 尽早发布账户状态到 Redis，确保 Dashboard 能显示权益（即使后续流程 return）
        await self._publish_account_state(symbol, account, position, market_data.current_price)

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

        # ── 每日亏损限制检查（在 LLM 决策之前）──
        if self._halt_until:
            if _dt.utcnow().strftime("%Y-%m-%d") < self._halt_until:
                logger.warning(f"强制休息中，截止: {self._halt_until}")
                return
            else:
                self._trading_halted = False
                self._halt_until = None
                self._halt_consecutive_days = 0
                logger.info("强制休息期结束，连续触发天数已重置")

        if self._trading_halted:
            # 有持仓时仍允许进入决策（后续只执行平仓）
            if not (position and position.size > 0):
                logger.warning("每日亏损限制已触发，跳过本轮决策")
                return

        daily_pnl_total = sum(self._daily_pnl.values())
        max_daily_loss = equity * (_cfg["daily_loss_limit_percent"] / 100)
        if daily_pnl_total < 0 and abs(daily_pnl_total) >= max_daily_loss:
            self._trading_halted = True
            halt_reason = (
                f"当日亏损 {daily_pnl_total:.2f} USDT 超出限额 "
                f"{max_daily_loss:.2f} USDT ({_cfg['daily_loss_limit_percent']}%)"
            )
            logger.warning(f"每日亏损限制触发: {halt_reason}")

            # 检查连续触发天数 — 如果 _daily_pnl_date 的前 N-1 天也触发了，则强制休息
            # 简单实现：利用已有的 _halt_consecutive_days 计数
            self._halt_consecutive_days += 1
            if self._halt_consecutive_days >= config.consecutive_halt_days_for_break:
                break_end = _dt.utcnow() + _td(days=config.forced_break_days)
                self._halt_until = break_end.strftime("%Y-%m-%d")
                logger.warning(
                    f"连续 {self._halt_consecutive_days} 天触发亏损限制，"
                    f"强制休息至 {self._halt_until}"
                )
                halt_reason += f"\n连续触发 {self._halt_consecutive_days} 天，强制休息至 {self._halt_until}"

            if self._notification_manager:
                await self._notification_manager.notify_alert(
                    f"⚠️ 每日亏损限制触发\n{halt_reason}"
                )
            return  # 跳过本轮决策

        # 2. 决策（含多时间框架数据 + 真实纪律上下文）
        total_daily_pnl = sum(self._daily_pnl.values())
        try:
            decision, tech, risk = await self.decision_engine.analyze_and_decide(
                market_data, position, balance, equity,
                mtf_data=mtf_data,
                daily_pnl=total_daily_pnl,
                trades_today=self._trades_today,
                consecutive_losses=self._consecutive_losses,
                emotional_state=self._get_emotional_state(),
                trigger_context=trigger_context,
            )
        except Exception as e:
            logger.error(f"Decision engine failed: {e}")
            return

        # ── 3. All rule-based filters (unified before notification) ──
        original_action = decision.action

        # 3a. Confidence filter
        if decision.action in ("open_long", "open_short"):
            min_conf = _cfg.get("min_confidence_to_trade", 60.0)
            if decision.confidence < min_conf:
                logger.info(f"Confidence filter: {decision.action} -> hold (conf={decision.confidence}<{min_conf})")
                decision.action = "hold"
                decision.reasoning += f" [FILTERED: low confidence {decision.confidence}]"

        # 3b. Confluence filter
        if decision.action in ("open_long", "open_short"):
            min_confl = _cfg.get("min_confluence_to_trade", 0.5)
            if mtf_data and mtf_data.confluence_score < min_confl:
                logger.info(f"Confluence filter: {decision.action} -> hold (confl={mtf_data.confluence_score:.2f}<{min_confl})")
                decision.action = "hold"
                decision.reasoning += f" [FILTERED: low confluence {mtf_data.confluence_score:.2f}]"

        # 3c. Daily loss limit halt
        if self._trading_halted and decision.action in ("open_long", "open_short"):
            logger.info(f"Daily loss limit: {decision.action} -> hold")
            decision.action = "hold"
            decision.reasoning += "\n[DailyLossLimit] 当日亏损限制已触发，禁止开新仓"

        # 3d. SignalFilter (anti-overtrading)
        if decision.action in ("open_long", "open_short"):
            if symbol not in self._signal_filters:
                self._signal_filters[symbol] = SignalFilter(
                    min_interval_hours=_cfg["signal_min_interval_hours"],
                    reverse_cooldown_hours=_cfg["signal_reverse_cooldown_hours"],
                )
            sf = self._signal_filters[symbol]
            action_map = {"open_long": SignalAction.LONG, "open_short": SignalAction.SHORT}
            allowed, filter_reason = sf.should_allow_signal(
                action_map[decision.action], _dt.utcnow()
            )
            if not allowed:
                logger.info(f"[SignalFilter] {symbol} {decision.action} -> hold: {filter_reason}")
                decision.action = "hold"
                decision.reasoning += f"\n[SignalFilter] {filter_reason}"

        # 3e. Log filter result and sync reasoning_zh
        if decision.action != original_action:
            logger.info(f"Action changed: {original_action} -> {decision.action}")
            # Ensure filter annotations are visible in reasoning_zh for notifications
            if decision.reasoning_zh:
                decision.reasoning_zh += f"\n[{original_action} -> hold]"

        # ── 4. Send notification (action is finalized) ──
        if self._notification_manager:
            await self._notification_manager.notify_decision(
                symbol=symbol,
                action=decision.action,
                confidence=decision.confidence,
                reasoning=decision.reasoning_zh or decision.reasoning,
            )

        # 5. 执行
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

                    # Trade counter for discipline context
                    if order_id:
                        self._trades_today += 1

                    # 更新 SignalFilter 状态（开仓成功后记录）
                    if order_id and decision.action in ("open_long", "open_short") and symbol in self._signal_filters:
                        action_map = {"open_long": SignalAction.LONG, "open_short": SignalAction.SHORT}
                        self._signal_filters[symbol].record_trade(
                            action_map[decision.action], _dt.utcnow()
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
