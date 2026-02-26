import { useEffect, useState, useCallback } from "react";
import { NavLink } from "react-router";
import { cn } from "~/lib/utils";
import {
  LayoutDashboard,
  LineChart,
  FileText,
  History,
  BarChart3,
  FlaskConical,
  SlidersHorizontal,
  Layers,
  Settings,
  Bell,
  Power,
  ScrollText,
  Cpu,
  BrainCircuit,
  SlidersVertical,
  MessageSquare,
  Zap,
} from "lucide-react";

const navItems = [
  { to: "/dashboard", icon: LayoutDashboard, label: "概览" },
  { to: "/dashboard/chart", icon: LineChart, label: "图表" },
  { to: "/dashboard/decisions", icon: FileText, label: "决策" },
  { to: "/dashboard/event-triggers", icon: Zap, label: "事件触发" },
  { to: "/dashboard/positions", icon: History, label: "仓位" },
  { to: "/dashboard/analytics", icon: BarChart3, label: "分析" },
  { to: "/dashboard/llm-usage", icon: Cpu, label: "LLM" },
  { to: "/dashboard/backtest", icon: FlaskConical, label: "回测" },
  { to: "/dashboard/backtest-settings", icon: SlidersHorizontal, label: "回测设置" },
  { to: "/dashboard/strategy", icon: Layers, label: "策略" },
];

const advisoryItems = [
  { to: "/dashboard/advisory", icon: BrainCircuit, label: "AI 建议", hasBadge: true },
  { to: "/dashboard/advisory-settings", icon: SlidersVertical, label: "建议设置", hasBadge: false },
  { to: "/dashboard/notification-settings", icon: MessageSquare, label: "通知设置", hasBadge: false },
];

const bottomItems = [
  { to: "/dashboard/logs", icon: ScrollText, label: "日志" },
  { to: "/dashboard/alerts", icon: Bell, label: "告警" },
  { to: "/dashboard/control", icon: Power, label: "控制" },
  { to: "/dashboard/settings", icon: Settings, label: "设置" },
];

function useAdvisoryPendingCount() {
  const [pendingCount, setPendingCount] = useState(0);

  const fetchPendingCount = useCallback(async () => {
    try {
      const res = await fetch("/api/advisory?status=pending");
      if (res.ok) {
        const data = await res.json();
        setPendingCount(data.pendingCount ?? 0);
      }
    } catch {
      // silently ignore fetch errors
    }
  }, []);

  useEffect(() => {
    fetchPendingCount();
    const interval = setInterval(fetchPendingCount, 60_000);
    return () => clearInterval(interval);
  }, [fetchPendingCount]);

  return pendingCount;
}

function PendingBadge({ count }: { count: number }) {
  if (count <= 0) return null;
  return (
    <span className="ml-auto flex h-5 min-w-5 items-center justify-center rounded-full bg-red-500 px-1.5 text-[10px] font-bold text-white">
      {count > 99 ? "99+" : count}
    </span>
  );
}

export function Sidebar() {
  const pendingCount = useAdvisoryPendingCount();

  return (
    <aside className="flex h-screen w-16 flex-col border-r bg-card lg:w-56">
      {/* Logo */}
      <div className="flex h-14 items-center justify-center border-b lg:justify-start lg:px-4">
        <span className="text-xl font-bold text-primary">T</span>
        <span className="hidden text-lg font-semibold lg:inline">rader</span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 p-2">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/dashboard"}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                "hover:bg-accent hover:text-accent-foreground",
                isActive
                  ? "bg-accent text-accent-foreground"
                  : "text-muted-foreground"
              )
            }
          >
            <item.icon className="h-5 w-5 shrink-0" />
            <span className="hidden lg:inline">{item.label}</span>
          </NavLink>
        ))}

        {/* Advisory Section */}
        <div className="my-2 border-t pt-2">
          {advisoryItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  "hover:bg-accent hover:text-accent-foreground",
                  isActive
                    ? "bg-accent text-accent-foreground"
                    : "text-muted-foreground"
                )
              }
            >
              <item.icon className="h-5 w-5 shrink-0" />
              <span className="hidden lg:inline">{item.label}</span>
              {item.hasBadge && <PendingBadge count={pendingCount} />}
            </NavLink>
          ))}
        </div>
      </nav>

      {/* Bottom Navigation */}
      <div className="border-t p-2">
        {bottomItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                "hover:bg-accent hover:text-accent-foreground",
                isActive
                  ? "bg-accent text-accent-foreground"
                  : "text-muted-foreground"
              )
            }
          >
            <item.icon className="h-5 w-5 shrink-0" />
            <span className="hidden lg:inline">{item.label}</span>
          </NavLink>
        ))}
      </div>
    </aside>
  );
}
