#!/usr/bin/env bash
# Install Python + Node deps, build robot_manage static UI, run the web server.
# Ctrl+C / SIGTERM stops the server (trap + kill).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

export OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://192.168.1.228:11434}"
export OLLAMA_MODEL="${OLLAMA_MODEL:-gemma4:e4b-mlx}"
export OLLAMA_VOICE_SAY=1 

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck source=/dev/null
source .venv/bin/activate

pip install -r requirements.txt -r requirements-robot-manage.txt

WEB="$ROOT/robot_manage/web"
if [[ -f "$WEB/package-lock.json" ]]; then
  (cd "$WEB" && npm ci)
else
  (cd "$WEB" && npm install)
fi
(cd "$WEB" && npm run build)

GST_LIB="$(
  python -c 'import pathlib, site; p = pathlib.Path(site.getsitepackages()[0]) / "gstreamer_libs" / "lib"; print(p.resolve() if p.is_dir() else "")'
)"
if [[ -n "${GST_LIB}" ]]; then
  export DYLD_LIBRARY_PATH="${GST_LIB}${DYLD_LIBRARY_PATH:+:${DYLD_LIBRARY_PATH}}"
fi
unset DYLD_FALLBACK_LIBRARY_PATH || true

MANAGE_PID=""
cleanup() {
  if [[ -n "${MANAGE_PID}" ]] && kill -0 "${MANAGE_PID}" 2>/dev/null; then
    kill -TERM "${MANAGE_PID}" 2>/dev/null || true
    wait "${MANAGE_PID}" 2>/dev/null || true
  fi
  MANAGE_PID=""
}
trap cleanup EXIT INT TERM HUP

# Default bind is 0.0.0.0 (LAN). Pass --bind 127.0.0.1 before "$@" for localhost only.
python -m robot_manage "$@" &
MANAGE_PID=$!
wait "${MANAGE_PID}"
MANAGE_EXIT=$?
exit "${MANAGE_EXIT}"
