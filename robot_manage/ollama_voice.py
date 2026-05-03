"""Ollama ``/api/chat`` text streaming for robot_manage."""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

import httpx

from robot_manage.settings import ollama_num_ctx, ollama_voice_http_stream


def _http_error_detail(r: httpx.Response) -> str:
    raw = (r.text or "").strip()
    if not raw:
        return ""
    try:
        j = json.loads(raw)
        if isinstance(j, dict) and "error" in j:
            return str(j["error"])
    except json.JSONDecodeError:
        pass
    return raw[:1200] + ("..." if len(raw) > 1200 else "")


async def _iter_chat_stream_deltas(resp: httpx.Response) -> AsyncIterator[str]:
    accumulated = ""
    async for line in resp.aiter_lines():
        if not line.strip():
            continue
        data = json.loads(line)
        if "error" in data:
            raise RuntimeError(str(data["error"]))
        msg = data.get("message") or {}
        piece = str(msg.get("content", ""))
        if not piece:
            continue
        if piece.startswith(accumulated):
            delta = piece[len(accumulated) :]
            accumulated = piece
            if delta:
                yield delta
        else:
            accumulated += piece
            yield piece


async def _yield_text_as_token_chunks(text: str, *, chunk: int = 24) -> AsyncIterator[str]:
    for i in range(0, len(text), chunk):
        yield text[i : i + chunk]
        await asyncio.sleep(0)


async def stream_text_chat_messages(
    *,
    client: httpx.AsyncClient,
    base_url: str,
    model: str,
    messages: list[dict[str, Any]],
) -> AsyncIterator[str]:
    """Stream assistant deltas from ``/api/chat`` with the given ``messages`` (plain text roles only)."""

    url = f"{base_url}/api/chat"
    options = {"num_ctx": ollama_num_ctx()}
    if ollama_voice_http_stream():
        payload: dict[str, Any] = {
            "model": model,
            "stream": True,
            "messages": messages,
            "options": options,
            "think": False,
        }
        async with client.stream("POST", url, json=payload) as resp:
            resp.raise_for_status()
            async for d in _iter_chat_stream_deltas(resp):
                yield d
        return

    payload = {
        "model": model,
        "stream": False,
        "messages": messages,
        "options": options,
        "think": False,
    }
    r = await client.post(url, json=payload)
    if r.is_error:
        raise RuntimeError(f"ollama_chat_http_{r.status_code}:{_http_error_detail(r)}")
    data = r.json()
    if "error" in data:
        raise RuntimeError(str(data["error"]))
    msg = data.get("message") or {}
    text = str(msg.get("content", ""))
    async for part in _yield_text_as_token_chunks(text):
        yield part
