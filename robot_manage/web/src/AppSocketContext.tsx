import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  type MutableRefObject,
} from "react";

import { REACHY_MODES_TOOLS_EVENT } from "@/voiceModesToolsEvent";
import type { CameraLayoutResponse } from "@/types/camera";
import type { YoloDetectionsPayload, YoloVisionState } from "@/types/yoloVision";

type LlmConfig = { model: string; ollama_host: string };

type VoiceStatus = { buffering: boolean; buffered_seconds_estimate: number };

type MeterPayload = { levels: number[]; peak: number };

type PipeInfo = {
  mlx_whisper_import_ok: boolean;
  /** Server import exception text when ``mlx_whisper_import_ok`` is false. */
  mlx_whisper_import_error: string | null;
  mlx_live_ready: boolean;
};

export type DeviceControlsState = {
  mic_enabled: boolean;
  camera_enabled: boolean;
  bot_awake: boolean;
  audio_output_enabled: boolean;
  /** When on, empty LLM reply triggers a head + antenna scan on the robot. */
  idle_look_sweep_enabled: boolean;
  /** When on, server steers head toward moving YOLO ByteTrack targets (Apple Silicon + weights only). */
  yolo_follow_enabled: boolean;
  /** Daemon mic capture level 0–100 (POST ``/api/volume/microphone/set``). */
  daemon_mic_input_volume: number;
  /** Daemon speaker output 0–100 (POST ``/api/volume/set``; may play a short test tone). */
  daemon_speaker_volume: number;
};

export type RobotStateMsg = {
  type: "robot_state";
  data: Record<string, unknown> | null;
  error: string | null;
  fetched_at: string | null;
};

type SnapshotPayload = {
  layout: CameraLayoutResponse;
  llm_config: LlmConfig;
  voice_pipeline: PipeInfo;
  voice_status: VoiceStatus;
  voice_meter: MeterPayload;
  modes_tools: { mode: string | null; tools: string[] };
  conversation: { role: string; content: string }[];
  robot_state: RobotStateMsg;
  yolo_vision?: YoloVisionState;
  device_controls?: {
    mic_enabled?: boolean;
    camera_enabled?: boolean;
    bot_awake?: boolean;
    audio_output_enabled?: boolean;
    idle_look_sweep_enabled?: boolean;
    yolo_follow_enabled?: boolean;
    daemon_mic_input_volume?: number;
    daemon_speaker_volume?: number;
  };
};

type AppSocketState = {
  connected: boolean;
  socketError: string | null;
  layout: CameraLayoutResponse | null;
  robotState: RobotStateMsg | null;
  llmConfig: LlmConfig | null;
  voicePipeline: PipeInfo | null;
  voiceStatus: VoiceStatus;
  voiceMeter: MeterPayload;
  modesTools: { mode: string | null; tools: string[] };
  conversation: { role: string; content: string }[];
  deviceControls: DeviceControlsState;
  yoloVision: YoloVisionState;
  yoloDetections: YoloDetectionsPayload | null;
};

const defaultDeviceControls: DeviceControlsState = {
  mic_enabled: true,
  camera_enabled: true,
  bot_awake: true,
  audio_output_enabled: true,
  idle_look_sweep_enabled: false,
  yolo_follow_enabled: true,
  daemon_mic_input_volume: 70,
  daemon_speaker_volume: 70,
};

function normalizeDeviceControls(raw: SnapshotPayload["device_controls"]): DeviceControlsState {
  if (!raw) return { ...defaultDeviceControls };
  return {
    mic_enabled: typeof raw.mic_enabled === "boolean" ? raw.mic_enabled : true,
    camera_enabled: typeof raw.camera_enabled === "boolean" ? raw.camera_enabled : true,
    bot_awake: typeof raw.bot_awake === "boolean" ? raw.bot_awake : true,
    audio_output_enabled: typeof raw.audio_output_enabled === "boolean" ? raw.audio_output_enabled : true,
    idle_look_sweep_enabled:
      typeof raw.idle_look_sweep_enabled === "boolean" ? raw.idle_look_sweep_enabled : false,
    yolo_follow_enabled: typeof raw.yolo_follow_enabled === "boolean" ? raw.yolo_follow_enabled : true,
    daemon_mic_input_volume:
      typeof raw.daemon_mic_input_volume === "number" && Number.isFinite(raw.daemon_mic_input_volume)
        ? Math.round(raw.daemon_mic_input_volume)
        : 70,
    daemon_speaker_volume:
      typeof raw.daemon_speaker_volume === "number" && Number.isFinite(raw.daemon_speaker_volume)
        ? Math.round(raw.daemon_speaker_volume)
        : 70,
  };
}

const initial: AppSocketState = {
  connected: false,
  socketError: null,
  layout: null,
  robotState: null,
  llmConfig: null,
  voicePipeline: null,
  voiceStatus: { buffering: false, buffered_seconds_estimate: 0 },
  voiceMeter: { levels: [], peak: 0 },
  modesTools: { mode: null, tools: [] },
  conversation: [],
  deviceControls: { ...defaultDeviceControls },
  yoloVision: {
    import_ok: false,
    weights_path: null,
    worker_running: false,
    worker_phase: null,
    worker_detail: null,
  },
  yoloDetections: null,
};

type Action =
  | { kind: "reset" }
  | { kind: "connected"; v: boolean }
  | { kind: "socket_error"; v: string | null }
  | { kind: "snapshot"; v: SnapshotPayload }
  | { kind: "layout"; v: CameraLayoutResponse }
  | { kind: "robot_state"; v: RobotStateMsg }
  | { kind: "voice_meter"; v: MeterPayload }
  | { kind: "voice_status"; v: VoiceStatus }
  | { kind: "voice_pipeline"; v: PipeInfo }
  | { kind: "modes_tools"; v: { mode: string | null; tools: string[] } }
  | { kind: "conversation"; v: { role: string; content: string }[] }
  | { kind: "device_controls"; v: DeviceControlsState }
  | { kind: "yolo_detections"; v: YoloDetectionsPayload };

function normalizeVoicePipeline(raw: unknown): PipeInfo {
  if (!raw || typeof raw !== "object") {
    return { mlx_whisper_import_ok: false, mlx_whisper_import_error: null, mlx_live_ready: false };
  }
  const o = raw as Record<string, unknown>;
  const err = o.mlx_whisper_import_error;
  return {
    mlx_whisper_import_ok: typeof o.mlx_whisper_import_ok === "boolean" ? o.mlx_whisper_import_ok : false,
    mlx_whisper_import_error: typeof err === "string" ? err : null,
    mlx_live_ready: typeof o.mlx_live_ready === "boolean" ? o.mlx_live_ready : false,
  };
}

function normalizeYoloVision(raw: unknown): YoloVisionState {
  if (!raw || typeof raw !== "object") {
    return {
      import_ok: false,
      weights_path: null,
      worker_running: false,
      worker_phase: null,
      worker_detail: null,
    };
  }
  const o = raw as Record<string, unknown>;
  const wp = o.worker_phase;
  const wd = o.worker_detail;
  return {
    import_ok: typeof o.import_ok === "boolean" ? o.import_ok : false,
    weights_path: typeof o.weights_path === "string" ? o.weights_path : null,
    worker_running: typeof o.worker_running === "boolean" ? o.worker_running : false,
    worker_phase: typeof wp === "string" ? wp : null,
    worker_detail: typeof wd === "string" ? wd : null,
  };
}

function reducer(s: AppSocketState, a: Action): AppSocketState {
  switch (a.kind) {
    case "reset":
      return { ...initial, socketError: s.socketError };
    case "connected":
      return { ...s, connected: a.v };
    case "socket_error":
      return { ...s, socketError: a.v };
    case "snapshot":
      return {
        ...s,
        layout: a.v.layout,
        llmConfig: a.v.llm_config,
        voicePipeline: normalizeVoicePipeline(a.v.voice_pipeline),
        voiceStatus: a.v.voice_status,
        voiceMeter: a.v.voice_meter,
        modesTools: a.v.modes_tools,
        conversation: a.v.conversation,
        robotState: a.v.robot_state,
        deviceControls: normalizeDeviceControls(a.v.device_controls),
        yoloVision: normalizeYoloVision(a.v.yolo_vision),
      };
    case "layout":
      return { ...s, layout: a.v };
    case "robot_state":
      return { ...s, robotState: a.v };
    case "voice_meter":
      return { ...s, voiceMeter: a.v };
    case "voice_status":
      return { ...s, voiceStatus: a.v };
    case "voice_pipeline":
      return { ...s, voicePipeline: a.v };
    case "modes_tools":
      return { ...s, modesTools: a.v };
    case "conversation":
      return { ...s, conversation: a.v };
    case "device_controls":
      return { ...s, deviceControls: a.v };
    case "yolo_detections":
      return { ...s, yoloDetections: a.v };
    default:
      return s;
  }
}

function appWsUrl(): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws/app`;
}

type Ctx = {
  state: AppSocketState;
  send: (msg: Record<string, unknown>) => void;
  voiceLiveHandlersRef: MutableRefObject<Set<(ev: Record<string, unknown>) => void>>;
  registerVoiceLiveHandler: (fn: (ev: Record<string, unknown>) => void) => () => void;
};

const AppSocketContext = createContext<Ctx | null>(null);

export function AppSocketProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initial);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const voiceLiveHandlersRef = useRef<Set<(ev: Record<string, unknown>) => void>>(new Set());

  const registerVoiceLiveHandler = useCallback((fn: (ev: Record<string, unknown>) => void) => {
    voiceLiveHandlersRef.current.add(fn);
    return () => {
      voiceLiveHandlersRef.current.delete(fn);
    };
  }, []);

  const send = useCallback((msg: Record<string, unknown>) => {
    const w = wsRef.current;
    if (w && w.readyState === WebSocket.OPEN) {
      w.send(JSON.stringify(msg));
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    const connect = () => {
      if (cancelled) return;
      if (reconnectTimerRef.current != null) {
        window.clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      dispatch({ kind: "socket_error", v: null });
      const ws = new WebSocket(appWsUrl());
      wsRef.current = ws;
      ws.onopen = () => {
        if (!cancelled) dispatch({ kind: "connected", v: true });
      };
      ws.onmessage = (ev) => {
        let msg: Record<string, unknown>;
        try {
          msg = JSON.parse(String(ev.data)) as Record<string, unknown>;
        } catch {
          return;
        }
        const t = msg.type as string | undefined;
        if (t === "snapshot") {
          const { type: _t, ...rest } = msg;
          dispatch({ kind: "snapshot", v: rest as SnapshotPayload });
          return;
        }
        if (t === "device_controls") {
          const mic = msg.mic_enabled;
          const cam = msg.camera_enabled;
          const bot = msg.bot_awake;
          const audio = msg.audio_output_enabled;
          const sweep = msg.idle_look_sweep_enabled;
          const yfollow = msg.yolo_follow_enabled;
          const dmic = msg.daemon_mic_input_volume;
          const dspk = msg.daemon_speaker_volume;
          dispatch({
            kind: "device_controls",
            v: {
              mic_enabled: typeof mic === "boolean" ? mic : true,
              camera_enabled: typeof cam === "boolean" ? cam : true,
              bot_awake: typeof bot === "boolean" ? bot : true,
              audio_output_enabled: typeof audio === "boolean" ? audio : true,
              idle_look_sweep_enabled: typeof sweep === "boolean" ? sweep : false,
              yolo_follow_enabled: typeof yfollow === "boolean" ? yfollow : true,
              daemon_mic_input_volume:
                typeof dmic === "number" && Number.isFinite(dmic) ? Math.round(dmic) : 70,
              daemon_speaker_volume:
                typeof dspk === "number" && Number.isFinite(dspk) ? Math.round(dspk) : 70,
            },
          });
          return;
        }
        if (t === "yolo_detections") {
          const fh = msg.frame_hw;
          const tracks = msg.tracks;
          const tms = msg.t_ms;
          const fh0 = Array.isArray(fh) && fh.length >= 2 ? Number(fh[0]) : NaN;
          const fh1 = Array.isArray(fh) && fh.length >= 2 ? Number(fh[1]) : NaN;
          const tmsN = Number(tms);
          if (
            Array.isArray(fh) &&
            fh.length === 2 &&
            Number.isFinite(fh0) &&
            Number.isFinite(fh1) &&
            Array.isArray(tracks) &&
            Number.isFinite(tmsN)
          ) {
            dispatch({
              kind: "yolo_detections",
              v: {
                frame_hw: [fh0, fh1],
                tracks: tracks as YoloDetectionsPayload["tracks"],
                t_ms: tmsN,
              },
            });
          }
          return;
        }
        if (t === "layout") {
          const p = msg.payload as CameraLayoutResponse;
          if (p) dispatch({ kind: "layout", v: p });
          return;
        }
        if (t === "robot_state") {
          dispatch({ kind: "robot_state", v: msg as unknown as RobotStateMsg });
          return;
        }
        if (t === "voice_meter") {
          const { type: _x, ...meter } = msg;
          dispatch({ kind: "voice_meter", v: meter as unknown as MeterPayload });
          return;
        }
        if (t === "voice_status") {
          const { type: _x, ...st } = msg;
          dispatch({ kind: "voice_status", v: st as unknown as VoiceStatus });
          return;
        }
        if (t === "voice_pipeline") {
          const { type: _x, ...pi } = msg;
          dispatch({ kind: "voice_pipeline", v: normalizeVoicePipeline(pi) });
          return;
        }
        if (t === "modes_tools") {
          const mode = (msg.mode as string | null | undefined) ?? null;
          const tools = Array.isArray(msg.tools) ? (msg.tools as string[]) : [];
          dispatch({ kind: "modes_tools", v: { mode, tools } });
          window.dispatchEvent(
            new CustomEvent(REACHY_MODES_TOOLS_EVENT, { detail: { mode, tools } }),
          );
          return;
        }
        if (t === "voice" && typeof msg.event === "string") {
          const evName = msg.event as string;
          if (evName === "modes_tools") {
            const mode = (msg.mode as string | null | undefined) ?? null;
            const tools = Array.isArray(msg.tools) ? (msg.tools as string[]) : [];
            dispatch({ kind: "modes_tools", v: { mode, tools } });
            window.dispatchEvent(
              new CustomEvent(REACHY_MODES_TOOLS_EVENT, { detail: { mode, tools } }),
            );
          }
          if (evName === "conversation" && Array.isArray(msg.messages)) {
            dispatch({ kind: "conversation", v: msg.messages as { role: string; content: string }[] });
          }
          return;
        }
        if (t === "voice_live") {
          const evName = msg.event as string | undefined;
          if (evName === "conversation" && Array.isArray(msg.messages)) {
            dispatch({ kind: "conversation", v: msg.messages as { role: string; content: string }[] });
          }
          if (evName === "modes_tools") {
            const mode = (msg.mode as string | null | undefined) ?? null;
            const tools = Array.isArray(msg.tools) ? (msg.tools as string[]) : [];
            dispatch({ kind: "modes_tools", v: { mode, tools } });
            window.dispatchEvent(
              new CustomEvent(REACHY_MODES_TOOLS_EVENT, { detail: { mode, tools } }),
            );
          }
          for (const h of voiceLiveHandlersRef.current) {
            try {
              h(msg);
            } catch {
              /* ignore */
            }
          }
          return;
        }
      };
      ws.onerror = () => {
        if (!cancelled) dispatch({ kind: "socket_error", v: "WebSocket error" });
      };
      ws.onclose = () => {
        wsRef.current = null;
        if (!cancelled) {
          dispatch({ kind: "connected", v: false });
          dispatch({ kind: "socket_error", v: "Disconnected — reconnecting…" });
          reconnectTimerRef.current = window.setTimeout(connect, 2500);
        }
      };
    };

    connect();
    return () => {
      cancelled = true;
      if (reconnectTimerRef.current != null) window.clearTimeout(reconnectTimerRef.current);
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, []);

  const ctx = useMemo<Ctx>(
    () => ({ state, send, voiceLiveHandlersRef, registerVoiceLiveHandler }),
    [state, send, registerVoiceLiveHandler],
  );

  return <AppSocketContext.Provider value={ctx}>{children}</AppSocketContext.Provider>;
}

export function useAppSocket(): Ctx {
  const c = useContext(AppSocketContext);
  if (!c) throw new Error("useAppSocket outside AppSocketProvider");
  return c;
}
