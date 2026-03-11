"""策略预设持久化服务"""

import json
from typing import Optional
from datetime import datetime, timezone

from .database import DatabaseManager
from ..strategies.presets import SYSTEM_PRESETS, DEFAULT_PRESET_NAME, get_all_system_defaults
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
                # Skip config update if user has modified this preset
                is_modified = await self.db.fetchval(
                    "SELECT is_modified FROM strategy_presets WHERE name = $1",
                    preset.name,
                )
                if is_modified:
                    # Only update metadata, keep user's config
                    await self.db.execute(
                        """UPDATE strategy_presets
                        SET display_name=$2, description=$3, category=$4, risk_level=$5,
                            updated_at=NOW()
                        WHERE name=$1 AND is_system=TRUE""",
                        preset.name,
                        preset.display_name,
                        preset.description,
                        preset.category,
                        preset.risk_level,
                    )
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
            """SELECT sp.*, a.activated_at as current_activated_at,
                      COALESCE(a.is_locked, FALSE) as is_locked
            FROM active_strategy a
            JOIN strategy_presets sp ON sp.id = a.preset_id
            WHERE a.deactivated_at IS NULL
            ORDER BY a.activated_at DESC LIMIT 1"""
        )
        return dict(row) if row else None

    async def activate_preset(self, preset_id: int, is_locked: bool = False) -> bool:
        """Activate a preset. Refuses if current strategy is locked."""
        preset = await self.get_preset_by_id(preset_id)
        if not preset:
            return False

        # Check if current strategy is locked
        current = await self.get_active_preset()
        if current and current.get("is_locked"):
            logger.warning(f"Cannot switch strategy: current preset '{current['name']}' is locked")
            return False

        await self.db.execute(
            """UPDATE active_strategy SET deactivated_at = NOW()
            WHERE deactivated_at IS NULL"""
        )

        await self.db.execute(
            "INSERT INTO active_strategy (preset_id, is_locked) VALUES ($1, $2)",
            preset_id,
            is_locked,
        )
        logger.info(f"Activated strategy preset: {preset['name']} (locked={is_locked})")
        return True

    async def set_strategy_lock(self, is_locked: bool) -> bool:
        """Toggle lock on the currently active strategy."""
        result = await self.db.execute(
            """UPDATE active_strategy SET is_locked = $1
            WHERE deactivated_at IS NULL""",
            is_locked,
        )
        if result:
            logger.info(f"Strategy lock set to {is_locked}")
            return True
        return False

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
                WHERE exit_time BETWEEN $1 AND $2""",
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

    async def update_preset_config(self, preset_id: int, config: dict) -> bool:
        """Update a preset's config. Marks system presets as modified."""
        preset = await self.get_preset_by_id(preset_id)
        if not preset:
            return False

        if preset["is_system"]:
            await self.db.execute(
                """UPDATE strategy_presets
                SET config_json=$2, is_modified=TRUE, updated_at=NOW()
                WHERE id=$1""",
                preset_id,
                json.dumps(config),
            )
        else:
            await self.db.execute(
                """UPDATE strategy_presets
                SET config_json=$2, updated_at=NOW()
                WHERE id=$1""",
                preset_id,
                json.dumps(config),
            )
        logger.info(f"Updated preset config: id={preset_id}")
        return True

    async def save_as_new_preset(
        self,
        source_preset_id: int,
        config: dict,
        name: str,
        display_name: str,
        description: str,
        category: str,
        risk_level: str,
    ) -> Optional[int]:
        """Create a new custom preset based on a source preset."""
        new_id = await self.db.fetchval(
            """INSERT INTO strategy_presets
            (name, display_name, description, category, risk_level,
             config_json, is_system, source_preset_id)
            VALUES ($1, $2, $3, $4, $5, $6, FALSE, $7)
            RETURNING id""",
            name,
            display_name,
            description,
            category,
            risk_level,
            json.dumps(config),
            source_preset_id,
        )
        logger.info(f"Created custom preset: {name} (id={new_id})")
        return new_id

    async def reset_preset(self, preset_id: int) -> bool:
        """Reset a modified system preset to its default config."""
        preset = await self.get_preset_by_id(preset_id)
        if not preset or not preset["is_system"] or not preset.get("is_modified"):
            return False

        defaults = get_all_system_defaults()
        default_config = defaults.get(preset["name"])
        if not default_config:
            return False

        await self.db.execute(
            """UPDATE strategy_presets
            SET config_json=$2, is_modified=FALSE, updated_at=NOW()
            WHERE id=$1""",
            preset_id,
            json.dumps(default_config),
        )
        logger.info(f"Reset preset to default: {preset['name']}")
        return True

    async def delete_preset(self, preset_id: int) -> bool:
        """Delete a custom (non-system) preset."""
        preset = await self.get_preset_by_id(preset_id)
        if not preset or preset["is_system"]:
            return False

        # Check if currently active
        active = await self.get_active_preset()
        if active and active["id"] == preset_id:
            return False

        # Clear source_preset_id references from child presets
        await self.db.execute(
            "UPDATE strategy_presets SET source_preset_id=NULL WHERE source_preset_id=$1",
            preset_id,
        )

        await self.db.execute(
            "DELETE FROM strategy_presets WHERE id=$1 AND is_system=FALSE",
            preset_id,
        )
        logger.info(f"Deleted custom preset: {preset['name']} (id={preset_id})")
        return True

    def get_system_defaults(self) -> dict[str, dict]:
        """Return all system preset default configs."""
        return get_all_system_defaults()

    async def check_name_exists(self, name: str) -> bool:
        """Check if a preset name already exists."""
        existing = await self.db.fetchval(
            "SELECT id FROM strategy_presets WHERE name = $1", name
        )
        return existing is not None

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

    async def get_all_symbol_strategies(self) -> list:
        """Load all enabled symbol strategy configurations from database."""
        from ..models.symbol_strategy import SymbolStrategyConfig
        from ..models.strategy_preset import StrategyPresetConfig

        query = """
            SELECT ss.symbol, sp.name as preset_name, sp.config_json,
                   ss.config_overrides, ss.enabled
            FROM symbol_strategy ss
            JOIN strategy_presets sp ON ss.preset_id = sp.id
            WHERE ss.enabled = true
            ORDER BY ss.symbol
        """
        rows = await self.db.fetch(query)

        results = []
        for row in rows:
            config_json = row["config_json"] if isinstance(row["config_json"], dict) else {}
            overrides = row["config_overrides"] if isinstance(row["config_overrides"], dict) else {}
            preset_config = StrategyPresetConfig(**config_json)
            results.append(
                SymbolStrategyConfig(
                    symbol=row["symbol"],
                    preset_name=row["preset_name"],
                    preset_config=preset_config,
                    config_overrides=overrides,
                )
            )
        return results
