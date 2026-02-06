#!/bin/bash
# 同时启动 AI Trader 和 Dashboard

cd "$(dirname "$0")/.."
PROJECT_ROOT=$(pwd)

# 清理函数
cleanup() {
    echo "Stopping all services..."
    kill $TRADER_PID $DASHBOARD_PID 2>/dev/null
    wait
    exit 0
}

trap cleanup SIGINT SIGTERM

# 启动 AI Trader
echo "Starting AI Trader..."
cd "$PROJECT_ROOT"
source .venv/bin/activate
PYTHONPATH="$PROJECT_ROOT/src" python -m ai_trader.main &
TRADER_PID=$!
echo "AI Trader PID: $TRADER_PID"

# 启动 Dashboard
echo "Starting Dashboard..."
cd "$PROJECT_ROOT/dashboard"
npm run dev &
DASHBOARD_PID=$!
echo "Dashboard PID: $DASHBOARD_PID"

echo ""
echo "==================================="
echo "Services running:"
echo "  AI Trader: PID $TRADER_PID"
echo "  Dashboard:  PID $DASHBOARD_PID (http://localhost:5173)"
echo "==================================="
echo "Press Ctrl+C to stop all services"

# 等待进程
wait
