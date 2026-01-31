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
                    stop_loss, take_profit, reasoning,
                    llm_provider, llm_model, llm_raw_output, llm_tokens_used
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14
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
                llm_provider,
                llm_model,
                llm_raw_output,
                llm_tokens_used,
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

            logger.info(f"决策已保存: {decision_id}, action={decision.action}")
            return decision_id

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
