import { useState, useEffect, useCallback } from "react";
import { useFetcher } from "react-router";
import { Card, CardContent } from "~/components/ui/card";
import { Button } from "~/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select";
import { cn, formatDateTime, formatTimeAgo } from "~/lib/utils";
import {
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  TrendingUp,
  Shield,
  Settings,
  RefreshCw,
  Check,
  X,
  Loader2,
} from "lucide-react";

interface Suggestion {
  id: string;
  type: string;
  target: string;
  action: string;
  detail: string | null;
  reasoning: string | null;
  risk_note: string | null;
  status: string;
  execution_result: string | null;
  rejection_reason: string | null;
}

interface Advisory {
  id: string;
  trigger_type: string;
  urgency: string;
  market_summary: string;
  status: string;
  created_at: string;
  resolved_at: string | null;
  suggestions: Suggestion[];
}

const urgencyConfig: Record<string, { label: string; color: string; bg: string }> = {
  high: { label: "高", color: "text-red-600 dark:text-red-400", bg: "bg-red-100 dark:bg-red-900/30" },
  medium: { label: "中", color: "text-yellow-600 dark:text-yellow-400", bg: "bg-yellow-100 dark:bg-yellow-900/30" },
  low: { label: "低", color: "text-green-600 dark:text-green-400", bg: "bg-green-100 dark:bg-green-900/30" },
};

const triggerTypeMap: Record<string, string> = {
  periodic: "定时分析",
  price_alert: "价格预警",
  risk_alert: "风险预警",
  news_event: "新闻事件",
  manual: "手动触发",
};

const suggestionTypeIcon: Record<string, typeof TrendingUp> = {
  trade: TrendingUp,
  risk: Shield,
  config: Settings,
  alert: AlertTriangle,
};

const statusMap: Record<string, { label: string; color: string }> = {
  pending: { label: "待处理", color: "text-yellow-600 dark:text-yellow-400" },
  accepted: { label: "已采纳", color: "text-blue-600 dark:text-blue-400" },
  rejected: { label: "已拒绝", color: "text-muted-foreground" },
  confirmed: { label: "已确认", color: "text-purple-600 dark:text-purple-400" },
  executed: { label: "已执行", color: "text-green-600 dark:text-green-400" },
  failed: { label: "执行失败", color: "text-red-600 dark:text-red-400" },
};

export default function AdvisoryPage() {
  const [advisories, setAdvisories] = useState<Advisory[]>([]);
  const [pendingCount, setPendingCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("pending");
  const [urgencyFilter, setUrgencyFilter] = useState("all");
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [rejectingId, setRejectingId] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState("");

  const fetcher = useFetcher();

  const fetchData = useCallback(async () => {
    try {
      const res = await fetch(`/api/advisory?status=${statusFilter}&limit=50`);
      const data = await res.json();
      if (data.advisories) {
        setAdvisories(data.advisories);
        setPendingCount(data.pendingCount ?? 0);
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    setLoading(true);
    fetchData();
  }, [fetchData]);

  // Auto-refresh every 30s
  useEffect(() => {
    const timer = setInterval(fetchData, 30000);
    return () => clearInterval(timer);
  }, [fetchData]);

  // Refresh after action completes
  useEffect(() => {
    if (fetcher.state === "idle" && fetcher.data) {
      fetchData();
    }
  }, [fetcher.state, fetcher.data, fetchData]);

  const toggleExpand = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleAction = (suggestionId: string, action: string, rejectionReason?: string) => {
    fetcher.submit(
      JSON.stringify({ suggestionId, action, rejectionReason }),
      {
        method: "POST",
        action: "/api/advisory-action",
        encType: "application/json",
      }
    );
    setRejectingId(null);
    setRejectReason("");
  };

  const filtered = urgencyFilter === "all"
    ? advisories
    : advisories.filter((a) => a.urgency === urgencyFilter);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold">AI 建议</h1>
          {pendingCount > 0 && (
            <span className="rounded-full bg-red-500 px-2.5 py-0.5 text-xs font-medium text-white">
              {pendingCount} 待处理
            </span>
          )}
        </div>
        <Button variant="ghost" size="sm" onClick={() => { setLoading(true); fetchData(); }}>
          <RefreshCw className={cn("mr-1 h-4 w-4", loading && "animate-spin")} />
          刷新
        </Button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-[130px]">
            <SelectValue placeholder="状态" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="pending">待处理</SelectItem>
            <SelectItem value="resolved">已解决</SelectItem>
            <SelectItem value="all">全部</SelectItem>
          </SelectContent>
        </Select>

        <Select value={urgencyFilter} onValueChange={setUrgencyFilter}>
          <SelectTrigger className="w-[130px]">
            <SelectValue placeholder="紧急程度" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部</SelectItem>
            <SelectItem value="high">高</SelectItem>
            <SelectItem value="medium">中</SelectItem>
            <SelectItem value="low">低</SelectItem>
          </SelectContent>
        </Select>

        <span className="text-sm text-muted-foreground">
          共 {filtered.length} 条
        </span>
      </div>

      {/* Advisory List */}
      {loading && advisories.length === 0 ? (
        <Card>
          <CardContent className="flex items-center justify-center py-12">
            <Loader2 className="mr-2 h-5 w-5 animate-spin text-muted-foreground" />
            <span className="text-muted-foreground">加载中...</span>
          </CardContent>
        </Card>
      ) : filtered.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            暂无数据
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {filtered.map((advisory) => {
            const expanded = expandedIds.has(advisory.id);
            const uc = urgencyConfig[advisory.urgency] || urgencyConfig.low;

            return (
              <Card key={advisory.id} className="overflow-hidden">
                <CardContent className="p-0">
                  {/* Header row */}
                  <button
                    className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/50"
                    onClick={() => toggleExpand(advisory.id)}
                  >
                    <span className={cn("rounded px-2 py-0.5 text-xs font-semibold", uc.color, uc.bg)}>
                      {uc.label}
                    </span>
                    <span className="rounded bg-muted px-2 py-0.5 text-xs">
                      {triggerTypeMap[advisory.trigger_type] || advisory.trigger_type}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-sm">
                      {advisory.market_summary}
                    </span>
                    <span className="shrink-0 text-xs text-muted-foreground" title={formatDateTime(advisory.created_at)}>
                      {formatTimeAgo(advisory.created_at)}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {advisory.suggestions.length} 条建议
                    </span>
                    {expanded ? (
                      <ChevronUp className="h-4 w-4 shrink-0 text-muted-foreground" />
                    ) : (
                      <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
                    )}
                  </button>

                  {/* Expanded suggestions */}
                  {expanded && (
                    <div className="border-t">
                      {advisory.suggestions.length === 0 ? (
                        <div className="px-4 py-4 text-sm text-muted-foreground">
                          无建议
                        </div>
                      ) : (
                        advisory.suggestions.map((s) => {
                          const Icon = suggestionTypeIcon[s.type] || AlertTriangle;
                          const st = statusMap[s.status] || statusMap.pending;
                          const isActioning = fetcher.state !== "idle";

                          return (
                            <div key={s.id} className="border-b px-4 py-3 last:border-b-0">
                              <div className="flex items-start gap-3">
                                <Icon className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                                <div className="min-w-0 flex-1 space-y-1">
                                  <div className="flex flex-wrap items-center gap-2">
                                    <span className="text-sm font-medium">{s.target}</span>
                                    <span className="rounded bg-muted px-1.5 py-0.5 text-xs">
                                      {s.action}
                                    </span>
                                    <span className={cn("text-xs font-medium", st.color)}>
                                      {st.label}
                                    </span>
                                  </div>
                                  {s.detail && (
                                    <p className="text-sm text-muted-foreground">{s.detail}</p>
                                  )}
                                  {s.reasoning && (
                                    <p className="text-sm">{s.reasoning}</p>
                                  )}
                                  {s.risk_note && (
                                    <p className="text-xs text-yellow-600 dark:text-yellow-400">
                                      <AlertTriangle className="mr-1 inline h-3 w-3" />
                                      {s.risk_note}
                                    </p>
                                  )}
                                  {s.execution_result && (
                                    <p className={cn(
                                      "text-xs",
                                      s.status === "executed" ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"
                                    )}>
                                      结果: {s.execution_result}
                                    </p>
                                  )}
                                  {s.rejection_reason && (
                                    <p className="text-xs text-muted-foreground">
                                      拒绝原因: {s.rejection_reason}
                                    </p>
                                  )}

                                  {/* Action buttons */}
                                  {s.status === "pending" && (
                                    <div className="flex items-center gap-2 pt-1">
                                      <Button
                                        size="sm"
                                        variant="default"
                                        disabled={isActioning}
                                        onClick={() => handleAction(s.id, "accept")}
                                      >
                                        <Check className="mr-1 h-3 w-3" />
                                        采纳
                                      </Button>
                                      {rejectingId === s.id ? (
                                        <div className="flex items-center gap-2">
                                          <input
                                            type="text"
                                            className="h-8 rounded border bg-background px-2 text-sm"
                                            placeholder="拒绝原因（可选）"
                                            value={rejectReason}
                                            onChange={(e) => setRejectReason(e.target.value)}
                                            onKeyDown={(e) => {
                                              if (e.key === "Enter") handleAction(s.id, "reject", rejectReason);
                                            }}
                                          />
                                          <Button
                                            size="sm"
                                            variant="destructive"
                                            disabled={isActioning}
                                            onClick={() => handleAction(s.id, "reject", rejectReason)}
                                          >
                                            确认拒绝
                                          </Button>
                                          <Button
                                            size="sm"
                                            variant="ghost"
                                            onClick={() => { setRejectingId(null); setRejectReason(""); }}
                                          >
                                            取消
                                          </Button>
                                        </div>
                                      ) : (
                                        <Button
                                          size="sm"
                                          variant="outline"
                                          disabled={isActioning}
                                          onClick={() => setRejectingId(s.id)}
                                        >
                                          <X className="mr-1 h-3 w-3" />
                                          拒绝
                                        </Button>
                                      )}
                                    </div>
                                  )}

                                  {s.status === "accepted" && (
                                    <div className="flex items-center gap-2 pt-1">
                                      <Button
                                        size="sm"
                                        variant="default"
                                        disabled={isActioning}
                                        onClick={() => handleAction(s.id, "confirm")}
                                      >
                                        确认执行
                                      </Button>
                                      <Button
                                        size="sm"
                                        variant="outline"
                                        disabled={isActioning}
                                        onClick={() => handleAction(s.id, "reject")}
                                      >
                                        取消
                                      </Button>
                                    </div>
                                  )}
                                </div>
                              </div>
                            </div>
                          );
                        })
                      )}
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
