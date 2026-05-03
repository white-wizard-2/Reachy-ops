"""Run robot_manage: ``python -m robot_manage ...``."""

from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from robot_manage.app import create_app


def main() -> None:
    p = argparse.ArgumentParser(
        description="robot_manage — Reachy Mini camera + Ollama voice web UI",
        epilog=(
            "Ollama: OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_SYSTEM. Optional: OLLAMA_VOICE_TRANSCRIBE_API=1, "
            "OLLAMA_VOICE_STREAM=1, OLLAMA_NUM_CTX, ROBOT_MANAGE_VOICE_DUMP_WAV=1, ROBOT_MANAGE_VOICE_DUMP_DIR."
        ),
    )
    p.add_argument("--robot-host", default="reachy-mini.local", help="Reachy Mini daemon host")
    p.add_argument("--robot-port", type=int, default=8000, help="Reachy Mini daemon port")
    p.add_argument(
        "--connection-mode",
        default="auto",
        choices=("auto", "localhost_only", "network"),
        help="reachy_mini connection mode",
    )
    p.add_argument(
        "--media-backend",
        default="default",
        help="reachy_mini MediaManager backend (default|webrtc|...)",
    )
    p.add_argument(
        "--bind",
        default="0.0.0.0",
        help="HTTP bind host (0.0.0.0 = all interfaces, reachable on LAN; use 127.0.0.1 for localhost only)",
    )
    p.add_argument("--port", type=int, default=8765, help="HTTP port for this web UI")
    p.add_argument(
        "--static-dir",
        type=Path,
        default=None,
        help="Directory with built frontend (default: robot_manage/static)",
    )
    args = p.parse_args()

    app = create_app(
        robot_host=args.robot_host,
        robot_port=args.robot_port,
        connection_mode=args.connection_mode,
        media_backend=args.media_backend,
        static_dir=args.static_dir,
    )
    uvicorn.run(app, host=args.bind, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
