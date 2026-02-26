import type { LoaderFunctionArgs } from "react-router";
import { db } from "db";
import { eventTriggerLogs } from "db/schema";
import { desc, eq, and, gte, lte, count } from "drizzle-orm";

export async function loader({ request }: LoaderFunctionArgs) {
  const url = new URL(request.url);
  const symbol = url.searchParams.get("symbol");
  const eventType = url.searchParams.get("type");
  const severity = url.searchParams.get("severity");
  const from = url.searchParams.get("from");
  const to = url.searchParams.get("to");
  const page = parseInt(url.searchParams.get("page") || "1");
  const limit = parseInt(url.searchParams.get("limit") || "20");
  const offset = (page - 1) * limit;

  const conditions = [];
  if (symbol) conditions.push(eq(eventTriggerLogs.symbol, symbol));
  if (eventType) conditions.push(eq(eventTriggerLogs.eventType, eventType));
  if (severity) conditions.push(eq(eventTriggerLogs.severity, severity));
  if (from) conditions.push(gte(eventTriggerLogs.triggeredAt, new Date(from)));
  if (to) conditions.push(lte(eventTriggerLogs.triggeredAt, new Date(to)));

  const whereClause = conditions.length > 0 ? and(...conditions) : undefined;

  try {
    const [logs, totalResult] = await Promise.all([
      db.select().from(eventTriggerLogs)
        .where(whereClause)
        .orderBy(desc(eventTriggerLogs.triggeredAt))
        .limit(limit).offset(offset),
      db.select({ count: count() }).from(eventTriggerLogs).where(whereClause),
    ]);

    return Response.json({
      logs,
      total: Number(totalResult[0]?.count ?? 0),
      page,
      limit,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return Response.json({ error: message }, { status: 500 });
  }
}
