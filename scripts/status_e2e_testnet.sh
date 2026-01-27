#!/bin/bash
# Check E2E Testnet Trading System Status

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs"
PID_FILE="$LOG_DIR/e2e_testnet.pid"
LOG_FILE="$LOG_DIR/e2e_testnet.log"
DECISION_LOG="$LOG_DIR/e2e_testnet_decisions.log"

echo "=" * 80
echo "📊 E2E Testnet Trading System Status"
echo "=" * 80
echo ""

# Check if running
if [ ! -f "$PID_FILE" ]; then
    echo "Status: ❌ NOT RUNNING"
    echo ""
    exit 0
fi

PID=$(cat "$PID_FILE")

if ! ps -p $PID > /dev/null 2>&1; then
    echo "Status: ❌ NOT RUNNING (stale PID file)"
    rm "$PID_FILE"
    echo ""
    exit 0
fi

echo "Status: ✅ RUNNING"
echo "PID: $PID"
echo ""

# Show process info
echo "Process Info:"
ps -p $PID -o pid,etime,pcpu,pmem,command | tail -1
echo ""

# Show log file stats
if [ -f "$LOG_FILE" ]; then
    echo "Main Log:"
    echo "  File: $LOG_FILE"
    echo "  Size: $(du -h "$LOG_FILE" | cut -f1)"
    echo "  Lines: $(wc -l < "$LOG_FILE")"
    echo ""
    echo "Last 10 lines:"
    tail -10 "$LOG_FILE" | sed 's/^/  /'
    echo ""
fi

# Show decision log stats
if [ -f "$DECISION_LOG" ]; then
    echo "Decision Log:"
    echo "  File: $DECISION_LOG"
    echo "  Size: $(du -h "$DECISION_LOG" | cut -f1)"
    echo "  Decisions: $(grep -c "Trading Decision" "$DECISION_LOG" || echo "0")"
    echo ""
fi

echo "Commands:"
echo "  - View live logs:  tail -f $LOG_FILE"
echo "  - View decisions:  tail -f $DECISION_LOG"
echo "  - Stop:            ./scripts/stop_e2e_testnet.sh"
echo ""
