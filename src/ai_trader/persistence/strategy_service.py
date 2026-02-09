"""策略预设持久化服务"""

import json
from typing import Optional
from datetime import datetime, timezone

from .database import DatabaseManager
from ..strategies.presets import SYSTEM_PRESETS, DEFAULT_PRESET_NAME
from ..utils.logger import logger


class StrategyPresetService:
    """策略预设的数据库操作"""

    def __init__(self, db: DatabaseManager):
        self.db = db

    async def init_system_presets(self):
        """初始化系统预设模板（仅插入不存在的）"""
        for preset in SYSTEM_PRESETS:
            existing = await self.db.fetchval(
                "SELECT id FROM strategy_presets WHERE name = $1",
                preset.name,
            )
            if existing is None:
                await self.db.execute(
                    """INSERT INTO strategy_presets
                    (name, display_name, description, category, risk_level, config_json, is_system)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)""",
                    preset.name,
                    preset.display_name,
                    preset.description,
                    preset.category,
                    preset.risk_level,
                    json.dumps(preset.config.model_dump()),
                    True,
                )
                logger.info(f"Initialized system preset: {preset.name}")
            else:
                await self.db.execute(
                    """UPDATE strategy_presets
                    SET display_name=$2, description=$3, category=$4, risk_level=$5,
                        config_json=$6, updated_at=NOW()
                    WHERE name=$1 AND is_system=TRUE""",
                    preset.name,
                    preset.display_name,
                    preset.description,
                    preset.category,
                    preset.risk_level,
                    json.dumps(preset.config.model_dump()),
                )

    async def get_all_presets(self) -> list[dict]:
        """获取所有预设模板"""
        rows = await self.db.fetch(
            "SELECT * FROM strategy_presets ORDER BY id"
        )
        return [dict(r) for r in rows]

    async def get_preset_by_id(self, preset_id: int) -> Optional[dict]:
        """按 ID 获取预设"""
        row = await self.db.fetchrow(
            "SELECT * FROM strategy_presets WHERE id = $1", preset_id
        )
        return dict(row) if row else None

    async def get_active_preset(self) -> Optional[dict]:
        """获取当前激活的策略预设"""
        row = await self.db.fetchrow(
            """SELECT sp.*, a.activated_at as current_activated_at
            FROM active_strategy a
            JOIN strategy_presets sp ON sp.id = a.preset_id
            WHERE a.deactivated_at IS NULL
            ORDER BY a.activated_at DESC LIMIT 1"""
        )
        return dict(row) if row else None

    async def activate_preset(self, preset_id: int) -> bool:
        """激活指定预设（停用当前活跃的）"""
        preset = await self.get_preset_by_id(preset_id)
        if not preset:
            return False

        await self.db.execute(
            """UPDATE active_strategy SET deactivated_at = NOW()
            WHERE deactivated_at IS NULL"""
        )

        await self.db.execute(
            "INSERT INTO active_strategy (preset_id) VALUES ($1)",
            preset_id,
        )
        logger.info(f"Activated strategy preset: {preset['name']}")
        return True

    async def get_activation_history(self, limit: int = 20) -> list[dict]:
        """获取策略切换历史"""
        rows = await self.db.fetch(
            """SELECT a.*, sp.name, sp.display_name
            FROM active_strategy a
            JOIN strategy_presets sp ON sp.id = a.preset_id
            ORDER BY a.activated_at DESC LIMIT $1""",
            limit,
        )
        return [dict(r) for r in rows]

    async def get_preset_stats(self, preset_id: int) -> dict:
        """获取某个预设在激活期间的交易统计"""
        rows = await self.db.fetch(
            """SELECT a.activated_at, a.deactivated_at
            FROM active_strategy a WHERE a.preset_id = $1
            ORDER BY a.activated_at""",
            preset_id,
        )

        total_trades = 0
        total_pnl = 0.0
        wins = 0

        for r in rows:
            start = r["activated_at"]
            end = r["deactivated_at"] or datetime.now(timezone.utc)

            stats = await self.db.fetchrow(
                """SELECT
                    COUNT(*) as trade_count,
                    COALESCE(SUM(realized_pnl), 0) as total_pnl,
                    COUNT(*) FILTER (WHERE realized_pnl > 0) as win_count
                FROM position_history
                WHERE closed_at BETWEEN $1 AND $2""",
                start, end,
            )
            if stats:
                total_trades += stats["trade_count"]
                total_pnl += float(stats["total_pnl"])
                wins += stats["win_count"]

        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

        return {
            "preset_id": preset_id,
            "total_trades": total_trades,
            "total_pnl": round(total_pnl, 2),
            "win_rate": round(win_rate, 1),
        }

    async def ensure_default_active(self):
        """确保有活跃策略，没有则激活默认"""
        active = await self.get_active_preset()
        if active is None:
            default = await self.db.fetchval(
                "SELECT id FROM strategy_presets WHERE name = $1",
                DEFAULT_PRESET_NAME,
            )
            if default:
                await self.activate_preset(default)
                logger.info(f"Activated default preset: {DEFAULT_PRESET_NAME}")
