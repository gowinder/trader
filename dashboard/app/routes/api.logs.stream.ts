import { spawn } from "child_process";
import path from "path";
import fs from "fs";

export async function loader({ request }: { request: Request }) {
  const url = new URL(request.url);
  const lines = parseInt(url.searchParams.get("lines") || "100");

  // 日志文件路径 - 使用环境变量或默认路径
  let logFile = process.env.TRADER_LOG_FILE;
  if (!logFile) {
    // Docker 环境: /logs/trading.log
    // 开发环境: ../logs/trading.log
    const dockerPath = "/logs/trading.log";
    const devPath = path.resolve(process.cwd(), "..", "logs", "trading.log");
    logFile = fs.existsSync(dockerPath) ? dockerPath : devPath;
  }

  // 检查文件是否存在
  if (!fs.existsSync(logFile)) {
    return new Response(
      JSON.stringify({ error: `Log file not found: ${logFile}` }),
      { status: 404, headers: { "Content-Type": "application/json" } }
    );
  }

  const stream = new ReadableStream({
    start(controller) {
      const encoder = new TextEncoder();

      // 发送初始连接消息
      controller.enqueue(encoder.encode(`data: {"type":"connected"}\n\n`));

      // 使用 tail -f 监听日志文件
      const tail = spawn("tail", ["-n", String(lines), "-f", logFile]);

      tail.stdout.on("data", (data: Buffer) => {
        const text = data.toString();
        const logLines = text.split("\n").filter((line: string) => line.trim());

        for (const line of logLines) {
          const parsed = parseLogLine(line);
          controller.enqueue(
            encoder.encode(`data: ${JSON.stringify({ type: "log", ...parsed })}\n\n`)
          );
        }
      });

      tail.stderr.on("data", (data: Buffer) => {
        controller.enqueue(
          encoder.encode(`data: ${JSON.stringify({ type: "error", message: data.toString() })}\n\n`)
        );
      });

      tail.on("close", () => {
        controller.close();
      });

      // 处理客户端断开连接
      request.signal.addEventListener("abort", () => {
        tail.kill();
        controller.close();
      });
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      "Connection": "keep-alive",
    },
  });
}

function parseLogLine(line: string): { timestamp: string; level: string; module: string; message: string; raw: string } {
  // 解析 loguru 格式: 2026-01-31 19:50:25 | INFO     | ai_trader.scheduler:start:35 - Message
  const match = line.match(
    /^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s*\|\s*(\w+)\s*\|\s*([^-]+)\s*-\s*(.*)$/
  );

  if (match) {
    return {
      timestamp: match[1],
      level: match[2].trim(),
      module: match[3].trim(),
      message: match[4],
      raw: line,
    };
  }

  // 无法解析的行
  return {
    timestamp: "",
    level: "INFO",
    module: "",
    message: line,
    raw: line,
  };
}
