import { requireAuth } from "~/services/auth.server";
import { useEffect, useRef, useState, useCallback } from "react";
import { cn } from "~/lib/utils";
import { Button } from "~/components/ui/button";
import { Input } from "~/components/ui/input";
import { Pause, Play, Trash2, ArrowDown } from "lucide-react";

export async function loader({ request }: { request: Request }) {
  await requireAuth(request);
  return null;
}

interface LogEntry {
  timestamp: string;
  level: string;
  module: string;
  message: string;
  raw: string;
}

const levelColors: Record<string, string> = {
  DEBUG: "text-gray-400",
  INFO: "text-green-400",
  WARNING: "text-yellow-400",
  ERROR: "text-red-400",
  CRITICAL: "text-red-600 font-bold",
};

const levelBgColors: Record<string, string> = {
  DEBUG: "bg-gray-500/20",
  INFO: "bg-green-500/20",
  WARNING: "bg-yellow-500/20",
  ERROR: "bg-red-500/20",
  CRITICAL: "bg-red-600/30",
};

export default function LogsPage() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [isPaused, setIsPaused] = useState(false);
  const [filter, setFilter] = useState("");
  const [levelFilter, setLevelFilter] = useState<string>("ALL");
  const [autoScroll, setAutoScroll] = useState(true);
  const containerRef = useRef<HTMLDivElement>(null);
  const pendingLogsRef = useRef<LogEntry[]>([]);

  const scrollToBottom = useCallback(() => {
    if (containerRef.current && autoScroll) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [autoScroll]);

  useEffect(() => {
    const eventSource = new EventSource("/api/logs/stream?lines=200");

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.type === "log") {
        const entry: LogEntry = {
          timestamp: data.timestamp,
          level: data.level,
          module: data.module,
          message: data.message,
          raw: data.raw,
        };

        if (isPaused) {
          pendingLogsRef.current.push(entry);
        } else {
          setLogs((prev) => {
            const newLogs = [...prev, entry];
            if (newLogs.length > 1000) {
              return newLogs.slice(-800);
            }
            return newLogs;
          });
        }
      }
    };

    eventSource.onerror = () => {
      console.error("SSE connection error");
    };

    return () => {
      eventSource.close();
    };
  }, [isPaused]);

  useEffect(() => {
    scrollToBottom();
  }, [logs, scrollToBottom]);

  const handleResume = () => {
    setLogs((prev) => [...prev, ...pendingLogsRef.current]);
    pendingLogsRef.current = [];
    setIsPaused(false);
  };

  const handleClear = () => {
    setLogs([]);
    pendingLogsRef.current = [];
  };

  const filteredLogs = logs.filter((log) => {
    if (levelFilter !== "ALL" && log.level !== levelFilter) {
      return false;
    }
    if (filter) {
      const searchLower = filter.toLowerCase();
      return (
        log.message.toLowerCase().includes(searchLower) ||
        log.module.toLowerCase().includes(searchLower)
      );
    }
    return true;
  });

  return (
    <div className="h-[calc(100vh-8rem)]">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">系统日志</h1>
      </div>
      <div className="h-[calc(100%-3rem)] rounded-lg border overflow-hidden flex flex-col">
        {/* 工具栏 */}
        <div className="flex items-center gap-2 p-2 border-b bg-card">
          <Button
            variant={isPaused ? "default" : "secondary"}
            size="sm"
            onClick={() => (isPaused ? handleResume() : setIsPaused(true))}
          >
            {isPaused ? (
              <>
                <Play className="h-4 w-4 mr-1" />
                恢复 ({pendingLogsRef.current.length})
              </>
            ) : (
              <>
                <Pause className="h-4 w-4 mr-1" />
                暂停
              </>
            )}
          </Button>

          <Button variant="outline" size="sm" onClick={handleClear}>
            <Trash2 className="h-4 w-4 mr-1" />
            清空
          </Button>

          <Button
            variant={autoScroll ? "default" : "outline"}
            size="sm"
            onClick={() => setAutoScroll(!autoScroll)}
          >
            <ArrowDown className="h-4 w-4 mr-1" />
            自动滚动
          </Button>

          <div className="flex-1" />

          <select
            className="h-8 px-2 rounded border bg-background text-sm"
            value={levelFilter}
            onChange={(e) => setLevelFilter(e.target.value)}
          >
            <option value="ALL">全部级别</option>
            <option value="DEBUG">DEBUG</option>
            <option value="INFO">INFO</option>
            <option value="WARNING">WARNING</option>
            <option value="ERROR">ERROR</option>
          </select>

          <Input
            className="w-64 h-8"
            placeholder="搜索日志..."
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />

          <span className="text-sm text-muted-foreground">
            {filteredLogs.length} / {logs.length}
          </span>
        </div>

        {/* 日志内容 */}
        <div
          ref={containerRef}
          className="flex-1 overflow-auto bg-black/90 font-mono text-sm p-2"
        >
          {filteredLogs.length === 0 ? (
            <div className="text-gray-500 text-center py-8">
              等待日志...
            </div>
          ) : (
            filteredLogs.map((log, index) => (
              <div
                key={index}
                className={cn(
                  "py-0.5 px-1 hover:bg-white/5 rounded",
                  levelBgColors[log.level]
                )}
              >
                <span className="text-gray-500">{log.timestamp}</span>
                <span className={cn("mx-2 font-semibold", levelColors[log.level])}>
                  [{log.level.padEnd(8)}]
                </span>
                <span className="text-cyan-400">{log.module}</span>
                <span className="text-gray-400 mx-1">-</span>
                <span className="text-gray-200">{log.message}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
