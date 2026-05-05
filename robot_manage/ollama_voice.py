"""Ollama ``/api/chat`` text streaming for robot_manage."""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

import httpx

from robot_manage.settings import ollama_num_ctx, ollama_voice_http_stream

_TOOL_CHAT_MAX_ROUNDS: int = 16


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


async def yield_text_as_token_chunks(text: str, *, chunk: int = 24) -> AsyncIterator[str]:
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
    async for part in yield_text_as_token_chunks(text):
        yield part


async def complete_vision_chat(
    client: httpx.AsyncClient,
    base_url: str,
    model: str,
    *,
    system: str,
    user: str,
    images: list[str],
) -> str:
    """One non-streaming ``/api/chat`` with base64 JPEG ``images`` (Ollama vision)."""

    url = f"{base_url.rstrip('/')}/api/chat"
    options = {"num_ctx": ollama_num_ctx()}
    payload: dict[str, Any] = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user, "images": images},
        ],
        "options": options,
        "think": False,
    }
    r = await client.post(url, json=payload)
    if r.is_error:
        raise RuntimeError(f"ollama_vision_http_{r.status_code}:{_http_error_detail(r)}")
    data = r.json()
    if "error" in data:
        raise RuntimeError(str(data["error"]))
    msg = data.get("message") or {}
    return str(msg.get("content", "") or "")


async def complete_chat_with_robot_tools(
    *,
    client: httpx.AsyncClient,
    base_url: str,
    model: str,
    conv: list[dict[str, Any]],
    mini: Any,
) -> str:
    """Non-streaming ``/api/chat`` with ``tools``; mutates ``conv`` with tool transcripts and final assistant."""

    from robot_manage.reachy_llm_tools import REACHY_TOOLS, execute_robot_tool, parse_tool_arguments

    url = f"{base_url}/api/chat"
    options = {"num_ctx": ollama_num_ctx()}

    for _ in range(_TOOL_CHAT_MAX_ROUNDS):
        payload: dict[str, Any] = {
            "model": model,
            "stream": False,
            "messages": conv,
            "tools": REACHY_TOOLS,
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
        tool_calls = msg.get("tool_calls")
        if not tool_calls:
            text = str(msg.get("content", "") or "").strip()
            am: dict[str, Any] = {"role": "assistant", "content": text}
            conv.append(am)
            return text

        am = dict(msg)
        am.setdefault("role", "assistant")
        conv.append(am)

        batch_images: list[str] = []
        for tc in tool_calls:
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function") or {}
            if not isinstance(fn, dict):
                continue
            tname = str(fn.get("name") or "")
            try:
                args = parse_tool_arguments(fn.get("arguments"))
            except (json.JSONDecodeError, TypeError) as e:
                body = json.dumps({"ok": False, "error": f"bad_arguments:{e!s}"})
                imgs: list[str] = []
            else:
                try:
                    body, imgs = await asyncio.to_thread(execute_robot_tool, mini, tname, args)
                except Exception as e:
                    body = json.dumps({"ok": False, "error": str(e)})
                    imgs = []
            conv.append({"role": "tool", "tool_name": tname, "content": body})
            batch_images.extend(imgs)

        if batch_images:
            conv.append(
                {
                    "role": "user",
                    "content": (
                        f"Attached: {len(batch_images)} robot camera frame(s). "
                        "Use them to answer; then continue with tools if needed or reply in plain language."
                    ),
                    "images": batch_images,
                }
            )

    raise RuntimeError(f"ollama_tool_rounds_exceeded:{_TOOL_CHAT_MAX_ROUNDS}")
