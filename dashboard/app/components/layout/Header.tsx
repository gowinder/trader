import { Form } from "react-router";
import { Button } from "~/components/ui/button";
import { LogOut, Activity } from "lucide-react";
import { formatUSD } from "~/lib/utils";

interface HeaderProps {
  balance?: number;
  symbol?: string;
  price?: number;
  systemStatus?: "running" | "paused" | "error";
}

export function Header({ balance, symbol, price, systemStatus = "running" }: HeaderProps) {
  const statusColor = {
    running: "bg-green-500",
    paused: "bg-yellow-500",
    error: "bg-red-500",
  };

  const statusText = {
    running: "运行中",
    paused: "已暂停",
    error: "异常",
  };

  return (
    <header className="flex h-14 items-center justify-between border-b bg-card px-4">
      <div className="flex items-center gap-6">
        {/* Symbol & Price */}
        {symbol && price && (
          <div className="flex items-center gap-2">
            <span className="font-medium">{symbol}</span>
            <span className="text-lg font-bold tabular-nums">{formatUSD(price)}</span>
          </div>
        )}
      </div>

      <div className="flex items-center gap-4">
        {/* Balance */}
        {balance !== undefined && (
          <div className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">账户:</span>
            <span className="font-medium tabular-nums">{formatUSD(balance)}</span>
          </div>
        )}

        {/* System Status */}
        <div className="flex items-center gap-2">
          <div className={`h-2 w-2 rounded-full ${statusColor[systemStatus]}`} />
          <span className="text-sm text-muted-foreground">{statusText[systemStatus]}</span>
        </div>

        {/* Activity Indicator */}
        <Activity className="h-4 w-4 text-muted-foreground" />

        {/* Logout */}
        <Form method="post" action="/logout">
          <Button variant="ghost" size="icon" type="submit" title="退出登录">
            <LogOut className="h-4 w-4" />
          </Button>
        </Form>
      </div>
    </header>
  );
}
