#!/bin/bash
# Stop E2E Testnet Trading System

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs"
PID_FILE="$LOG_DIR/e2e_testnet.pid"

if [ ! -f "$PID_FILE" ]; then
    echo "❌ E2E test is not running (no PID file found)"
    exit 1
fi

PID=$(cat "$PID_FILE")

if ! ps -p $PID > /dev/null 2>&1; then
    echo "❌ E2E test is not running (process not found)"
    rm "$PID_FILE"
    exit 1
fi

echo "🛑 Stopping E2E Testnet Trading System (PID: $PID)..."

kill $PID

# Wait for process to stop
for i in {1..10}; do
    if ! ps -p $PID > /dev/null 2>&1; then
        echo "✅ E2E test stopped successfully"
        rm "$PID_FILE"
        exit 0
    fi
    sleep 1
done

# Force kill if still running
if ps -p $PID > /dev/null 2>&1; then
    echo "⚠️  Process still running, forcing shutdown..."
    kill -9 $PID
    rm "$PID_FILE"
    echo "✅ E2E test force stopped"
fi
