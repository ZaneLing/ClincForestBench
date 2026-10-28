#!/usr/bin/env bash
# Double-click on macOS, or run ./deploy.command start|status|stop.
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
else
  PYTHON_BIN="${PYTHON:-python3}"
fi
exec "$PYTHON_BIN" "$ROOT_DIR/scripts/dev/local_deploy.py" "$@"
