import type { ActionFunctionArgs, LoaderFunctionArgs } from "react-router";
import { db } from "db";
import { backtestScheduleConfig } from "db/schema";
import { desc, eq } from "drizzle-orm";

// GET: 获取当前配置
export async function loader({ request }: LoaderFunctionArgs) {
  const config = await db
    .select()
    .from(backtestScheduleConfig)
    .orderBy(desc(backtestScheduleConfig.updatedAt))
    .limit(1);

  if (config.length === 0) {
    // 返回默认配置
    return Response.json({
      enabled: false,
      scheduleType: "manual",
      scheduleHour: 0,
      scheduleDayOfWeek: null,
      symbols: ["BTCUSDT"],
      timeframe: "1h",
      lookbackDays: 30,
      initialCapital: 10000,
      enableFilters: true,
      strategies: ["trend_following"],
    });
  }

  const cfg = config[0];
  return Response.json({
    id: cfg.id,
    enabled: cfg.enabled,
    scheduleType: cfg.scheduleType,
    scheduleHour: cfg.scheduleHour,
    scheduleDayOfWeek: cfg.scheduleDayOfWeek,
    symbols: cfg.symbols,
    timeframe: cfg.timeframe,
    lookbackDays: cfg.lookbackDays,
    initialCapital: cfg.initialCapital ? parseFloat(cfg.initialCapital) : 10000,
    enableFilters: cfg.enableFilters,
    strategies: cfg.strategies,
    updatedAt: cfg.updatedAt.toISOString(),
  });
}

// POST: 更新配置
export async function action({ request }: ActionFunctionArgs) {
  if (request.method !== "POST") {
    return Response.json({ error: "Method not allowed" }, { status: 405 });
  }

  const body = await request.json();

  const {
    enabled,
    scheduleType,
    scheduleHour,
    scheduleDayOfWeek,
    symbols,
    timeframe,
    lookbackDays,
    initialCapital,
    enableFilters,
    strategies,
  } = body;

  // 查找现有配置
  const existing = await db
    .select()
    .from(backtestScheduleConfig)
    .orderBy(desc(backtestScheduleConfig.updatedAt))
    .limit(1);

  if (existing.length > 0) {
    // 更新现有配置
    await db
      .update(backtestScheduleConfig)
      .set({
        enabled: enabled ?? false,
        scheduleType: scheduleType ?? "manual",
        scheduleHour: scheduleHour ?? 0,
        scheduleDayOfWeek: scheduleDayOfWeek,
        symbols: symbols ?? ["BTCUSDT"],
        timeframe: timeframe ?? "1h",
        lookbackDays: lookbackDays ?? 30,
        initialCapital: String(initialCapital ?? 10000),
        enableFilters: enableFilters ?? true,
        strategies: strategies ?? ["trend_following"],
        updatedAt: new Date(),
      })
      .where(eq(backtestScheduleConfig.id, existing[0].id));
  } else {
    // 创建新配置
    await db.insert(backtestScheduleConfig).values({
      enabled: enabled ?? false,
      scheduleType: scheduleType ?? "manual",
      scheduleHour: scheduleHour ?? 0,
      scheduleDayOfWeek: scheduleDayOfWeek,
      symbols: symbols ?? ["BTCUSDT"],
      timeframe: timeframe ?? "1h",
      lookbackDays: lookbackDays ?? 30,
      initialCapital: String(initialCapital ?? 10000),
      enableFilters: enableFilters ?? true,
      strategies: strategies ?? ["trend_following"],
    });
  }

  return Response.json({ success: true });
}
