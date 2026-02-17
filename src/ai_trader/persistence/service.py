"""决策持久化服务"""

import json
from typing import Optional
from datetime import datetime
from uuid import UUID

from .database import DatabaseManager
from ..models.decision import TradingDecision, TechnicalAnalysisResult, RiskAssessment
from ..models.market import MarketData
from ..sentiment.analyzer import SentimentResult
from ..utils.logger import logger


class DecisionPersistenceService:
    """决策数据持久化服务

    将交易决策及其相关分析数据写入 PostgreSQL 数据库，
    供 Dashboard 展示和分析使用。
    """

    def __init__(self, db: DatabaseManager):
        """初始化持久化服务

        Args:
            db: 数据库管理器实例
        """
        self.db = db

    async def save_decision(
        self,
        decision: TradingDecision,
        technical: TechnicalAnalysisResult,
        risk: RiskAssessment,
        market_data: MarketData,
        sentiment: Optional[SentimentResult] = None,
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None,
        llm_raw_output: Optional[str] = None,
        llm_tokens_used: Optional[int] = None,
        strategy_preset: Optional[str] = None,
        market_state: Optional[str] = None,
        strategy_signals: Optional[dict] = None,
    ) -> UUID:
        """保存完整决策数据

        Args:
            decision: 交易决策
            technical: 技术分析结果
            risk: 风险评估结果
            market_data: 市场数据
            sentiment: 情绪分析结果 (可选)
            llm_provider: LLM 提供商
            llm_model: LLM 模型名称
            llm_raw_output: LLM 原始输出
            llm_tokens_used: LLM token 使用量

        Returns:
            决策 ID (UUID)
        """
        async with self.db.transaction() as conn:
            # 1. 插入决策主记录
            decision_id = await conn.fetchval(
                """
                INSERT INTO decisions (
                    symbol, timeframe, action, confidence,
                    leverage, position_size_pct, entry_price,
                    stop_loss, take_profit, reasoning, reasoning_zh,
                    llm_provider, llm_model, llm_raw_output, llm_tokens_used,
                    strategy_preset, market_state, strategy_signals
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18
                ) RETURNING id
                """,
                market_data.symbol,
                market_data.interval,
                decision.action,
                int(decision.confidence),
                decision.leverage,
                decision.position_size_percent,
                decision.entry_price,
                decision.stop_loss_price,
                decision.take_profit_price,
                decision.reasoning,
                decision.reasoning_zh or None,
                llm_provider,
                llm_model,
                llm_raw_output,
                llm_tokens_used,
                strategy_preset,
                market_state,
                json.dumps(strategy_signals) if strategy_signals else None,
            )

            # 2. 插入技术分析快照
            await conn.execute(
                """
                INSERT INTO technical_snapshots (
                    decision_id, trend, trend_confidence, signal_strength,
                    price, rsi, macd, macd_signal, ma7, ma25, ma99, atr,
                    boll_upper, boll_lower, support_levels, resistance_levels,
                    volume_trend, pattern, key_observations
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19
                )
                """,
                decision_id,
                technical.trend,
                int(technical.trend_confidence),
                technical.signal_strength,
                market_data.current_price,
                market_data.indicators.rsi if market_data.indicators else None,
                market_data.indicators.macd if market_data.indicators else None,
                market_data.indicators.macd_signal if market_data.indicators else None,
                market_data.indicators.ma7 if market_data.indicators else None,
                market_data.indicators.ma25 if market_data.indicators else None,
                market_data.indicators.ma99 if market_data.indicators else None,
                market_data.indicators.atr if market_data.indicators else None,
                market_data.indicators.boll_upper if market_data.indicators else None,
                market_data.indicators.boll_lower if market_data.indicators else None,
                json.dumps(technical.support_levels),
                json.dumps(technical.resistance_levels),
                technical.volume_trend,
                technical.pattern,
                json.dumps(technical.key_observations),
            )

            # 3. 插入风险评估快照
            await conn.execute(
                """
                INSERT INTO risk_snapshots (
                    decision_id, risk_level, risk_score,
                    recommended_leverage, recommended_position_pct,
                    should_trade, risk_factors, mitigation_suggestions
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8
                )
                """,
                decision_id,
                risk.risk_level,
                int(risk.risk_score),
                risk.recommended_leverage,
                risk.recommended_position_percent,
                risk.should_trade,
                json.dumps(risk.risk_factors),
                json.dumps(risk.mitigation_suggestions),
            )

            # 4. 插入情绪分析快照 (如果有)
            if sentiment:
                await conn.execute(
                    """
                    INSERT INTO sentiment_snapshots (
                        decision_id, overall_score, news_count,
                        bullish_count, bearish_count, top_news, data_source
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7
                    )
                    """,
                    decision_id,
                    sentiment.get_numeric_score(),
                    sentiment.news_count,
                    0,  # bullish_count - 需要从 sentiment 计算
                    0,  # bearish_count - 需要从 sentiment 计算
                    json.dumps(
                        {
                            "score": sentiment.score.value,
                            "confidence": sentiment.confidence,
                            "reasoning": sentiment.reasoning,
                            "extreme_fear": sentiment.extreme_fear,
                            "extreme_greed": sentiment.extreme_greed,
                            "risk_event": sentiment.risk_event,
                            "divergence": sentiment.divergence,
                        }
                    ),
                    "mixed",  # data_source
                )

            # 5. 计算决策质量评分并写入 decisions 表
            quality = self._compute_decision_quality(decision, market_data)
            quality_score = quality.get("quality_score")
            if quality_score is not None:
                try:
                    await conn.execute(
                        "UPDATE decisions SET quality_score = $1 WHERE id = $2",
                        quality_score,
                        decision_id,
                    )
                except Exception as e:
                    logger.warning(f"Failed to update quality_score: {e}")

            logger.info(
                f"决策已保存: {decision_id}, action={decision.action}, "
                f"quality={quality_score}"
            )
            return decision_id

    def _compute_decision_quality(
        self, decision: TradingDecision, market_data: MarketData
    ) -> dict:
        """评估 LLM 输出质量

        检查价格偏差、止损距离、风险回报比等指标。

        Returns:
            quality_score (0-100) 和 issues 列表
        """
        # hold 动作不需要质量评分
        if decision.action == "hold":
            return {"quality_score": 100, "issues": []}

        issues = []

        # 检查价格合理性
        if decision.entry_price and decision.entry_price > 0 and market_data.current_price > 0:
            price_deviation = (
                abs(decision.entry_price - market_data.current_price)
                / market_data.current_price
            )
            if price_deviation > 0.05:
                issues.append(f"entry_price偏差过大: {price_deviation:.1%}")

        # 检查止损合理性
        if decision.stop_loss_price and decision.entry_price and decision.entry_price > 0:
            sl_distance = (
                abs(decision.stop_loss_price - decision.entry_price)
                / decision.entry_price
            )
            if sl_distance > 0.15 or sl_distance < 0.005:
                issues.append(f"止损距离异常: {sl_distance:.1%}")

        # 检查风险回报比
        if (
            decision.stop_loss_price
            and decision.take_profit_price
            and decision.entry_price
        ):
            risk = abs(decision.entry_price - decision.stop_loss_price)
            reward = abs(decision.take_profit_price - decision.entry_price)
            if risk > 0:
                rr_ratio = reward / risk
                if rr_ratio < 1.0:
                    issues.append(f"风险回报比不足: {rr_ratio:.1f}")

        return {
            "quality_score": max(0, 100 - len(issues) * 20),
            "issues": issues,
        }

    async def update_decision_order(
        self, decision_id: UUID, order_id: UUID
    ) -> None:
        """更新决策关联的订单 ID

        Args:
            decision_id: 决策 ID
            order_id: 订单 ID
        """
        await self.db.execute(
            "UPDATE decisions SET order_id = $1 WHERE id = $2",
            order_id,
            decision_id,
        )
        logger.info(f"决策 {decision_id} 已关联订单 {order_id}")

    async def save_order(
        self,
        symbol: str,
        exchange_order_id: str,
        side: str,
        order_type: str,
        price: Optional[float],
        size: float,
        status: str,
    ) -> UUID:
        """保存订单记录

        Args:
            symbol: 交易对
            exchange_order_id: 交易所订单 ID
            side: 买卖方向 (buy/sell)
            order_type: 订单类型 (market/limit)
            price: 价格
            size: 数量
            status: 状态

        Returns:
            订单 ID (UUID)
        """
        order_id = await self.db.fetchval(
            """
            INSERT INTO orders (
                symbol, exchange_order_id, side, order_type,
                price, size, status
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7
            ) RETURNING id
            """,
            symbol,
            exchange_order_id,
            side,
            order_type,
            price,
            size,
            status,
        )
        logger.info(f"订单已保存: {order_id}")
        return order_id

    async def update_order_fill(
        self,
        order_id: UUID,
        filled_price: float,
        filled_size: float,
        fee: Optional[float],
        status: str,
    ) -> None:
        """更新订单成交信息

        Args:
            order_id: 订单 ID
            filled_price: 成交价格
            filled_size: 成交数量
            fee: 手续费
            status: 状态
        """
        await self.db.execute(
            """
            UPDATE orders SET
                filled_price = $1,
                filled_size = $2,
                fee = $3,
                status = $4,
                closed_at = CASE WHEN $4 IN ('filled', 'cancelled') THEN NOW() ELSE closed_at END
            WHERE id = $5
            """,
            filled_price,
            filled_size,
            fee,
            status,
            order_id,
        )
        logger.info(f"订单 {order_id} 已更新: status={status}")

    async def save_position_open(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        entry_size: float,
        leverage: Optional[float],
        entry_decision_id: Optional[UUID] = None,
    ) -> UUID:
        """记录仓位开仓

        Args:
            symbol: 交易对
            side: 方向 (long/short)
            entry_price: 入场价格
            entry_size: 入场数量
            leverage: 杠杆
            entry_decision_id: 开仓决策 ID

        Returns:
            仓位 ID (UUID)
        """
        position_id = await self.db.fetchval(
            """
            INSERT INTO position_history (
                symbol, side, entry_time, entry_price, entry_size,
                leverage, entry_decision_id, status
            ) VALUES (
                $1, $2, NOW(), $3, $4, $5, $6, 'open'
            ) RETURNING id
            """,
            symbol,
            side,
            entry_price,
            entry_size,
            leverage,
            entry_decision_id,
        )
        logger.info(f"仓位已记录: {position_id}, {side} {symbol}")
        return position_id

    async def save_position_close(
        self,
        position_id: UUID,
        exit_price: float,
        realized_pnl: float,
        pnl_percent: float,
        fee_total: Optional[float],
        exit_decision_id: Optional[UUID] = None,
    ) -> None:
        """记录仓位平仓

        Args:
            position_id: 仓位 ID
            exit_price: 出场价格
            realized_pnl: 已实现盈亏
            pnl_percent: 盈亏百分比
            fee_total: 总手续费
            exit_decision_id: 平仓决策 ID
        """
        await self.db.execute(
            """
            UPDATE position_history SET
                exit_time = NOW(),
                exit_price = $1,
                realized_pnl = $2,
                pnl_percent = $3,
                fee_total = $4,
                exit_decision_id = $5,
                status = 'closed'
            WHERE id = $6
            """,
            exit_price,
            realized_pnl,
            pnl_percent,
            fee_total,
            exit_decision_id,
            position_id,
        )
        logger.info(f"仓位 {position_id} 已平仓: pnl={realized_pnl}")

    async def update_daily_stats(
        self,
        symbol: str,
        pnl: float,
        is_win: bool,
    ) -> None:
        """更新每日统计

        Args:
            symbol: 交易对
            pnl: 本次盈亏
            is_win: 是否盈利
        """
        today = datetime.now().date()

        # Upsert daily stats
        await self.db.execute(
            """
            INSERT INTO daily_stats (date, symbol, total_trades, winning_trades, losing_trades, total_pnl)
            VALUES ($1, $2, 1, $3, $4, $5)
            ON CONFLICT (date, symbol) DO UPDATE SET
                total_trades = daily_stats.total_trades + 1,
                winning_trades = daily_stats.winning_trades + $3,
                losing_trades = daily_stats.losing_trades + $4,
                total_pnl = daily_stats.total_pnl + $5
            """,
            today,
            symbol,
            1 if is_win else 0,
            0 if is_win else 1,
            pnl,
        )
        logger.info(f"每日统计已更新: {today} {symbol}")

    async def log_operation(
        self,
        action: str,
        operator: Optional[str] = None,
        details: Optional[dict] = None,
        ip_address: Optional[str] = None,
    ) -> None:
        """记录操作日志

        Args:
            action: 操作类型
            operator: 操作者
            details: 详细信息
            ip_address: IP 地址
        """
        await self.db.execute(
            """
            INSERT INTO operation_logs (action, operator, details, ip_address)
            VALUES ($1, $2, $3, $4)
            """,
            action,
            operator,
            json.dumps(details) if details else None,
            ip_address,
        )

    # ==================== 回测持久化 ====================

    async def create_backtest(
        self,
        mode: str,
        symbol: Optional[str],
        start_date: str,
        end_date: str,
        initial_capital: float,
    ) -> UUID:
        """创建回测记录

        Args:
            mode: 回测模式 (single/multi)
            symbol: 交易对 (单币种模式)
            start_date: 开始日期 YYYY-MM-DD
            end_date: 结束日期 YYYY-MM-DD
            initial_capital: 初始资金

        Returns:
            回测 ID
        """
        from datetime import date as date_type

        # 转换字符串为 date 对象
        if isinstance(start_date, str):
            start_date = date_type.fromisoformat(start_date)
        if isinstance(end_date, str):
            end_date = date_type.fromisoformat(end_date)

        backtest_id = await self.db.fetchval(
            """
            INSERT INTO backtests (
                mode, symbol, start_date, end_date,
                initial_capital, status, progress
            ) VALUES (
                $1, $2, $3, $4, $5, 'running', 0
            ) RETURNING id
            """,
            mode,
            symbol,
            start_date,
            end_date,
            initial_capital,
        )
        logger.info(f"回测已创建: {backtest_id}")
        return backtest_id

    async def update_backtest_progress(
        self, backtest_id: UUID, progress: int
    ) -> None:
        """更新回测进度

        Args:
            backtest_id: 回测 ID
            progress: 进度 (0-100)
        """
        await self.db.execute(
            "UPDATE backtests SET progress = $1 WHERE id = $2",
            progress,
            backtest_id,
        )

    async def complete_backtest(
        self,
        backtest_id: UUID,
        final_capital: float,
        total_pnl: float,
        total_trades: int,
        winning_trades: int,
        max_drawdown: float,
        sharpe_ratio: float,
        symbol_results: Optional[dict] = None,
    ) -> None:
        """完成回测并保存结果

        Args:
            backtest_id: 回测 ID
            final_capital: 最终资金
            total_pnl: 总盈亏
            total_trades: 总交易数
            winning_trades: 盈利交易数
            max_drawdown: 最大回撤
            sharpe_ratio: 夏普比率
            symbol_results: 各交易对结果
        """
        await self.db.execute(
            """
            UPDATE backtests SET
                status = 'completed',
                progress = 100,
                final_capital = $1,
                total_pnl = $2,
                total_trades = $3,
                winning_trades = $4,
                max_drawdown = $5,
                sharpe_ratio = $6,
                symbol_results = $7,
                completed_at = NOW()
            WHERE id = $8
            """,
            final_capital,
            total_pnl,
            total_trades,
            winning_trades,
            max_drawdown,
            sharpe_ratio,
            json.dumps(symbol_results) if symbol_results else None,
            backtest_id,
        )
        logger.info(f"回测已完成: {backtest_id}, pnl={total_pnl}")

    async def fail_backtest(
        self, backtest_id: UUID, error_message: str
    ) -> None:
        """标记回测失败

        Args:
            backtest_id: 回测 ID
            error_message: 错误信息
        """
        await self.db.execute(
            """
            UPDATE backtests SET
                status = 'failed',
                error_message = $1
            WHERE id = $2
            """,
            error_message,
            backtest_id,
        )
        logger.error(f"回测失败: {backtest_id}, error={error_message}")

    async def save_backtest_trade(
        self,
        backtest_id: UUID,
        symbol: str,
        side: str,
        entry_time: datetime,
        entry_price: float,
        exit_time: Optional[datetime],
        exit_price: Optional[float],
        size: float = 0.0,
        pnl: Optional[float] = None,
        pnl_percent: Optional[float] = None,
        decision_snapshot: Optional[dict] = None,
    ) -> UUID:
        """保存回测交易记录"""
        trade_id = await self.db.fetchval(
            """
            INSERT INTO backtest_trades (
                backtest_id, symbol, side, entry_time, entry_price,
                exit_time, exit_price, size, pnl, pnl_percent, decision_snapshot
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11
            ) RETURNING id
            """,
            backtest_id,
            symbol,
            side,
            entry_time,
            entry_price,
            exit_time,
            exit_price,
            size,
            pnl,
            pnl_percent,
            json.dumps(decision_snapshot) if decision_snapshot else None,
        )
        return trade_id

    async def save_backtest_equity(
        self,
        backtest_id: UUID,
        timestamp: datetime,
        total_equity: float,
        symbol_equity: Optional[dict] = None,
    ) -> None:
        """保存回测权益曲线数据点

        Args:
            backtest_id: 回测 ID
            timestamp: 时间戳
            total_equity: 总权益
            symbol_equity: 各交易对权益
        """
        await self.db.execute(
            """
            INSERT INTO backtest_equity (
                backtest_id, timestamp, total_equity, symbol_equity
            ) VALUES ($1, $2, $3, $4)
            """,
            backtest_id,
            timestamp,
            total_equity,
            json.dumps(symbol_equity) if symbol_equity else None,
        )

    # ==================== LLM 使用记录 ====================

    async def record_llm_usage(
        self,
        provider: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: int = 0,
        cost_usd: float = 0.0,
        latency_ms: int = 0,
        success: bool = True,
        error_message: Optional[str] = None,
        decision_id: Optional[UUID] = None,
        usage_type: Optional[str] = None,
    ) -> UUID:
        """记录 LLM 调用"""
        if total_tokens == 0:
            total_tokens = input_tokens + output_tokens

        record_id = await self.db.fetchval(
            """
            INSERT INTO llm_usage (
                provider, model, input_tokens, output_tokens, total_tokens,
                cost_usd, latency_ms, success, error_message, decision_id,
                usage_type
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            RETURNING id
            """,
            provider,
            model,
            input_tokens,
            output_tokens,
            total_tokens,
            cost_usd,
            latency_ms,
            success,
            error_message,
            decision_id,
            usage_type,
        )
        logger.debug(
            f"Recorded LLM usage: {provider}/{model} "
            f"tokens={total_tokens} cost=${cost_usd:.6f} type={usage_type}"
        )
        return record_id

    async def get_llm_usage_stats(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> dict:
        """获取 LLM 使用统计

        Args:
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            统计数据
        """
        params = []
        where_parts = []

        if start_time:
            where_parts.append(f"created_at >= ${len(params) + 1}")
            params.append(start_time)
        if end_time:
            where_parts.append(f"created_at <= ${len(params) + 1}")
            params.append(end_time)

        where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

        # 总体统计
        row = await self.db.fetchrow(
            f"""
            SELECT
                COUNT(*) as total_calls,
                COALESCE(SUM(total_tokens), 0) as total_tokens,
                COALESCE(SUM(cost_usd), 0) as total_cost_usd,
                COALESCE(AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END), 0) as success_rate,
                COALESCE(AVG(latency_ms), 0) as avg_latency_ms
            FROM llm_usage
            {where_clause}
            """,
            *params,
        )

        # 今日费用
        today = datetime.now().date()
        today_cost = await self.db.fetchval(
            """
            SELECT COALESCE(SUM(cost_usd), 0)
            FROM llm_usage
            WHERE DATE(created_at) = $1
            """,
            today,
        )

        # 按 provider 统计
        provider_rows = await self.db.fetch(
            f"""
            SELECT
                provider,
                COUNT(*) as calls,
                COALESCE(SUM(total_tokens), 0) as tokens,
                COALESCE(SUM(cost_usd), 0) as cost_usd
            FROM llm_usage
            {where_clause}
            GROUP BY provider
            """,
            *params,
        )

        by_provider = {}
        for r in provider_rows:
            by_provider[r["provider"]] = {
                "calls": r["calls"],
                "tokens": r["tokens"],
                "cost_usd": float(r["cost_usd"]),
            }

        return {
            "total_calls": row["total_calls"],
            "total_tokens": row["total_tokens"],
            "total_cost_usd": float(row["total_cost_usd"]),
            "today_cost_usd": float(today_cost),
            "success_rate": float(row["success_rate"]) * 100,
            "avg_latency_ms": float(row["avg_latency_ms"]),
            "by_provider": by_provider,
        }

    async def get_llm_usage_records(
        self,
        limit: int = 100,
        offset: int = 0,
        provider: Optional[str] = None,
    ) -> dict:
        """获取 LLM 使用记录列表

        Args:
            limit: 返回数量
            offset: 偏移量
            provider: 按 provider 筛选

        Returns:
            记录列表和总数
        """
        params = []
        where_clause = ""

        if provider:
            where_clause = "WHERE provider = $1"
            params.append(provider)

        # 获取记录
        rows = await self.db.fetch(
            f"""
            SELECT
                id, created_at, provider, model, input_tokens, output_tokens,
                total_tokens, cost_usd, latency_ms, success, error_message
            FROM llm_usage
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
            """,
            *params,
            limit,
            offset,
        )

        # 获取总数
        total = await self.db.fetchval(
            f"SELECT COUNT(*) FROM llm_usage {where_clause}",
            *params,
        )

        records = [
            {
                "id": str(r["id"]),
                "timestamp": r["created_at"].isoformat(),
                "provider": r["provider"],
                "model": r["model"],
                "input_tokens": r["input_tokens"],
                "output_tokens": r["output_tokens"],
                "total_tokens": r["total_tokens"],
                "cost_usd": float(r["cost_usd"]),
                "latency_ms": r["latency_ms"],
                "success": r["success"],
                "error_message": r["error_message"],
            }
            for r in rows
        ]

        return {
            "records": records,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    async def get_llm_daily_stats(self, days: int = 30) -> list:
        """获取每日 LLM 使用统计

        Args:
            days: 天数

        Returns:
            每日统计列表
        """
        rows = await self.db.fetch(
            """
            SELECT
                DATE(created_at) as date,
                provider,
                COUNT(*) as calls,
                COALESCE(SUM(total_tokens), 0) as tokens,
                COALESCE(SUM(cost_usd), 0) as cost_usd
            FROM llm_usage
            WHERE created_at >= NOW() - INTERVAL '%s days'
            GROUP BY DATE(created_at), provider
            ORDER BY date
            """ % days,
        )

        return [
            {
                "date": str(r["date"]),
                "provider": r["provider"],
                "calls": r["calls"],
                "tokens": r["tokens"],
                "cost_usd": float(r["cost_usd"]),
            }
            for r in rows
        ]
