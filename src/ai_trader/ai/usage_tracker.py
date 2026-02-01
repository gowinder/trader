"""LLM 使用量追踪器 - 记录调用统计和费用"""

import json
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, asdict
import aiosqlite

from ..utils.logger import logger


@dataclass
class UsageRecord:
    """使用记录"""
    id: Optional[int] = None
    timestamp: Optional[datetime] = None
    provider: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    success: bool = True
    error_message: str = ""

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if self.total_tokens == 0:
            self.total_tokens = self.input_tokens + self.output_tokens


@dataclass
class UsageStats:
    """使用统计"""
    total_calls: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    success_rate: float = 0.0
    avg_latency_ms: float = 0.0
    by_provider: Dict[str, Dict[str, Any]] = None

    def __post_init__(self):
        if self.by_provider is None:
            self.by_provider = {}


class PricingManager:
    """价格管理器"""

    DEFAULT_PRICING = {
        "openrouter": {
            "deepseek/deepseek-v3.2": {"input": 0.14, "output": 0.28},
            "deepseek/deepseek-chat": {"input": 0.14, "output": 0.28},
        },
        "gemini": {
            "gemini-2.0-flash": {"input": 0, "output": 0},
            "gemini-1.5-pro": {"input": 0, "output": 0},
        },
        "codex": {
            "gpt-4o": {"input": 2.5, "output": 10},
            "gpt-4o-mini": {"input": 0.15, "output": 0.6},
        },
        "qwen": {
            "qwen-max-latest": {"input": 0, "output": 0},
            "qwen-plus": {"input": 0, "output": 0},
        },
    }

    def __init__(self, pricing_file: Optional[str] = None):
        self._pricing = self.DEFAULT_PRICING.copy()
        self._pricing_file = pricing_file

        if pricing_file:
            self._load_pricing_file(pricing_file)

    def _load_pricing_file(self, path: str):
        """从文件加载价格配置"""
        file_path = Path(path)
        if file_path.exists():
            try:
                with open(file_path, "r") as f:
                    custom_pricing = json.load(f)
                    # 合并配置
                    for provider, models in custom_pricing.items():
                        if provider not in self._pricing:
                            self._pricing[provider] = {}
                        self._pricing[provider].update(models)
            except Exception as e:
                logger.warning(f"Failed to load pricing file: {e}")

    def get_cost(self, provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
        """计算费用（USD）"""
        provider_pricing = self._pricing.get(provider, {})

        # 尝试精确匹配
        model_pricing = provider_pricing.get(model)

        # 尝试模糊匹配
        if model_pricing is None:
            for m, p in provider_pricing.items():
                if m in model or model in m:
                    model_pricing = p
                    break

        if model_pricing is None:
            return 0.0

        # 价格单位是 per 1M tokens
        input_cost = (input_tokens / 1_000_000) * model_pricing.get("input", 0)
        output_cost = (output_tokens / 1_000_000) * model_pricing.get("output", 0)

        return input_cost + output_cost

    def save_pricing(self, path: str):
        """保存价格配置到文件"""
        with open(path, "w") as f:
            json.dump(self._pricing, f, indent=2)


class UsageTracker:
    """使用量追踪器"""

    def __init__(
        self,
        db_path: str = "data/llm_usage.db",
        pricing_file: Optional[str] = None,
    ):
        self._db_path = db_path
        self._pricing_manager = PricingManager(pricing_file)
        self._db: Optional[aiosqlite.Connection] = None
        self._initialized = False

    async def _ensure_initialized(self):
        """确保数据库已初始化"""
        if self._initialized:
            return

        # 确保目录存在
        db_dir = Path(self._db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

        self._db = await aiosqlite.connect(self._db_path)

        # 创建表
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS llm_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                total_tokens INTEGER DEFAULT 0,
                cost_usd REAL DEFAULT 0,
                latency_ms INTEGER DEFAULT 0,
                success INTEGER DEFAULT 1,
                error_message TEXT DEFAULT ''
            )
        """)

        # 创建索引
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp ON llm_usage(timestamp)
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_provider ON llm_usage(provider)
        """)

        await self._db.commit()
        self._initialized = True

    async def record(
        self,
        provider: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        latency_ms: int = 0,
        success: bool = True,
        error_message: str = "",
    ):
        """记录一次调用"""
        await self._ensure_initialized()

        total_tokens = input_tokens + output_tokens
        cost_usd = self._pricing_manager.get_cost(
            provider, model, input_tokens, output_tokens
        )

        record = UsageRecord(
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            success=success,
            error_message=error_message,
        )

        await self._db.execute(
            """
            INSERT INTO llm_usage
            (timestamp, provider, model, input_tokens, output_tokens, total_tokens,
             cost_usd, latency_ms, success, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.timestamp.isoformat(),
                record.provider,
                record.model,
                record.input_tokens,
                record.output_tokens,
                record.total_tokens,
                record.cost_usd,
                record.latency_ms,
                1 if record.success else 0,
                record.error_message,
            ),
        )
        await self._db.commit()

        logger.debug(
            f"Recorded LLM usage: {provider}/{model} "
            f"tokens={total_tokens} cost=${cost_usd:.4f}"
        )

    async def get_stats(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> UsageStats:
        """获取统计数据"""
        await self._ensure_initialized()

        # 默认时间范围：全部
        where_clause = ""
        params = []

        if start_time:
            where_clause += " AND timestamp >= ?"
            params.append(start_time.isoformat())
        if end_time:
            where_clause += " AND timestamp <= ?"
            params.append(end_time.isoformat())

        if where_clause:
            where_clause = "WHERE 1=1" + where_clause

        # 总体统计
        cursor = await self._db.execute(
            f"""
            SELECT
                COUNT(*) as total_calls,
                COALESCE(SUM(total_tokens), 0) as total_tokens,
                COALESCE(SUM(cost_usd), 0) as total_cost_usd,
                COALESCE(AVG(CASE WHEN success = 1 THEN 1.0 ELSE 0.0 END), 0) as success_rate,
                COALESCE(AVG(latency_ms), 0) as avg_latency_ms
            FROM llm_usage
            {where_clause}
            """,
            params,
        )
        row = await cursor.fetchone()

        stats = UsageStats(
            total_calls=row[0],
            total_tokens=row[1],
            total_cost_usd=row[2],
            success_rate=row[3] * 100,
            avg_latency_ms=row[4],
        )

        # 按 provider 统计
        cursor = await self._db.execute(
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
            params,
        )

        stats.by_provider = {}
        async for row in cursor:
            stats.by_provider[row[0]] = {
                "calls": row[1],
                "tokens": row[2],
                "cost_usd": row[3],
            }

        return stats

    async def get_daily_stats(
        self,
        days: int = 30,
    ) -> List[Dict[str, Any]]:
        """获取每日统计数据"""
        await self._ensure_initialized()

        start_time = datetime.now() - timedelta(days=days)

        cursor = await self._db.execute(
            """
            SELECT
                DATE(timestamp) as date,
                provider,
                COUNT(*) as calls,
                COALESCE(SUM(total_tokens), 0) as tokens,
                COALESCE(SUM(cost_usd), 0) as cost_usd
            FROM llm_usage
            WHERE timestamp >= ?
            GROUP BY DATE(timestamp), provider
            ORDER BY date
            """,
            (start_time.isoformat(),),
        )

        results = []
        async for row in cursor:
            results.append({
                "date": row[0],
                "provider": row[1],
                "calls": row[2],
                "tokens": row[3],
                "cost_usd": row[4],
            })

        return results

    async def get_records(
        self,
        limit: int = 100,
        offset: int = 0,
        provider: Optional[str] = None,
    ) -> List[UsageRecord]:
        """获取调用记录"""
        await self._ensure_initialized()

        where_clause = ""
        params = []

        if provider:
            where_clause = "WHERE provider = ?"
            params.append(provider)

        params.extend([limit, offset])

        cursor = await self._db.execute(
            f"""
            SELECT
                id, timestamp, provider, model, input_tokens, output_tokens,
                total_tokens, cost_usd, latency_ms, success, error_message
            FROM llm_usage
            {where_clause}
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
            """,
            params,
        )

        records = []
        async for row in cursor:
            records.append(UsageRecord(
                id=row[0],
                timestamp=datetime.fromisoformat(row[1]),
                provider=row[2],
                model=row[3],
                input_tokens=row[4],
                output_tokens=row[5],
                total_tokens=row[6],
                cost_usd=row[7],
                latency_ms=row[8],
                success=bool(row[9]),
                error_message=row[10],
            ))

        return records

    async def get_today_cost(self) -> float:
        """获取今日费用"""
        await self._ensure_initialized()

        today = datetime.now().date().isoformat()

        cursor = await self._db.execute(
            """
            SELECT COALESCE(SUM(cost_usd), 0)
            FROM llm_usage
            WHERE DATE(timestamp) = ?
            """,
            (today,),
        )
        row = await cursor.fetchone()
        return row[0]

    async def close(self):
        """关闭数据库连接"""
        if self._db:
            await self._db.close()
            self._db = None
            self._initialized = False


# 全局单例
_usage_tracker: Optional[UsageTracker] = None


def get_usage_tracker() -> UsageTracker:
    """获取全局 UsageTracker 实例"""
    global _usage_tracker
    if _usage_tracker is None:
        _usage_tracker = UsageTracker()
    return _usage_tracker
