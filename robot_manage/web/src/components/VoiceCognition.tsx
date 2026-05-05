import { useCallback, useEffect, useRef, useState } from "react";

import { useAppSocket } from "@/AppSocketContext";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CollapsibleCardToggle, useCollapsibleCard } from "@/components/CollapsibleCardHeader";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import { REACHY_MODES_TOOLS_EVENT } from "@/voiceModesToolsEvent";

export { REACHY_MODES_TOOLS_EVENT } from "@/voiceModesToolsEvent";

type LlmConfig = { model: string; ollama_host: string };

type PipeInfo = {
  mlx_whisper_import_ok: boolean;
  mlx_whisper_import_error: string | null;
  mlx_live_ready: boolean;
};

type ChatMessage = { role: string; content: string };

const VOICE_SESSION_LIVE = "reachy_ops_voice_live";
const VOICE_SESSION_UI = "reachy_ops_voice_ui_v1";

type SsePayload =
  | { event: "meta"; voice?: string }
  | { event: "utterance_start" }
  | { event: "utterance_end"; text: string }
  | { event: "conversation"; messages: ChatMessage[] }
  | { event: "llm_token"; t: string }
  | { event: "llm_round_start" }
  | { event: "llm_round_end" }
  | { event: "modes_tools"; mode: string | null; tools: string[] }
  | { event: "error"; message: string };

function voiceLiveToPayload(msg: Record<string, unknown>): SsePayload | null {
  const { type: _t, ...rest } = msg;
  if (typeof rest.event !== "string") return null;
  return rest as SsePayload;
}

/** Renders voice JSON envelope as spoken text; optional motion line from server-shaped JSON. */
function AssistantMessageBody({ content }: { content: string }) {
  const t = content.trim();
  if (!t.startsWith("{")) {
    return <pre className="whitespace-pre-wrap break-words">{content}</pre>;
  }
  try {
    const o = JSON.parse(t) as { speech?: unknown; move?: unknown };
    if (typeof o.speech !== "string") {
      return <pre className="whitespace-pre-wrap break-words">{content}</pre>;
    }
    let motion: string | null = null;
    if (o.move !== null && o.move !== undefined) {
      if (typeof o.move === "object") {
        const m = o.move as { library?: unknown; id?: unknown };
        if (typeof m.library === "string" && typeof m.id === "string") {
          motion = `${m.library}/${m.id}`;
        }
      } else if (typeof o.move === "string") {
        motion = o.move;
      }
    }
    return (
      <>
        <p className="whitespace-pre-wrap break-words">{o.speech}</p>
        {motion ? (
          <p className="mt-1.5 font-mono text-[10px] text-muted-foreground/90">motion · {motion}</p>
        ) : null}
      </>
    );
  } catch {
    return <pre className="whitespace-pre-wrap break-words">{content}</pre>;
  }
}

function MicHistogram({ levels, peak }: { levels: number[]; peak: number }) {
  return (
    <div className="rounded-lg border border-border/60 bg-black/50 p-3">
      <div className="mb-2 flex items-center justify-between font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
        <span>Input level (recent ~0.35s)</span>
        <span className="text-primary/90">peak {peak.toFixed(2)}</span>
      </div>
      <div
        className="flex h-24 items-end justify-center gap-px sm:gap-0.5"
        style={{ minHeight: "6rem" }}
        aria-label="Microphone level histogram"
      >
        {levels.map((h, i) => (
          <div
            key={i}
            className="w-1.5 rounded-t bg-gradient-to-t from-primary/25 via-primary/70 to-secondary/80 sm:w-2"
            style={{ height: `${Math.max(4, h * 100)}%`, opacity: 0.35 + h * 0.65 }}
          />
        ))}
      </div>
    </div>
  );
}

function ConversationPanel({ messages }: { messages: ChatMessage[] }) {
  return (
    <div className="max-h-[min(48vh,420px)] space-y-2 overflow-y-auto rounded-md border border-border/50 bg-black/40 p-3 2xl:max-h-[min(72vh,800px)]">
      {messages.length === 0 ? (
        <p className="font-mono text-xs text-muted-foreground/70">No messages yet.</p>
      ) : (
        messages.map((m, i) => (
          <div
            key={`${m.role}-${i}`}
            className={cn(
              "rounded-md border px-3 py-2 font-mono text-xs leading-relaxed",
              m.role === "system" && "border-border/40 bg-muted/15 text-muted-foreground",
              m.role === "user" && "border-primary/35 bg-primary/10 text-foreground/95",
              m.role === "assistant" && "border-secondary/35 bg-secondary/10 text-foreground/95",
            )}
          >
            <span className="mb-1 block text-[10px] uppercase tracking-widest text-muted-foreground/90">{m.role}</span>
            {m.role === "assistant" ? (
              <AssistantMessageBody content={m.content} />
            ) : (
              <pre className="whitespace-pre-wrap break-words">{m.content}</pre>
            )}
          </div>
        ))
      )}
    </div>
  );
}

export function VoiceCognition() {
  const { state, send, registerVoiceLiveHandler } = useAppSocket();
  const cfg: LlmConfig | null = state.llmConfig;
  const pipe: PipeInfo | null = state.voicePipeline;
  const ringSec = state.voiceStatus.buffered_seconds_estimate;
  const levels = state.voiceMeter.levels;
  const meterPeak = state.voiceMeter.peak;
  const conversation = state.conversation;

  const [lastUtterance, setLastUtterance] = useState("");
  const [listening, setListening] = useState(false);
  const [llmOut, setLlmOut] = useState("");
  const [liveErr, setLiveErr] = useState<string | null>(null);
  const [liveOn, setLiveOn] = useState(false);
  const liveOnRef = useRef(false);
  const voiceUnsubRef = useRef<(() => void) | null>(null);
  const voiceResumeRef = useRef(false);
  const llmPreRef = useRef<HTMLPreElement>(null);
  const { open: liveOpen, toggle: liveToggle, contentId: liveContentId } = useCollapsibleCard(false);
  const [uiHydrated, setUiHydrated] = useState(false);

  useEffect(() => {
    liveOnRef.current = liveOn;
  }, [liveOn]);

  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(VOICE_SESSION_UI);
      if (raw) {
        const u = JSON.parse(raw) as { lastUtterance?: string; llmOut?: string };
        if (typeof u.lastUtterance === "string") setLastUtterance(u.lastUtterance);
        if (typeof u.llmOut === "string") setLlmOut(u.llmOut);
      }
    } catch {
      /* private mode or corrupt */
    }
    setUiHydrated(true);
  }, []);

  useEffect(() => {
    if (!uiHydrated) return;
    const id = window.setTimeout(() => {
      try {
        sessionStorage.setItem(
          VOICE_SESSION_UI,
          JSON.stringify({ lastUtterance, llmOut, conversation }),
        );
      } catch {
        /* ignore */
      }
    }, 300);
    return () => window.clearTimeout(id);
  }, [uiHydrated, lastUtterance, llmOut, conversation]);

  useEffect(() => {
    if (llmPreRef.current) llmPreRef.current.scrollTop = llmPreRef.current.scrollHeight;
  }, [llmOut]);

  const applyVoiceEvent = useCallback((ev: SsePayload) => {
    if (ev.event === "utterance_start") setListening(true);
    if (ev.event === "utterance_end") {
      setListening(false);
      if ("text" in ev && typeof (ev as { text: string }).text === "string") {
        setLastUtterance((ev as { text: string }).text);
      }
    }
    if (ev.event === "llm_round_start") setLlmOut("");
    if (ev.event === "llm_token") setLlmOut((o) => o + ev.t);
    if (ev.event === "error") setLiveErr(ev.message);
    if (ev.event === "modes_tools") {
      window.dispatchEvent(
        new CustomEvent(REACHY_MODES_TOOLS_EVENT, {
          detail: { mode: ev.mode, tools: Array.isArray(ev.tools) ? ev.tools : [] },
        }),
      );
    }
  }, []);

  const stopLive = useCallback(() => {
    voiceUnsubRef.current?.();
    voiceUnsubRef.current = null;
    send({ type: "voice_live_stop" });
    liveOnRef.current = false;
    setLiveOn(false);
    setListening(false);
    try {
      sessionStorage.setItem(VOICE_SESSION_LIVE, "0");
    } catch {
      /* ignore */
    }
  }, [send]);

  const startLive = useCallback(() => {
    if (liveOnRef.current) return;
    liveOnRef.current = true;
    setLiveErr(null);
    setListening(false);
    setLiveOn(true);
    try {
      sessionStorage.setItem(VOICE_SESSION_LIVE, "1");
    } catch {
      /* ignore */
    }

    voiceUnsubRef.current?.();
    voiceUnsubRef.current = registerVoiceLiveHandler((msg) => {
      const ev = voiceLiveToPayload(msg);
      if (!ev) return;
      applyVoiceEvent(ev);
    });
    send({ type: "voice_live_start" });
  }, [applyVoiceEvent, registerVoiceLiveHandler, send]);

  useEffect(() => {
    return () => {
      voiceUnsubRef.current?.();
      voiceUnsubRef.current = null;
      send({ type: "voice_live_stop" });
    };
  }, [send]);

  useEffect(() => {
    if (voiceResumeRef.current || !pipe?.mlx_live_ready) return;
    let want = false;
    try {
      want = sessionStorage.getItem(VOICE_SESSION_LIVE) === "1";
    } catch {
      return;
    }
    if (!want || liveOnRef.current) return;
    voiceResumeRef.current = true;
    startLive();
  }, [pipe?.mlx_live_ready, startLive]);

  const cfgWaiting = !state.connected || (cfg === null && state.socketError === null);
  const socketHint = state.socketError;

  return (
    <section className="mt-2 space-y-4 md:mt-3">
      <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="font-mono text-[10px] font-medium uppercase tracking-[0.45em] text-secondary/90">
            cognition layer
          </p>
          <h2 className="font-display text-2xl font-bold tracking-wide text-glow md:text-3xl">VOICE · COGNITION</h2>
          <p className="mt-1 font-sans text-sm text-muted-foreground md:max-w-[min(100%,52rem)]">
            Telemetry and live tokens use the shared <code className="font-mono text-[10px]">/ws/app</code> channel
            (no REST polling). MLX Whisper segments speech by <strong className="text-foreground/90">silence</strong>{" "}
            (see <code className="font-mono text-[10px]">MLX_VOICE_*</code> env in run script), then Ollama{" "}
            <code className="font-mono text-[10px]">/api/chat</code> with full conversation context.
          </p>
        </div>
        <div className="flex flex-col items-start gap-2 md:items-end">
          {cfg ? (
            <div className="flex flex-wrap justify-end gap-2">
              <Badge variant="secondary" className="font-mono text-[10px] tracking-widest">
                {cfg.ollama_host}
              </Badge>
              <Badge variant="outline" className="max-w-[220px] truncate font-mono text-[10px] tracking-wide">
                {cfg.model}
              </Badge>
            </div>
          ) : cfgWaiting ? (
            <Badge variant="ghost" className="font-mono text-[10px]">
              CONFIG…
            </Badge>
          ) : (
            <Badge variant="offline" className="max-w-[240px] truncate font-mono text-[10px]">
              {socketHint ?? "config"}
            </Badge>
          )}
          <Badge variant="outline" className="font-mono text-[10px] tracking-wide">
            mic ring ≈ {ringSec.toFixed(1)}s
          </Badge>
          {pipe ? (
            <Badge variant={pipe.mlx_live_ready ? "default" : "secondary"} className="font-mono text-[10px]">
              mlx {pipe.mlx_live_ready ? "live" : "idle"}
            </Badge>
          ) : (
            <Badge variant="ghost" className="font-mono text-[10px]">
              PIPE…
            </Badge>
          )}
        </div>
      </div>

      <MicHistogram levels={levels.length ? levels : Array.from({ length: 40 }, () => 0)} peak={meterPeak} />

      <Card className="viewport-glass relative overflow-hidden border-primary/25">
        <div className="pointer-events-none absolute right-0 top-0 h-40 w-40 bg-primary/10 blur-3xl" />
        <CardHeader className="relative z-10">
          <CollapsibleCardToggle
            open={liveOpen}
            onToggle={liveToggle}
            controlsId={liveContentId}
            className="absolute right-3 top-3"
          />
          <CardTitle className="font-display text-lg tracking-wide">Live — MLX + Ollama (context)</CardTitle>
          <CardDescription className="text-xs leading-relaxed text-muted-foreground/95">
            {pipe?.mlx_whisper_import_ok === false
              ? pipe?.mlx_whisper_import_error
                ? `mlx_whisper import failed: ${pipe.mlx_whisper_import_error}`
                : "This server cannot import mlx_whisper — reinstall deps (requirements-robot-manage.txt on macOS includes mlx-whisper)."
              : pipe?.mlx_live_ready
                ? "Speak in phrases; the server waits for silence before transcribing and updating the LLM context. Live stream uses WebSocket voice_live messages."
                : "Click Start live — the MLX pipeline starts on first connect when the robot mic ring is active."}
          </CardDescription>
          <Separator className="mt-3 bg-gradient-to-r from-transparent via-primary/30 to-transparent" />
        </CardHeader>
        {liveOpen ? (
          <CardContent id={liveContentId} className="relative z-10 space-y-4">
          <div className="grid gap-4 lg:grid-cols-2 2xl:grid-cols-3 2xl:items-start">
            <div className="min-w-0 space-y-2">
              <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Latest utterance</p>
              <pre className="min-h-[4.5rem] whitespace-pre-wrap break-words rounded-md border border-border/50 bg-black/45 p-3 font-mono text-xs text-foreground/95">
                {listening ? (
                  <span className="text-primary/80">Listening… (end with a short pause)</span>
                ) : lastUtterance ? (
                  lastUtterance
                ) : (
                  <span className="text-muted-foreground/55">Waiting for speech…</span>
                )}
              </pre>
            </div>
            <div className="min-w-0 space-y-2">
              <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Assistant (streaming)</p>
              <pre
                ref={llmPreRef}
                className="max-h-[min(40vh,320px)] min-h-[4.5rem] overflow-y-auto whitespace-pre-wrap break-words rounded-md border border-border/50 bg-black/45 p-3 font-mono text-xs text-foreground/95 2xl:max-h-[min(55vh,480px)]"
              >
                {llmOut || <span className="text-muted-foreground/55">{liveOn ? "…" : "Idle."}</span>}
              </pre>
            </div>
            <div className="min-w-0 space-y-2 lg:col-span-2 2xl:col-span-1">
              <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Ollama conversation context</p>
              <ConversationPanel messages={conversation} />
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="button" className="font-display tracking-[0.14em]" disabled={liveOn} onClick={() => void startLive()}>
              {liveOn ? "LIVE…" : "START LIVE"}
            </Button>
            <Button type="button" variant="outline" disabled={!liveOn} onClick={() => stopLive()}>
              STOP
            </Button>
          </div>
          {liveErr ? <p className="font-mono text-xs text-amber-300/90">{liveErr}</p> : null}
          </CardContent>
        ) : null}
      </Card>
    </section>
  );
}
