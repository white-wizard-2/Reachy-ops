"""Runtime configuration (env-first)."""

from __future__ import annotations

import os
from pathlib import Path


def ollama_base_url() -> str:
    return os.environ.get("OLLAMA_BASE_URL", "http://192.168.1.228:11434").rstrip("/")


def ollama_model() -> str:
    return os.environ.get("OLLAMA_MODEL", "gemma4:e4b")


def ollama_system_prompt() -> str:
    return os.environ.get(
        "OLLAMA_SYSTEM",
        "You are Disco, the voice assistant on a Pollen Reachy Mini robot. "
        "Stay in character: one steady persona—warm, concise, capable, lightly playful, never corporate. "
        "User turns come from the robot microphone; answer briefly and accurately. "
        "Reply in the same language as the user's current turn; do not offer to switch languages or "
        "snap back to English with generic sign-offs unless they asked for English. "
        "Do not use emojis or emoticons; plain text only. "
        "Do not invent camera feeds, coordinates, sectors, or surveillance-style fiction unless they ask.",
    )


def ollama_voice_http_stream() -> bool:
    """``stream: true`` when ``OLLAMA_VOICE_STREAM=1`` (default ``stream: false``)."""

    return os.environ.get("OLLAMA_VOICE_STREAM", "").strip().lower() in ("1", "true", "yes")


def ollama_num_ctx() -> int:
    return int(os.environ.get("OLLAMA_NUM_CTX", "8192"))


def mlx_whisper_repo() -> str:
    """Hugging Face repo id for ``mlx_whisper.transcribe`` (default: large-v3 MLX)."""

    return os.environ.get(
        "MLX_WHISPER_REPO",
        "mlx-community/whisper-large-v3-mlx",
    ).strip()


def mlx_whisper_max_chunk_sec() -> float:
    """Max seconds of audio per utterance before a forced Whisper pass (cap)."""

    return float(os.environ.get("MLX_WHISPER_MAX_CHUNK_SEC", "20.0"))


def mlx_whisper_language() -> str | None:
    """ISO-639-1 code passed to Whisper decode (e.g. ``en``); empty env → auto-detect."""

    raw = os.environ.get("MLX_WHISPER_LANGUAGE", "").strip()
    return raw if raw else None


def mlx_whisper_no_speech_threshold() -> float:
    """Higher → more likely to treat quiet as no speech (default ``0.82``; Whisper default ~0.6)."""

    return float(os.environ.get("MLX_WHISPER_NO_SPEECH_THRESHOLD", "0.82"))


def mlx_whisper_min_rms() -> float:
    """Skip Whisper on an utterance when mono float32 RMS is below this; ``0`` disables (default ``0.01``)."""

    return float(os.environ.get("MLX_WHISPER_MIN_RMS", "0.01"))


def mlx_whisper_condition_on_previous_text() -> bool:
    """``MLX_WHISPER_CONDITION_ON_PREVIOUS=1`` — default off to reduce repetition on quiet buffers."""

    return os.environ.get("MLX_WHISPER_CONDITION_ON_PREVIOUS", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def mlx_voice_tick_sec() -> float:
    """VAD poll interval in seconds (default ``0.12``)."""

    return float(os.environ.get("MLX_VOICE_TICK_SEC", "0.12"))


def mlx_voice_silence_end_ms() -> float:
    """End an utterance after this many ms of sub-threshold RMS (default ``800``)."""

    return float(os.environ.get("MLX_VOICE_SILENCE_END_MS", "800"))


def mlx_voice_min_utterance_ms() -> float:
    """Minimum voiced duration (ms) before silence can end an utterance (default ``400``)."""

    return float(os.environ.get("MLX_VOICE_MIN_UTTERANCE_MS", "400"))


def mlx_voice_speech_rms() -> float:
    """Mono float32 RMS above this counts as speech for VAD (default ``0.012``)."""

    return float(os.environ.get("MLX_VOICE_SPEECH_RMS", "0.012"))


def ollama_voice_json_moves_enabled() -> bool:
    """``OLLAMA_VOICE_JSON_MOVES=1`` — assistant replies are JSON ``{speech, move}`` (legacy; can fight TTS timing)."""

    return os.environ.get("OLLAMA_VOICE_JSON_MOVES", "").strip().lower() in ("1", "true", "yes")


def robot_manage_reaction_moves_enabled() -> bool:
    """``ROBOT_MANAGE_REACTION_MOVES=1`` — play a short reaction move during TTS (default on)."""

    raw = os.environ.get("ROBOT_MANAGE_REACTION_MOVES", "1").strip().lower()
    return raw in ("1", "true", "yes")


def ollama_voice_robot_tools_enabled() -> bool:
    """``OLLAMA_VOICE_ROBOT_TOOLS=1`` — expose motors + camera to Ollama as tools (default on)."""

    raw = os.environ.get("OLLAMA_VOICE_ROBOT_TOOLS", "1").strip().lower()
    return raw in ("1", "true", "yes")


def ollama_voice_text_system_prompt() -> str:
    from robot_manage.move_catalog import move_instruction_appendix

    default = (
        "You are Disco, the onboard assistant for this Reachy Mini—the human is talking to you on the robot. "
        "Reply with plain natural language only: one assistant message, no JSON, no markdown fences, no commentary. "
        "That text is what gets read aloud on the robot speaker. "
        "Embody one personality: friendly, direct, a little fun, never stiff or call-center scripted. "
        "Use first person as Disco when it fits; keep answers short and useful. "
        "User turns are transcribed from the robot microphone (MLX Whisper); keep continuity across turns. "
        "Match the language of the user's latest message; do not volunteer language switches, "
        "do not default to English with phrases like switching back to English, and avoid stock closers "
        "such as how can I assist you further with your Reachy Mini robot. "
        "Do not use emojis or emoticons. "
        "Do not invent camera feeds, coordinates, sectors, or surveillance-style fiction unless they ask."
    )
    base = os.environ.get("OLLAMA_VOICE_TEXT_SYSTEM", default)
    if ollama_voice_robot_tools_enabled():
        from robot_manage.reachy_llm_tools import robot_tools_system_appendix

        base = base + "\n\n" + robot_tools_system_appendix()
    if ollama_voice_json_moves_enabled():
        return base + "\n\n" + move_instruction_appendix()
    return base


def ollama_voice_max_history_messages() -> int:
    """Max chat messages (including system) kept for Ollama; oldest user/assistant pairs are dropped."""

    return max(4, int(os.environ.get("OLLAMA_VOICE_MAX_HISTORY_MESSAGES", "32")))


def ollama_voice_say_enabled() -> bool:
    """``OLLAMA_VOICE_SAY=1`` — speak each completed LLM sentence with macOS ``say`` (host running robot_manage)."""

    return os.environ.get("OLLAMA_VOICE_SAY", "").strip().lower() in ("1", "true", "yes")


def ollama_voice_say_target() -> str:
    """Where to play TTS audio.

    - ``macos``: use local ``say`` on the host running robot_manage
    - ``reachy``: synthesize TTS and play it on the Reachy Mini speaker via the daemon API

    Env: ``OLLAMA_VOICE_SAY_TARGET`` (default ``macos``).
    """

    v = os.environ.get("OLLAMA_VOICE_SAY_TARGET", "macos").strip().lower()
    return v if v in ("macos", "reachy") else "macos"


def ollama_voice_say_voice() -> str | None:
    """Optional ``say -v`` voice name (``OLLAMA_VOICE_SAY_VOICE``)."""

    v = os.environ.get("OLLAMA_VOICE_SAY_VOICE", "").strip()
    return v if v else None


def ollama_voice_say_post_ms() -> float:
    """Ms to keep mic gated after each TTS batch (reverb tail). Env: ``OLLAMA_VOICE_SAY_POST_MS`` (default ``500``)."""

    return float(os.environ.get("OLLAMA_VOICE_SAY_POST_MS", "500"))


def yolo_mlx_weights_path() -> str | None:
    """Path to converted YOLO26 weights (``.npz`` / ``.safetensors``). Env ``ROBOT_MANAGE_YOLO_NPZ``."""

    raw = os.environ.get("ROBOT_MANAGE_YOLO_NPZ", "").strip()
    if not raw:
        return None
    p = Path(raw).expanduser()
    return str(p.resolve()) if p.is_file() else None


def yolo_mlx_import_ok() -> bool:
    try:
        import yolo26mlx  # noqa: F401

        return True
    except Exception:
        return False
