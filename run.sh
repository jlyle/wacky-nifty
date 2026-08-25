#!/usr/bin/env bash
set -euo pipefail

PORT=5050
LOG_FILE=app.log

if python3 -c "
import socket, sys
s = socket.socket()
s.settimeout(1)
sys.exit(0 if s.connect_ex(('127.0.0.1', $PORT)) == 0 else 1)
"; then
    echo "Error: something is already listening on port $PORT (is the app already running?)" >&2
    exit 1
fi

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

nohup python3 app.py > "$LOG_FILE" 2>&1 &
APP_PID=$!
disown

sleep 1
if ! kill -0 "$APP_PID" 2>/dev/null; then
    echo "Error: app.py failed to start. Last lines of $LOG_FILE:" >&2
    tail -n 20 "$LOG_FILE" >&2 || true
    exit 1
fi

echo "Wacky Nifty running at http://localhost:$PORT (pid $APP_PID). Logs: $LOG_FILE"
