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

type LlmConfig = { model: string; ollama_host: string };

type VoiceStatus = { buffering: boolean; buffered_seconds_estimate: number };

type MeterPayload = { levels: number[]; peak: number };

type PipeInfo = {
  mlx_whisper_import_ok: boolean;
  mlx_live_ready: boolean;
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
};

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
  | { kind: "conversation"; v: { role: string; content: string }[] };

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
        voicePipeline: a.v.voice_pipeline,
        voiceStatus: a.v.voice_status,
        voiceMeter: a.v.voice_meter,
        modesTools: a.v.modes_tools,
        conversation: a.v.conversation,
        robotState: a.v.robot_state,
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
          dispatch({ kind: "voice_pipeline", v: pi as unknown as PipeInfo });
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
