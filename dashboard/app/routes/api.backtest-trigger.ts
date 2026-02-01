import type { ActionFunctionArgs } from "react-router";
import { spawn } from "child_process";
import path from "path";

export async function action({ request }: ActionFunctionArgs) {
  if (request.method !== "POST") {
    return Response.json({ error: "Method not allowed" }, { status: 405 });
  }

  const body = await request.json();
  const {
    symbol = "BTCUSDT",
    startDate,
    endDate,
    interval = "1h",
    capital = 10000,
  } = body;

  // 验证日期
  if (!startDate || !endDate) {
    return Response.json({ error: "startDate and endDate are required" }, { status: 400 });
  }

  // 构建命令参数 - 使用现有的 run_backtest.py 脚本
  const args = [
    "scripts/run_backtest.py",
    "--symbol", symbol,
    "--start", startDate,
    "--end", endDate,
    "--interval", interval,
    "--capital", String(capital),
    "--save-to-db",
  ];

  // 获取 Python 路径 (容器内或本地)
  const pythonPath = process.env.PYTHON_PATH || "python";

  try {
    // 异步启动回测进程
    const proc = spawn(pythonPath, args, {
      cwd: path.resolve(process.cwd(), ".."),
      detached: true,
      stdio: "ignore",
    });

    proc.unref();

    return Response.json({
      success: true,
      message: "Backtest started",
      pid: proc.pid,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return Response.json({ error: message }, { status: 500 });
  }
}
