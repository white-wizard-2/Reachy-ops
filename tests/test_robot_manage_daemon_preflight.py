"""daemon_preflight (httpx MockTransport, no robot)."""

import asyncio

import httpx

from robot_manage.daemon_preflight import (
    classify_daemon_state,
    ensure_reachy_mini_daemon_backend_running,
)


def test_classify_daemon_state() -> None:
    assert classify_daemon_state({"state": "running"}) == "running"
    assert classify_daemon_state({"state": "stopped"}) == "stopped"
    assert classify_daemon_state({"state": "starting"}) == "other"
    assert classify_daemon_state({}) == "other"


def test_ensure_noop_when_running() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/daemon/status":
            return httpx.Response(200, json={"state": "running"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)

    async def run() -> None:
        async with httpx.AsyncClient(transport=transport, base_url="http://robot:8000") as client:
            await ensure_reachy_mini_daemon_backend_running("robot", 8000, client=client)

    asyncio.run(run())


def test_ensure_starts_then_running() -> None:
    n_status = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/daemon/status":
            n_status["n"] += 1
            if n_status["n"] == 1:
                return httpx.Response(200, json={"state": "stopped"})
            return httpx.Response(200, json={"state": "running"})
        if request.url.path == "/api/daemon/start":
            assert request.url.params.get("wake_up") == "true"
            return httpx.Response(200, json={"job_id": "test-job"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)

    async def run() -> None:
        async with httpx.AsyncClient(transport=transport, base_url="http://robot:8000") as client:
            await ensure_reachy_mini_daemon_backend_running(
                "robot", 8000, client=client, poll_interval_s=0.01, start_timeout_s=5.0
            )

    asyncio.run(run())


def test_ensure_other_state_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/daemon/status":
            return httpx.Response(200, json={"state": "starting", "error": "busy"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)

    async def run() -> None:
        async with httpx.AsyncClient(transport=transport, base_url="http://robot:8000") as client:
            await ensure_reachy_mini_daemon_backend_running("robot", 8000, client=client)

    try:
        asyncio.run(run())
    except ConnectionError as e:
        assert "starting" in str(e)
        assert "busy" in str(e)
    else:
        raise AssertionError("expected ConnectionError")
