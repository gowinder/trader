import { Outlet } from "react-router";
import type { Route } from "./+types/dashboard";
import { requireAuth } from "~/services/auth.server";
import { Sidebar } from "~/components/layout/Sidebar";
import { Header } from "~/components/layout/Header";

export async function loader({ request }: Route.LoaderArgs) {
  await requireAuth(request);

  // TODO: 从数据库获取实时数据
  return {
    balance: 12345.67,
    symbol: "BTCUSDT",
    price: 98234.56,
    systemStatus: "running" as const,
  };
}

export default function DashboardLayout({ loaderData }: Route.ComponentProps) {
  const { balance, symbol, price, systemStatus } = loaderData;

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header
          balance={balance}
          symbol={symbol}
          price={price}
          systemStatus={systemStatus}
        />
        <main className="flex-1 overflow-auto bg-background p-4">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
