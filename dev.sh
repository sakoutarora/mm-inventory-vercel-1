#!/usr/bin/env bash
set -euo pipefail

# Start backend API (Lambda local server)
echo "Starting backend on http://localhost:8000 ..."
(cd api && python3 local_server.py) &
BACKEND_PID=$!

# Start frontend console (Vite dev server)
echo "Starting frontend on http://localhost:5174 ..."
(cd console && npm run dev) &
FRONTEND_PID=$!

# Kill both on exit
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT INT TERM

echo ""
echo "  Backend:  http://localhost:8000"
echo "  Frontend: http://localhost:5174"
echo ""
echo "Press Ctrl+C to stop both."

wait
