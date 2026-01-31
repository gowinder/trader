import { cn, getPnlColorClass } from "~/lib/utils";
import { Card, CardContent } from "~/components/ui/card";
import type { LucideIcon } from "lucide-react";

interface StatCardProps {
  label: string;
  value: string | number;
  icon?: LucideIcon;
  change?: number;
  variant?: "default" | "profit" | "loss";
  className?: string;
}

export function StatCard({
  label,
  value,
  icon: Icon,
  change,
  variant = "default",
  className,
}: StatCardProps) {
  return (
    <Card className={cn("", className)}>
      <CardContent className="p-4">
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">{label}</p>
          {Icon && <Icon className="h-4 w-4 text-muted-foreground" />}
        </div>
        <p
          className={cn(
            "mt-2 text-2xl font-bold tabular-nums",
            variant === "profit" && "text-profit",
            variant === "loss" && "text-loss"
          )}
        >
          {value}
        </p>
        {change !== undefined && (
          <p className={cn("mt-1 text-xs", getPnlColorClass(change))}>
            {change > 0 ? "+" : ""}
            {change.toFixed(2)}%
          </p>
        )}
      </CardContent>
    </Card>
  );
}
