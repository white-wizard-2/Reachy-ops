# Reachy-ops

Web console and voice stack for **Reachy Mini**: multiplexed camera MJPEG, microphone ring buffer, **MLX Whisper** (silence-segmented utterances) → **Ollama** `/api/chat` with conversation context, optional macOS `say` for replies.

The previous **vision → full-vector online learning** experiment (`robot_world`, `main.py`, PyTorch/MLX training) lives under **`_temp/`** so this repo stays focused on operations.

---

## Requirements files

| File | Purpose |
|------|--------|
| `requirements.txt` | **robot_manage base:** grpc pins, `reachy-mini`, `reachy-sdk`, `numpy`, `opencv-python-headless`, `requests`. |
| `requirements-robot-manage.txt` | **robot_manage web:** `fastapi`, `uvicorn`, `httpx`. |
| `requirements-robot-manage-mlx.txt` | **Optional** Apple Silicon: `mlx-whisper` for live voice ASR (install in addition to the two above). |
| `_temp/requirements-mlx.txt` | **Archived learner only** (`_temp/robot_world`): `mlx-image` + you install `torch` / `torchvision` separately — see `_temp/README.md`. |

There is **no** root `torch` / `torchvision` pin anymore; those were for `robot_world`, which lives under `_temp/`.

---

## Quick start

```bash
./run_robot_manage.sh
```

Optional Apple Silicon ASR:

```bash
pip install -r requirements-robot-manage-mlx.txt
```

See comments in `run_robot_manage.sh` for `OLLAMA_*`, `MLX_*`, and `OLLAMA_VOICE_SAY_*` environment variables.

---

## Layout

| Path | Role |
|------|------|
| `robot_manage/` | FastAPI app, static UI build, MLX voice pipeline, camera/mic. |
| `run_robot_manage.sh` | venv, deps, `npm run build`, `python -m robot_manage`. |
| `tests/` | Tests for `robot_manage` and shared utilities (no `robot_world`). |
| `_temp/robot_world/` | Archived learner / model code (not imported by `robot_manage`). |
| `_temp/main.py` | Archived CLI entrypoint for online learning. |
| `_temp/tests_robot_world/` | Archived tests; run with `PYTHONPATH=_temp` (see `_temp/README.md`). |

---

## GitHub

Remote (replace or add if you already have `origin`):

```bash
git init
git remote add origin git@github.com:white-wizard-2/Reachy-ops.git
git add -A
git commit -m "Initial Reachy-ops import"
git branch -M main
git push -u origin main
```

---

## Development

```bash
ruff check robot_manage tests
PYTHONPATH=. pytest tests/ -q
```

Long-form docs for the archived learning stack: `_temp/ORIGINAL_README_ROBOT_WORLD.md`.
