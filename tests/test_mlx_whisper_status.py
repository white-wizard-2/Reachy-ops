"""mlx_whisper import probe."""

from __future__ import annotations

from robot_manage.mlx_whisper_status import mlx_whisper_import_probe


def test_mlx_whisper_import_probe_returns_tuple() -> None:
    ok, err = mlx_whisper_import_probe()
    assert isinstance(ok, bool)
    assert err is None or isinstance(err, str)
