#!/bin/bash
# Start E2E Testnet Trading System

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs"
PID_FILE="$LOG_DIR/e2e_testnet.pid"
LOG_FILE="$LOG_DIR/e2e_testnet.log"

# Create logs directory
mkdir -p "$LOG_DIR"

# Check if already running
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p $PID > /dev/null 2>&1; then
        echo "❌ E2E test is already running (PID: $PID)"
        echo "   Use ./scripts/stop_e2e_testnet.sh to stop it first"
        exit 1
    else
        echo "⚠️  Stale PID file found, removing..."
        rm "$PID_FILE"
    fi
fi

echo "🚀 Starting E2E Testnet Trading System..."
echo "   Log file: $LOG_FILE"
echo "   PID file: $PID_FILE"
echo ""

# Start the script in background
cd "$PROJECT_DIR"
nohup python scripts/run_e2e_testnet.py >> "$LOG_FILE" 2>&1 &
PID=$!

# Save PID
echo $PID > "$PID_FILE"

echo "✅ E2E test started (PID: $PID)"
echo ""
echo "Commands:"
echo "  - View logs:  tail -f $LOG_FILE"
echo "  - Stop:       ./scripts/stop_e2e_testnet.sh"
echo "  - Status:     ./scripts/status_e2e_testnet.sh"
echo ""
