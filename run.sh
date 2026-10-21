#!/usr/bin/env bash
# Monitor — arranque simple (sin venv, sin dependencias).
set -euo pipefail
cd "$(dirname "$0")"
exec python3 server.py --port "${MONITOR_PORT:-8770}" "$@"
