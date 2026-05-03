"""HTTP error body helper for Ollama responses."""

import httpx

from robot_manage.ollama_voice import _http_error_detail


def test_http_error_detail_json_error_field() -> None:
    r = httpx.Response(500, content=b'{"error":"model exploded"}')
    assert _http_error_detail(r) == "model exploded"


def test_http_error_detail_truncates_plain_text() -> None:
    long = "x" * 2000
    r = httpx.Response(500, content=long.encode())
    out = _http_error_detail(r)
    assert out.endswith("...")
    assert len(out) <= 1203
