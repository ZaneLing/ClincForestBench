#!/usr/bin/env bash
# Start the local API and web application as one managed process.
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOST="127.0.0.1"
API_PORT="8000"
WEB_PORT="3000"
OPEN_BROWSER=1
AUTO_INSTALL=1
STARTUP_TIMEOUT=120

usage() {
  cat <<'EOF'
Usage: ./start.command [options]

Start the ClincForestBench API and web UI together. Missing local dependencies
are installed automatically, the browser opens when both services are ready,
and Ctrl-C stops both services.

Options:
  --host HOST          Bind address (default: 127.0.0.1)
  --api-port PORT      API port (default: 8000)
  --web-port PORT      Web port (default: 3000)
  --no-open            Do not open a browser
  --no-install         Fail instead of installing missing dependencies
  --timeout SECONDS    Startup timeout (default: 120)
  -h, --help           Show this help

Environment variables with the same purpose are also supported:
CFB_HOST, CFB_API_PORT, CFB_WEB_PORT, CFB_OPEN_BROWSER, CFB_AUTO_INSTALL,
and CFB_STARTUP_TIMEOUT.
EOF
}

HOST="${CFB_HOST:-$HOST}"
API_PORT="${CFB_API_PORT:-$API_PORT}"
WEB_PORT="${CFB_WEB_PORT:-$WEB_PORT}"
OPEN_BROWSER="${CFB_OPEN_BROWSER:-$OPEN_BROWSER}"
AUTO_INSTALL="${CFB_AUTO_INSTALL:-$AUTO_INSTALL}"
STARTUP_TIMEOUT="${CFB_STARTUP_TIMEOUT:-$STARTUP_TIMEOUT}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      [[ $# -ge 2 ]] || { echo "Missing value for --host" >&2; exit 2; }
      HOST="$2"
      shift 2
      ;;
    --api-port)
      [[ $# -ge 2 ]] || { echo "Missing value for --api-port" >&2; exit 2; }
      API_PORT="$2"
      shift 2
      ;;
    --web-port)
      [[ $# -ge 2 ]] || { echo "Missing value for --web-port" >&2; exit 2; }
      WEB_PORT="$2"
      shift 2
      ;;
    --timeout)
      [[ $# -ge 2 ]] || { echo "Missing value for --timeout" >&2; exit 2; }
      STARTUP_TIMEOUT="$2"
      shift 2
      ;;
    --no-open)
      OPEN_BROWSER=0
      shift
      ;;
    --no-install)
      AUTO_INSTALL=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

for value in "$API_PORT" "$WEB_PORT" "$STARTUP_TIMEOUT"; do
  [[ "$value" =~ ^[0-9]+$ ]] || {
    echo "Ports and timeout must be positive integers." >&2
    exit 2
  }
done
[[ "$API_PORT" -ge 1 && "$API_PORT" -le 65535 ]] || {
  echo "Invalid API port: $API_PORT" >&2
  exit 2
}
[[ "$WEB_PORT" -ge 1 && "$WEB_PORT" -le 65535 ]] || {
  echo "Invalid web port: $WEB_PORT" >&2
  exit 2
}
[[ "$API_PORT" != "$WEB_PORT" ]] || {
  echo "API and web ports must be different." >&2
  exit 2
}
[[ "$STARTUP_TIMEOUT" -ge 1 ]] || {
  echo "Startup timeout must be at least one second." >&2
  exit 2
}

cd "$ROOT_DIR"

command -v curl >/dev/null 2>&1 || {
  echo "curl is required for service health checks." >&2
  exit 1
}

install_python_dependencies() {
  local bootstrap_python
  bootstrap_python="${PYTHON:-python3}"
  command -v "$bootstrap_python" >/dev/null 2>&1 || {
    echo "Python 3.9+ is required (tried: $bootstrap_python)." >&2
    exit 1
  }
  echo "[setup] Creating the Python environment..."
  "$bootstrap_python" -m venv .venv
  .venv/bin/python -m pip install --upgrade pip setuptools wheel
  .venv/bin/python -m pip install -e '.[dev]'
}

if [[ ! -x .venv/bin/python ]] || ! .venv/bin/python -c 'import uvicorn, sqlalchemy' >/dev/null 2>&1; then
  if [[ "$AUTO_INSTALL" != "1" ]]; then
    echo "Python dependencies are missing. Run 'make venv' or omit --no-install." >&2
    exit 1
  fi
  install_python_dependencies
fi

NODE_BIN_DIR=""
if [[ -x .tools/node/bin/node && -x .tools/node/bin/npm ]]; then
  NODE_BIN_DIR="$ROOT_DIR/.tools/node/bin"
elif command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; then
  NODE_BIN_DIR="$(dirname "$(command -v node)")"
elif [[ "$AUTO_INSTALL" == "1" && "$(uname -s)" == "Darwin" ]]; then
  echo "[setup] Installing the project-local Node runtime..."
  bash scripts/dev/bootstrap_node.sh
  NODE_BIN_DIR="$ROOT_DIR/.tools/node/bin"
else
  echo "Node 22.13+ and npm are required. On macOS, omit --no-install to install them." >&2
  exit 1
fi

export PATH="$NODE_BIN_DIR:$PATH"
node -e '
  const [major, minor] = process.versions.node.split(".").map(Number);
  if (major < 22 || (major === 22 && minor < 13)) process.exit(1);
' || {
  echo "Node 22.13+ is required; found $(node --version)." >&2
  exit 1
}

if [[ ! -d frontend/node_modules ]] || ! (cd frontend && npm ls --depth=0 --silent >/dev/null 2>&1); then
  if [[ "$AUTO_INSTALL" != "1" ]]; then
    echo "Frontend dependencies are missing. Run 'make frontend-install' or omit --no-install." >&2
    exit 1
  fi
  echo "[setup] Installing frontend dependencies..."
  (cd frontend && npm ci)
fi

CONNECT_HOST="$HOST"
case "$CONNECT_HOST" in
  0.0.0.0|::) CONNECT_HOST="127.0.0.1" ;;
esac
API_URL="http://${CONNECT_HOST}:${API_PORT}"
WEB_URL="http://${CONNECT_HOST}:${WEB_PORT}"

port_is_open() {
  .venv/bin/python - "$CONNECT_HOST" "$1" <<'PY'
import socket
import sys

try:
    with socket.create_connection((sys.argv[1], int(sys.argv[2])), timeout=0.25):
        raise SystemExit(0)
except OSError:
    raise SystemExit(1)
PY
}

for port in "$API_PORT" "$WEB_PORT"; do
  if port_is_open "$port"; then
    echo "Port $port is already in use. Choose another port and try again." >&2
    exit 1
  fi
done

RUN_DIR="${CFB_RUN_DIR:-$ROOT_DIR/.run}"
mkdir -p "$RUN_DIR"
API_LOG="$RUN_DIR/api.log"
WEB_LOG="$RUN_DIR/web.log"
: >"$API_LOG"
: >"$WEB_LOG"

API_PID=""
WEB_PID=""
TAIL_PID=""

stop_process() {
  local pid="$1"
  [[ -n "$pid" ]] || return 0
  kill -0 "$pid" 2>/dev/null || return 0
  pkill -TERM -P "$pid" 2>/dev/null || true
  kill -TERM "$pid" 2>/dev/null || true
}

cleanup() {
  local status=$?
  trap - EXIT INT TERM
  [[ -n "$TAIL_PID" ]] && kill "$TAIL_PID" 2>/dev/null || true
  stop_process "$WEB_PID"
  stop_process "$API_PID"
  wait "$WEB_PID" 2>/dev/null || true
  wait "$API_PID" 2>/dev/null || true
  if [[ -n "$API_PID" || -n "$WEB_PID" ]]; then
    echo
    echo "ClincForestBench stopped."
  fi
  exit "$status"
}

trap cleanup EXIT
trap 'exit 130' INT TERM

echo "[start] API -> $API_URL"
(
  cd "$ROOT_DIR"
  exec env \
    ARENA_REPOSITORY="${ARENA_REPOSITORY:-sqlite}" \
    DATABASE_URL="${DATABASE_URL:-sqlite:///data/clincforestbench.db}" \
    .venv/bin/python -m uvicorn backend.app.main:app \
      --reload --host "$HOST" --port "$API_PORT"
) >>"$API_LOG" 2>&1 &
API_PID=$!

echo "[start] Web -> $WEB_URL"
(
  cd "$ROOT_DIR/frontend"
  exec env NEXT_PUBLIC_API_BASE_URL="$API_URL" \
    npm run dev -- --hostname "$HOST" --port "$WEB_PORT"
) >>"$WEB_LOG" 2>&1 &
WEB_PID=$!

wait_until_ready() {
  local name="$1"
  local url="$2"
  local pid="$3"
  local log_file="$4"
  local elapsed=0

  while [[ "$elapsed" -lt "$STARTUP_TIMEOUT" ]]; do
    if curl --silent --fail --max-time 2 "$url" >/dev/null 2>&1; then
      echo "[ready] $name"
      return 0
    fi
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "$name exited during startup. Recent log output:" >&2
      tail -n 40 "$log_file" >&2
      return 1
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done

  echo "$name did not become ready within ${STARTUP_TIMEOUT}s. Recent log output:" >&2
  tail -n 40 "$log_file" >&2
  return 1
}

wait_until_ready "API" "$API_URL/health" "$API_PID" "$API_LOG"
wait_until_ready "Web" "$WEB_URL" "$WEB_PID" "$WEB_LOG"

if [[ "$OPEN_BROWSER" == "1" ]]; then
  if command -v open >/dev/null 2>&1; then
    open "$WEB_URL" >/dev/null 2>&1 || true
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$WEB_URL" >/dev/null 2>&1 || true
  else
    echo "Open $WEB_URL in your browser."
  fi
fi

echo
echo "ClincForestBench is running at $WEB_URL"
echo "API documentation: $API_URL/docs"
echo "Logs: $API_LOG and $WEB_LOG"
echo "Press Ctrl-C to stop both services."
echo

if [[ "${CFB_TAIL_LOGS:-1}" == "1" ]]; then
  tail -n 20 -F "$API_LOG" "$WEB_LOG" &
  TAIL_PID=$!
fi

while kill -0 "$API_PID" 2>/dev/null && kill -0 "$WEB_PID" 2>/dev/null; do
  sleep 1
done

echo "A service exited unexpectedly. Recent logs:" >&2
tail -n 40 "$API_LOG" >&2
tail -n 40 "$WEB_LOG" >&2
exit 1
