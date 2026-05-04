"""Reachy LLM tool executor and Ollama non-streaming tool chat loop."""

from __future__ import annotations

import asyncio
import json

import httpx
import numpy as np

from robot_manage.ollama_voice import complete_chat_with_robot_tools
from robot_manage.reachy_llm_tools import execute_robot_tool, parse_tool_arguments


def test_parse_tool_arguments_dict() -> None:
    assert parse_tool_arguments({"x": 1}) == {"x": 1}


def test_parse_tool_arguments_json_str() -> None:
    assert parse_tool_arguments('{"a": 2}') == {"a": 2}


class _MiniState:
    def __init__(self) -> None:
        self.head_calls: list[list[float]] = []
        self.goto_kw: list[dict] = []

    def get_current_joint_positions(self) -> tuple[list[float], list[float]]:
        return ([0.1] * 7, [0.2, 0.3])

    def get_current_head_pose(self) -> np.ndarray:
        return np.eye(4, dtype=np.float64)

    def _set_joint_positions(
        self,
        *,
        head_joint_positions: list[float] | None,
        antennas_joint_positions: list[float] | None,
    ) -> None:
        if head_joint_positions is not None:
            self.head_calls.append(list(head_joint_positions))

    def set_target_antenna_joint_positions(self, v: list[float]) -> None:
        self.ant = list(v)

    def set_target_body_yaw(self, y: float) -> None:
        self.yaw = y

    def set_target_head_pose(self, m: np.ndarray) -> None:
        self.pose = np.asarray(m)

    def goto_target(self, **kw: object) -> None:
        self.goto_kw.append(dict(kw))


def test_execute_get_robot_state() -> None:
    m = _MiniState()
    body, imgs = execute_robot_tool(m, "get_robot_state", {})
    assert imgs == []
    d = json.loads(body)
    assert len(d["head_joints_rad"]) == 7
    assert len(d["antenna_joints_rad"]) == 2


def test_ollama_complete_chat_tool_round_trip() -> None:
    n = {"i": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        n["i"] += 1
        if n["i"] == 1:
            payload = {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "type": "function",
                            "function": {
                                "name": "get_robot_state",
                                "arguments": {},
                            },
                        }
                    ],
                }
            }
        else:
            payload = {"message": {"role": "assistant", "content": "OK done."}}
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)

    async def run() -> tuple[str, list[dict]]:
        async with httpx.AsyncClient(transport=transport) as client:
            conv: list[dict] = [{"role": "system", "content": "s"}, {"role": "user", "content": "x"}]
            text = await complete_chat_with_robot_tools(
                client=client,
                base_url="http://ollama.invalid",
                model="test",
                conv=conv,
                mini=_MiniState(),
            )
            return text, conv

    text, conv = asyncio.run(run())
    assert text == "OK done."
    assert any(m.get("role") == "tool" for m in conv)
    assert conv[-1].get("role") == "assistant"
    assert conv[-1].get("content") == "OK done."
