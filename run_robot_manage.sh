#!/usr/bin/env bash
# Install Python + Node deps, build robot_manage static UI, run the web server.
# Ctrl+C / SIGTERM stops the server (trap + kill).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
export ROBOT_HOST=192.168.1.191
export OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://192.168.1.228:11434}"
export OLLAMA_MODEL="${OLLAMA_MODEL:-gemma4:e4b-mlx}"
export OLLAMA_VOICE_SAY=1 
export OLLAMA_VOICE_SAY_TARGET="${OLLAMA_VOICE_SAY_TARGET:-reachy}"
# Optional: OLLAMA_VOICE_JSON_MOVES=1 — legacy JSON speech+move; default plain text TTS (see pollen-robotics/reachy_mini_conversation_app for tool-queued motion).
export ROBOT_MANAGE_REACTION_MOVES="${ROBOT_MANAGE_REACTION_MOVES:-1}"
# Optional: Apple Silicon host only — converted YOLO26 weights for yolo-mlx ByteTrack + UI overlay:
export ROBOT_MANAGE_YOLO_NPZ="$HOME/models/yolo26n.npz"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck source=/dev/null
source .venv/bin/activate

pip install -r requirements.txt -r requirements-robot-manage.txt
if [[ -f requirements-robot-manage-mlx.txt ]]; then
  pip install -r requirements-robot-manage-mlx.txt
fi
if [[ -f requirements-robot-manage-yolo.txt ]]; then
  pip install -r requirements-robot-manage-yolo.txt
fi

# Broken/partial mlx-metal leaves ``mlx/lib`` without ``libmlx.dylib`` → ImportError at runtime.
if [[ "$(uname -s)" == "Darwin" ]]; then
  MLX_LIBMLX="$(
    python -c 'import pathlib, site; p = pathlib.Path(site.getsitepackages()[0]) / "mlx" / "lib" / "libmlx.dylib"; print(p.resolve() if p.is_file() else "")'
  )"
  if [[ -z "${MLX_LIBMLX}" ]]; then
    echo "robot_manage: mlx/lib/libmlx.dylib missing — reinstalling mlx + mlx-metal" >&2
    pip install --force-reinstall --no-cache-dir "mlx>=0.31.2" "mlx-metal>=0.31.2"
  fi
fi

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

# Wireless Reachy Mini quickstart: daemon runs on the robot when powered on.
# Out of the box, prefer mDNS host; if it isn't reachable, prompt for IP.
DEFAULT_ROBOT_HOST="${ROBOT_HOST:-reachy-mini.local}"
DEFAULT_ROBOT_PORT="${ROBOT_PORT:-8000}"
DEFAULT_CONNECTION_MODE="${ROBOT_CONNECTION_MODE:-network}"
DEFAULT_MEDIA_BACKEND="${ROBOT_MEDIA_BACKEND:-default}"

# Reachy Mini daemon is FastAPI; /api/health is robot_manage, not the robot.
can_reach_daemon() {
  local host="$1"
  local port="$2"
  curl -fsS --connect-timeout 2 "http://${host}:${port}/openapi.json" >/dev/null 2>&1
}

ARGS=("$@")
if [[ "${#ARGS[@]}" -eq 0 ]]; then
  if can_reach_daemon "${DEFAULT_ROBOT_HOST}" "${DEFAULT_ROBOT_PORT}"; then
    ARGS=(--robot-host "${DEFAULT_ROBOT_HOST}" --robot-port "${DEFAULT_ROBOT_PORT}" --connection-mode "${DEFAULT_CONNECTION_MODE}" --media-backend "${DEFAULT_MEDIA_BACKEND}")
  else
    cat <<EOF
Reachy Mini daemon not reachable at http://${DEFAULT_ROBOT_HOST}:${DEFAULT_ROBOT_PORT}

Per the official quickstart, ensure:
- Reachy Mini is powered on (daemon starts automatically)
- Your computer and Reachy Mini are on the same network

If mDNS is not working, rerun with the robot IP (from the Reachy Mini app / SDK):
  ROBOT_HOST=192.168.1.191 ./run_robot_manage.sh
EOF
    exit 2
  fi
fi

# Default bind is 0.0.0.0 (LAN). Pass --bind 127.0.0.1 before other args for localhost only.
python -m robot_manage "${ARGS[@]}" &
MANAGE_PID=$!
wait "${MANAGE_PID}"
MANAGE_EXIT=$?
exit "${MANAGE_EXIT}"
