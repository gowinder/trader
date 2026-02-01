"""回测调度运行器

独立进程，从数据库读取配置并执行定时回测任务。
"""

import asyncio
import os
from datetime import datetime, timedelta
from typing import Optional

from ..backtest.engine import BacktestEngine, BacktestConfig
from ..strategies.market_classifier import MarketClassifier
from ..strategies.strategy_selector import StrategySelector
from ..strategies.signal_filter import SignalFilter
from ..persistence.database import DatabaseManager
from ..persistence.service import DecisionPersistenceService
from ..data.fetcher import CachedDataFetcher
from ..config import config
from ..utils.logger import logger


class BacktestRunner:
    """回测调度运行器"""

    def __init__(self):
        self.db_url = os.environ.get("DASHBOARD_DATABASE_URL", "")
        self.db: Optional[DatabaseManager] = None
        self.persistence: Optional[DecisionPersistenceService] = None
        self.running = False
        self.last_run_time: Optional[datetime] = None

    async def connect(self):
        """连接数据库"""
        if not self.db_url:
            raise ValueError("DASHBOARD_DATABASE_URL 未配置")
        self.db = DatabaseManager(self.db_url)
        await self.db.connect()
        self.persistence = DecisionPersistenceService(self.db)
        logger.info("回测运行器已连接数据库")

    async def close(self):
        """关闭连接"""
        if self.db:
            await self.db.close()
            logger.info("回测运行器已断开数据库")

    async def get_config(self) -> Optional[dict]:
        """从数据库获取回测配置"""
        row = await self.db.fetchrow(
            "SELECT * FROM backtest_schedule_config ORDER BY updated_at DESC LIMIT 1"
        )
        if not row:
            return None
        return dict(row)

    async def should_run(self, cfg: dict) -> bool:
        """判断是否应该运行回测"""
        if not cfg.get("enabled"):
            return False

        schedule_type = cfg.get("schedule_type", "manual")

        if schedule_type == "manual":
            # 手动模式：检查是否有待执行标记
            return cfg.get("pending_run", False)

        now = datetime.now()
        schedule_hour = cfg.get("schedule_hour", 0)

        if schedule_type == "daily":
            # 每日模式：检查是否到达执行时间且今天未执行
            if now.hour == schedule_hour:
                if self.last_run_time is None or self.last_run_time.date() < now.date():
                    return True

        elif schedule_type == "weekly":
            # 每周模式：检查是否到达执行日和时间
            schedule_day = cfg.get("schedule_day_of_week", 0)
            if now.weekday() == schedule_day and now.hour == schedule_hour:
                if self.last_run_time is None or (now - self.last_run_time).days >= 7:
                    return True

        return False

    async def run_backtest(self, cfg: dict) -> None:
        """执行单次回测"""
        symbols = cfg.get("symbols", ["BTCUSDT"])
        timeframe = cfg.get("timeframe", "1h")
        lookback_days = cfg.get("lookback_days", 30)
        initial_capital = float(cfg.get("initial_capital", 10000))
        enable_filters = cfg.get("enable_filters", True)

        end_date = datetime.now()
        start_date = end_date - timedelta(days=lookback_days)

        logger.info(f"开始回测: symbols={symbols}, range={start_date.date()} ~ {end_date.date()}")

        for symbol in symbols:
            try:
                await self._run_single_backtest(
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date,
                    timeframe=timeframe,
                    initial_capital=initial_capital,
                    enable_filters=enable_filters,
                )
            except Exception as e:
                logger.error(f"回测 {symbol} 失败: {e}")

        self.last_run_time = datetime.now()
        logger.info("回测完成")

    async def _run_single_backtest(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        timeframe: str,
        initial_capital: float,
        enable_filters: bool,
    ) -> None:
        """执行单个交易对的回测"""
        import pandas as pd

        # 获取历史数据
        fetcher = CachedDataFetcher(cache_dir="data/cache")
        symbol_formatted = f"{symbol[:-4]}/{symbol[-4:]}" if "/" not in symbol else symbol

        df = fetcher.get_data(
            symbol=symbol_formatted,
            start_date=start_date,
            end_date=end_date,
            timeframe=timeframe,
        )

        if len(df) < 50:
            logger.warning(f"{symbol} 数据不足，跳过")
            return

        # 生成信号
        signals = self._generate_signals(df, enable_filters)

        # 配置回测
        bt_config = BacktestConfig(
            initial_capital=initial_capital,
            commission_rate=0.0002,
            slippage_rate=0.001,
            max_position_size=0.5,
            enable_stop_loss=True,
            enable_take_profit=True,
        )

        # 执行回测
        engine = BacktestEngine(bt_config)
        result = engine.run(df, signals)

        # 保存到数据库
        backtest_id = await self.persistence.create_backtest(
            mode="single",
            symbol=symbol,
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d"),
            initial_capital=initial_capital,
        )

        # 保存交易记录
        for trade in engine.trades:
            await self.persistence.save_backtest_trade(
                backtest_id=backtest_id,
                symbol=symbol,
                side=trade.side,
                entry_time=trade.timestamp,
                entry_price=trade.entry_price,
                exit_time=trade.timestamp,
                exit_price=trade.exit_price,
                pnl=trade.pnl,
                pnl_percent=(trade.pnl / (trade.entry_price * trade.size) * 100)
                if trade.pnl and trade.entry_price and trade.size
                else None,
            )

        # 保存权益曲线
        step = max(1, len(engine.equity_curve) // 100)
        for i in range(0, len(engine.equity_curve), step):
            if i < len(df):
                ts = df.iloc[i]["timestamp"]
                if isinstance(ts, str):
                    ts = datetime.fromisoformat(ts)
                await self.persistence.save_backtest_equity(
                    backtest_id=backtest_id,
                    timestamp=ts,
                    total_equity=engine.equity_curve[i],
                )

        # 完成回测
        await self.persistence.complete_backtest(
            backtest_id=backtest_id,
            final_capital=result.final_capital,
            total_pnl=result.total_pnl,
            total_trades=result.total_trades,
            winning_trades=result.winning_trades,
            max_drawdown=result.max_drawdown,
            sharpe_ratio=result.sharpe_ratio,
        )

        logger.info(f"{symbol} 回测完成: PnL={result.total_pnl:.2f}, WinRate={result.win_rate:.1%}")

    def _generate_signals(self, df, enable_filters: bool):
        """生成交易信号"""
        import pandas as pd

        market_classifier = MarketClassifier()
        strategy_selector = StrategySelector(config.enabled_strategies)
        signal_filter = SignalFilter(min_interval_hours=6) if enable_filters else None

        signals = []

        for i in range(len(df)):
            window_df = df.iloc[max(0, i - 100) : i + 1]

            if len(window_df) < 50:
                signals.append({
                    "action": "hold",
                    "confidence": 0.0,
                    "entry_price": None,
                    "stop_loss": None,
                    "take_profit": None,
                })
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

            if enable_filters and action != "hold":
                current_time = df.iloc[i]["timestamp"]
                if signal.confidence < 0.55:
                    action = "hold"
                elif signal_filter:
                    allowed, _ = signal_filter.should_allow_signal(signal.action, current_time)
                    if not allowed:
                        action = "hold"
                    else:
                        signal_filter.record_trade(signal.action, current_time)

            signals.append({
                "action": action,
                "confidence": signal.confidence,
                "entry_price": signal.entry_price,
                "stop_loss": signal.stop_loss,
                "take_profit": signal.take_profit,
            })

        return pd.DataFrame(signals)

    async def run_loop(self, check_interval: int = 60):
        """主循环"""
        self.running = True
        logger.info(f"回测运行器启动，检查间隔: {check_interval}秒")

        while self.running:
            try:
                cfg = await self.get_config()
                if cfg and await self.should_run(cfg):
                    await self.run_backtest(cfg)
            except Exception as e:
                logger.error(f"回测运行器错误: {e}")

            await asyncio.sleep(check_interval)

    def stop(self):
        """停止运行"""
        self.running = False
        logger.info("回测运行器停止")


async def main():
    """入口函数"""
    runner = BacktestRunner()
    await runner.connect()

    try:
        await runner.run_loop(check_interval=60)
    finally:
        await runner.close()


if __name__ == "__main__":
    asyncio.run(main())
