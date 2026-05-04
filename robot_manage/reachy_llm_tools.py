"""Ollama tool schemas + execution for Reachy Mini motors and camera (robot_manage voice stack)."""

from __future__ import annotations

import base64
import json
import math
from typing import Any, Final

import numpy as np
from scipy.spatial.transform import Rotation as R

from robot_manage.jpeg_util import bgr_frame_to_jpeg_bytes

_FRAME_GRAB_ATTEMPTS: Final[int] = 60
_FRAME_GRAB_INTERVAL_S: Final[float] = 0.02


def _pose16_to_matrix(flat16: list[float]) -> np.ndarray:
    if len(flat16) != 16:
        raise ValueError("head_pose_matrix must have 16 floats (row-major 4x4)")
    m = np.array(flat16, dtype=np.float64).reshape(4, 4)
    return m


def _encode_camera_jpeg_b64(frame: np.ndarray, *, max_width: int = 640, quality: int = 82) -> str:
    import cv2

    if frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError(f"expected BGR (H,W,3), got {frame.shape}")
    h, w = int(frame.shape[0]), int(frame.shape[1])
    if w > max_width:
        scale = max_width / float(w)
        nw = max_width
        nh = max(1, int(round(h * scale)))
        frame = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_AREA)
    jpeg = bgr_frame_to_jpeg_bytes(frame, quality=quality)
    return base64.b64encode(jpeg).decode("ascii")


def _grab_frame(mini: Any) -> np.ndarray | None:
    for _ in range(_FRAME_GRAB_ATTEMPTS):
        fr = mini.media.get_frame()
        if fr is not None:
            return fr
        import time

        time.sleep(_FRAME_GRAB_INTERVAL_S)
    return None


def robot_tools_system_appendix() -> str:
    return (
        "You have robot tools to move the head (7 head joints + 2 antenna joints + body yaw) and to capture camera frames. "
        "When the user asks what you see or to look around: call look_delta or goto_head_pose to change viewpoint, "
        "then capture_camera, then describe the scene from the attached image. "
        "Angles are radians unless noted. head_pose_matrix is row-major 4x4 (16 numbers). "
        "Prefer small look_delta steps for scanning. After tools, reply in plain natural language (no JSON envelope)."
    )


REACHY_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_robot_state",
            "description": "Read current head joint positions (7), antenna joint positions (2), head 4x4 pose (row-major 16 floats), and body yaw if inferable from context.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_head_joints",
            "description": "Immediately command the 7 head joint angles in radians (Stewart platform + yaw chain).",
            "parameters": {
                "type": "object",
                "properties": {
                    "joints": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 7,
                        "maxItems": 7,
                        "description": "Seven head joint angles in radians",
                    }
                },
                "required": ["joints"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_antenna_joints",
            "description": "Immediately set both antenna joint angles in radians [right, left].",
            "parameters": {
                "type": "object",
                "properties": {
                    "joints": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 2,
                        "maxItems": 2,
                    }
                },
                "required": ["joints"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_body_yaw",
            "description": "Set target body yaw in radians.",
            "parameters": {
                "type": "object",
                "properties": {"yaw_rad": {"type": "number"}},
                "required": ["yaw_rad"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_head_pose",
            "description": "Immediately set the head pose from a 4x4 matrix (row-major 16 floats, homogeneous transform).",
            "parameters": {
                "type": "object",
                "properties": {
                    "head_pose_matrix": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 16,
                        "maxItems": 16,
                    }
                },
                "required": ["head_pose_matrix"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "goto_head_pose",
            "description": "Smoothly move the head to a target 4x4 pose over duration seconds (min-jerk on daemon).",
            "parameters": {
                "type": "object",
                "properties": {
                    "head_pose_matrix": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 16,
                        "maxItems": 16,
                    },
                    "duration_sec": {"type": "number", "description": "Movement duration in seconds (>0)"},
                },
                "required": ["head_pose_matrix", "duration_sec"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "goto_antennas",
            "description": "Smoothly move antennas to [right, left] radians over duration_sec.",
            "parameters": {
                "type": "object",
                "properties": {
                    "joints": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 2,
                        "maxItems": 2,
                    },
                    "duration_sec": {"type": "number"},
                },
                "required": ["joints", "duration_sec"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "look_delta",
            "description": "Small head reorientation relative to current pose: yaw and pitch in radians applied to current rotation (body frame approximation).",
            "parameters": {
                "type": "object",
                "properties": {
                    "yaw_rad": {"type": "number"},
                    "pitch_rad": {"type": "number"},
                    "duration_sec": {"type": "number"},
                },
                "required": ["yaw_rad", "pitch_rad", "duration_sec"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "capture_camera",
            "description": "Grab one camera frame from the robot. A vision image is attached for you in the next user message; use it to answer visually.",
            "parameters": {
                "type": "object",
                "properties": {"note": {"type": "string", "description": "Optional short note for logs"}},
                "required": [],
            },
        },
    },
]


def execute_robot_tool(mini: Any, name: str, args: dict[str, Any]) -> tuple[str, list[str]]:
    """Run one tool; return (JSON string for tool role content, list of base64 JPEGs to attach as user images)."""

    images: list[str] = []

    if name == "get_robot_state":
        hj, aj = mini.get_current_joint_positions()
        pose = mini.get_current_head_pose()
        out = {
            "head_joints_rad": list(hj),
            "antenna_joints_rad": list(aj),
            "head_pose_matrix_row_major": [float(x) for x in np.asarray(pose, dtype=np.float64).reshape(-1)],
        }
        return json.dumps(out), images

    if name == "set_head_joints":
        joints = args.get("joints")
        if not isinstance(joints, list) or len(joints) != 7:
            raise ValueError("joints must be a list of 7 numbers")
        js = [float(x) for x in joints]
        mini._set_joint_positions(head_joint_positions=js, antennas_joint_positions=None)  # noqa: SLF001
        return json.dumps({"ok": True, "set": "head_joints"}), images

    if name == "set_antenna_joints":
        joints = args.get("joints")
        if not isinstance(joints, list) or len(joints) != 2:
            raise ValueError("joints must be a list of 2 numbers")
        mini.set_target_antenna_joint_positions([float(joints[0]), float(joints[1])])
        return json.dumps({"ok": True, "set": "antennas"}), images

    if name == "set_body_yaw":
        yaw = float(args["yaw_rad"])
        mini.set_target_body_yaw(yaw)
        return json.dumps({"ok": True, "set": "body_yaw", "yaw_rad": yaw}), images

    if name == "set_head_pose":
        flat = args.get("head_pose_matrix")
        if not isinstance(flat, list):
            raise ValueError("head_pose_matrix must be a list")
        m = _pose16_to_matrix([float(x) for x in flat])
        mini.set_target_head_pose(m)
        return json.dumps({"ok": True, "set": "head_pose"}), images

    if name == "goto_head_pose":
        flat = args.get("head_pose_matrix")
        dur = float(args["duration_sec"])
        if dur <= 0:
            raise ValueError("duration_sec must be positive")
        m = _pose16_to_matrix([float(x) for x in flat])
        mini.goto_target(head=m, duration=dur, body_yaw=None)
        return json.dumps({"ok": True, "moved": "head_pose", "duration_sec": dur}), images

    if name == "goto_antennas":
        joints = args.get("joints")
        dur = float(args["duration_sec"])
        if not isinstance(joints, list) or len(joints) != 2 or dur <= 0:
            raise ValueError("invalid joints or duration")
        mini.goto_target(antennas=[float(joints[0]), float(joints[1])], duration=dur, body_yaw=None)
        return json.dumps({"ok": True, "moved": "antennas", "duration_sec": dur}), images

    if name == "look_delta":
        yaw = float(args["yaw_rad"])
        pitch = float(args["pitch_rad"])
        dur = float(args["duration_sec"])
        if dur <= 0:
            raise ValueError("duration_sec must be positive")
        cur = np.asarray(mini.get_current_head_pose(), dtype=np.float64)
        r0 = cur[:3, :3]
        t0 = cur[:3, 3]
        dR = R.from_euler("yx", [yaw, pitch]).as_matrix()
        r1 = r0 @ dR
        nxt = np.eye(4, dtype=np.float64)
        nxt[:3, :3] = r1
        nxt[:3, 3] = t0
        mini.goto_target(head=nxt, duration=dur, body_yaw=None)
        return json.dumps({"ok": True, "moved": "look_delta", "yaw_rad": yaw, "pitch_rad": pitch}), images

    if name == "capture_camera":
        fr = _grab_frame(mini)
        if fr is None:
            return json.dumps({"ok": False, "error": "no_frame"}), images
        b64 = _encode_camera_jpeg_b64(fr)
        images.append(b64)
        h, w = int(fr.shape[0]), int(fr.shape[1])
        return json.dumps({"ok": True, "width": w, "height": h, "jpeg_chars": len(b64)}), images

    raise ValueError(f"unknown tool: {name}")


def parse_tool_arguments(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        s = raw.strip()
        return json.loads(s) if s else {}
    raise TypeError(f"bad tool arguments type: {type(raw)}")
