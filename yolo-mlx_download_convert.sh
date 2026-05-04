#!/usr/bin/env bash
# Download Ultralytics YOLO26n .pt weights and convert to MLX .npz for robot_manage
# (ROBOT_MANAGE_YOLO_NPZ). Run from any directory; uses repo .venv when present.
#
# Usage:
#   ./yolo-mlx_download_convert.sh
#   ./yolo-mlx_download_convert.sh -o "$HOME/models"
#   ./yolo-mlx_download_convert.sh --skip-install   # reuse existing yolo-mlx[convert]
#
# Env:
#   YOLO_MLX_SPEC         pip spec (default: yolo-mlx[convert]>=0.2.0)
#   YOLO26_PT_BASE_URL    Ultralytics release base (default: v8.4.0 assets URL)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

YOLO_MLX_SPEC="${YOLO_MLX_SPEC:-yolo-mlx[convert]>=0.2.0}"
BASE_URL="${YOLO26_PT_BASE_URL:-https://github.com/ultralytics/assets/releases/download/v8.4.0}"
MODEL_STEM="yolo26n"
SKIP_INSTALL=0
OUT_DIR="${HOME}/models"

usage() {
  cat <<EOF
Download ${MODEL_STEM}.pt from Ultralytics and convert to ${MODEL_STEM}.npz using yolo-mlx.

Usage: $0 [options]

  -o, --output-dir DIR   Directory for .pt and .npz (default: \$HOME/models)
      --skip-install     Do not run pip (expect yolo-mlx CLI + convert deps already)
  -f, --force-convert    Re-run conversion even if .npz already exists
  -h, --help             Show this help

Upstream: https://github.com/thewebAI/yolo-mlx
EOF
}

FORCE_CONVERT=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h | --help)
      usage
      exit 0
      ;;
    -o | --output-dir)
      OUT_DIR="${2:?missing directory after $1}"
      shift 2
      ;;
    --skip-install)
      SKIP_INSTALL=1
      shift
      ;;
    -f | --force-convert)
      FORCE_CONVERT=1
      shift
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

mkdir -p "$OUT_DIR"
PT="${OUT_DIR}/${MODEL_STEM}.pt"
NPZ="${OUT_DIR}/${MODEL_STEM}.npz"

if [[ -f "${ROOT}/.venv/bin/activate" ]]; then
  # shellcheck source=/dev/null
  source "${ROOT}/.venv/bin/activate"
fi

if [[ "${SKIP_INSTALL}" -eq 0 ]]; then
  echo "Installing ${YOLO_MLX_SPEC} ..."
  pip install "${YOLO_MLX_SPEC}"
fi

if ! command -v yolo-mlx >/dev/null 2>&1; then
  echo "yolo-mlx not on PATH (activate venv or install ${YOLO_MLX_SPEC})." >&2
  exit 1
fi

if [[ ! -f "$PT" ]]; then
  echo "Downloading ${BASE_URL}/${MODEL_STEM}.pt -> $PT"
  curl -fL --progress-bar -o "$PT" "${BASE_URL}/${MODEL_STEM}.pt"
else
  echo "Found existing $PT (skip download)"
fi

# sanity: > 1 MiB
_file_size() {
  wc -c <"$1" | tr -d ' '
}
sz="$(_file_size "$PT")"
if [[ "${sz}" -lt 1048576 ]]; then
  echo "Download looks too small (${sz} bytes); removing $PT" >&2
  rm -f "$PT"
  exit 1
fi

if [[ -f "$NPZ" && "${FORCE_CONVERT}" -eq 0 ]]; then
  echo "Found existing $NPZ (use --force-convert to overwrite). Done."
  echo "Set: export ROBOT_MANAGE_YOLO_NPZ=$NPZ"
  exit 0
fi

echo "Converting $PT -> $NPZ (--verify) ..."
yolo-mlx converters convert "$PT" -o "$NPZ" --verify

echo "OK: $NPZ"
echo "Set: export ROBOT_MANAGE_YOLO_NPZ=$NPZ"
