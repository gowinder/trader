import { NavLink } from "react-router";
import { cn } from "~/lib/utils";
import {
  LayoutDashboard,
  LineChart,
  FileText,
  History,
  BarChart3,
  FlaskConical,
  Settings,
  Bell,
  Power,
} from "lucide-react";

const navItems = [
  { to: "/dashboard", icon: LayoutDashboard, label: "概览" },
  { to: "/dashboard/chart", icon: LineChart, label: "图表" },
  { to: "/dashboard/decisions", icon: FileText, label: "决策" },
  { to: "/dashboard/positions", icon: History, label: "仓位" },
  { to: "/dashboard/analytics", icon: BarChart3, label: "分析" },
  { to: "/dashboard/backtest", icon: FlaskConical, label: "回测" },
];

const bottomItems = [
  { to: "/dashboard/alerts", icon: Bell, label: "告警" },
  { to: "/dashboard/control", icon: Power, label: "控制" },
  { to: "/dashboard/settings", icon: Settings, label: "设置" },
];

export function Sidebar() {
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
