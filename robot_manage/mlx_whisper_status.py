"""Single place to probe ``mlx_whisper`` (import can fail with ``OSError``, not only ``ImportError``)."""

from __future__ import annotations

_ERR_MAX = 720


def mlx_whisper_import_probe() -> tuple[bool, str | None]:
    """Return ``(ok, error_detail)``. ``error_detail`` is ``None`` when import succeeds."""

    try:
        import mlx_whisper  # noqa: F401
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"[:_ERR_MAX]
    return True, None
