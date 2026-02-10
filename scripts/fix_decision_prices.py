"""修复旧决策记录中缺失的 entry_price / stop_loss / take_profit

从 technical_snapshots 中获取当时的 price 和 atr，
用与 decision engine 相同的逻辑补算价格。

用法:
    DASHBOARD_DATABASE_URL=postgresql://... python scripts/fix_decision_prices.py [--dry-run]
"""

import asyncio
import os
import sys

import asyncpg


# 与 decision engine 一致的默认参数
DEFAULT_ATR_SL_MULTIPLIER = 2.0
DEFAULT_ATR_TP_MULTIPLIER = 3.0
DEFAULT_STOP_LOSS_PCT = 0.02   # 2%
DEFAULT_TAKE_PROFIT_PCT = 0.03  # 3%


async def fix_prices(dry_run: bool = False):
    db_url = os.environ.get("DASHBOARD_DATABASE_URL")
    if not db_url:
        print("错误: 请设置 DASHBOARD_DATABASE_URL 环境变量")
        sys.exit(1)

    conn = await asyncpg.connect(db_url)

    try:
        # 查找需要修复的决策: open/add 操作且价格缺失或为0
        rows = await conn.fetch("""
            SELECT d.id, d.action, d.entry_price, d.stop_loss, d.take_profit,
                   ts.price AS market_price, ts.atr
            FROM decisions d
            LEFT JOIN technical_snapshots ts ON ts.decision_id = d.id
            WHERE d.action IN ('open_long', 'open_short', 'add_long', 'add_short')
              AND (
                  d.entry_price IS NULL OR d.entry_price = 0
                  OR d.stop_loss IS NULL OR d.stop_loss = 0
                  OR d.take_profit IS NULL OR d.take_profit = 0
              )
            ORDER BY d.created_at
        """)

        print(f"找到 {len(rows)} 条需要修复的决策记录")

        if not rows:
            print("无需修复")
            return

        fixed = 0
        skipped = 0

        for row in rows:
            decision_id = row["id"]
            action = row["action"]
            market_price = float(row["market_price"]) if row["market_price"] else None
            atr = float(row["atr"]) if row["atr"] else None
            current_entry = float(row["entry_price"]) if row["entry_price"] else 0
            current_sl = float(row["stop_loss"]) if row["stop_loss"] else 0
            current_tp = float(row["take_profit"]) if row["take_profit"] else 0

            if not market_price:
                print(f"  跳过 {decision_id}: 无市场价格快照")
                skipped += 1
                continue

            is_long = "long" in action

            # 计算缺失的价格
            entry = current_entry if current_entry else market_price

            if atr and atr > 0:
                sl = current_sl if current_sl else (
                    entry - DEFAULT_ATR_SL_MULTIPLIER * atr if is_long
                    else entry + DEFAULT_ATR_SL_MULTIPLIER * atr
                )
                tp = current_tp if current_tp else (
                    entry + DEFAULT_ATR_TP_MULTIPLIER * atr if is_long
                    else entry - DEFAULT_ATR_TP_MULTIPLIER * atr
                )
            else:
                sl = current_sl if current_sl else (
                    entry * (1 - DEFAULT_STOP_LOSS_PCT) if is_long
                    else entry * (1 + DEFAULT_STOP_LOSS_PCT)
                )
                tp = current_tp if current_tp else (
                    entry * (1 + DEFAULT_TAKE_PROFIT_PCT) if is_long
                    else entry * (1 - DEFAULT_TAKE_PROFIT_PCT)
                )

            print(f"  {decision_id} ({action}): entry={entry:.2f}, sl={sl:.2f}, tp={tp:.2f}"
                  f" (原: entry={current_entry}, sl={current_sl}, tp={current_tp})")

            if not dry_run:
                await conn.execute("""
                    UPDATE decisions
                    SET entry_price = $1, stop_loss = $2, take_profit = $3
                    WHERE id = $4
                """, entry, sl, tp, decision_id)

            fixed += 1

        print(f"\n{'[DRY RUN] ' if dry_run else ''}修复 {fixed} 条, 跳过 {skipped} 条")

    finally:
        await conn.close()


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("=== DRY RUN 模式 (不会修改数据库) ===\n")
    asyncio.run(fix_prices(dry_run))
