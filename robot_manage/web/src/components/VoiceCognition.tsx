import { useCallback, useEffect, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";

type LlmConfig = { model: string; ollama_host: string };

type VoiceStatus = { buffering: boolean; buffered_seconds_estimate: number };

type MeterPayload = { levels: number[]; peak: number };

type PipeInfo = {
  mlx_whisper_import_ok: boolean;
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
  | { event: "error"; message: string };

function parseSseBuffer(buffer: string): { events: SsePayload[]; rest: string } {
  const events: SsePayload[] = [];
  const parts = buffer.split("\n\n");
  const rest = parts.pop() ?? "";
  for (const block of parts) {
    for (const raw of block.split("\n")) {
      const line = raw.trim();
      if (!line.startsWith("data:")) continue;
      const json = line.slice(5).trim();
      try {
        events.push(JSON.parse(json) as SsePayload);
      } catch {
        /* ignore */
      }
    }
  }
  return { events, rest };
}

async function fetchLlmConfig(): Promise<LlmConfig> {
  const res = await fetch("/api/llm/config");
  if (!res.ok) throw new Error(`llm config ${res.status}`);
  return res.json() as Promise<LlmConfig>;
}

async function fetchVoiceStatus(): Promise<VoiceStatus> {
  const res = await fetch("/api/voice/status");
  if (!res.ok) throw new Error(`voice status ${res.status}`);
  return res.json() as Promise<VoiceStatus>;
}

async function fetchVoiceMeter(bars: number): Promise<MeterPayload> {
  const res = await fetch(`/api/voice/meter?bars=${bars}`);
  if (!res.ok) throw new Error(`meter ${res.status}`);
  return res.json() as Promise<MeterPayload>;
}

async function fetchVoicePipeline(): Promise<PipeInfo> {
  const res = await fetch("/api/voice/pipeline");
  if (!res.ok) throw new Error(`voice pipeline ${res.status}`);
  return res.json() as Promise<PipeInfo>;
}

async function fetchVoiceConversation(): Promise<ChatMessage[]> {
  const res = await fetch("/api/voice/conversation");
  if (!res.ok) return [];
  const j = (await res.json()) as { messages?: ChatMessage[] };
  return Array.isArray(j.messages) ? j.messages : [];
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
    <div className="max-h-[min(48vh,420px)] space-y-2 overflow-y-auto rounded-md border border-border/50 bg-black/40 p-3">
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
            <pre className="whitespace-pre-wrap break-words">{m.content}</pre>
          </div>
        ))
      )}
    </div>
  );
}

export function VoiceCognition() {
  const [cfg, setCfg] = useState<LlmConfig | null>(null);
  const [cfgErr, setCfgErr] = useState<string | null>(null);
  const [pipe, setPipe] = useState<PipeInfo | null>(null);
  const [pipeErr, setPipeErr] = useState<string | null>(null);
  const [ringSec, setRingSec] = useState(0);
  const [lastUtterance, setLastUtterance] = useState("");
  const [listening, setListening] = useState(false);
  const [conversation, setConversation] = useState<ChatMessage[]>([]);
  const [llmOut, setLlmOut] = useState("");
  const [liveErr, setLiveErr] = useState<string | null>(null);
  const [liveOn, setLiveOn] = useState(false);
  const liveAbortRef = useRef<AbortController | null>(null);
  const [levels, setLevels] = useState<number[]>([]);
  const [meterPeak, setMeterPeak] = useState(0);
  const llmPreRef = useRef<HTMLPreElement>(null);
  const liveOnRef = useRef(false);
  const voiceResumeRef = useRef(false);
  const [uiHydrated, setUiHydrated] = useState(false);

  useEffect(() => {
    liveOnRef.current = liveOn;
  }, [liveOn]);

  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(VOICE_SESSION_UI);
      if (raw) {
        const u = JSON.parse(raw) as { lastUtterance?: string; llmOut?: string; conversation?: ChatMessage[] };
        if (typeof u.lastUtterance === "string") setLastUtterance(u.lastUtterance);
        if (typeof u.llmOut === "string") setLlmOut(u.llmOut);
        if (Array.isArray(u.conversation) && u.conversation.length > 0) setConversation(u.conversation);
      }
    } catch {
      /* private mode or corrupt */
    }
    void (async () => {
      const server = await fetchVoiceConversation();
      if (server.length > 0) setConversation(server);
      setUiHydrated(true);
    })();
  }, []);

  useEffect(() => {
    if (!uiHydrated) return;
    const id = window.setTimeout(() => {
      try {
        sessionStorage.setItem(VOICE_SESSION_UI, JSON.stringify({ lastUtterance, llmOut, conversation }));
      } catch {
        /* ignore */
      }
    }, 300);
    return () => window.clearTimeout(id);
  }, [uiHydrated, lastUtterance, llmOut, conversation]);

  useEffect(() => {
    void (async () => {
      try {
        setCfg(await fetchLlmConfig());
      } catch (e) {
        setCfgErr(e instanceof Error ? e.message : "config");
      }
    })();
  }, []);

  useEffect(() => {
    void (async () => {
      try {
        setPipe(await fetchVoicePipeline());
      } catch (e) {
        setPipeErr(e instanceof Error ? e.message : "pipeline");
      }
    })();
  }, []);

  useEffect(() => {
    const id = window.setInterval(() => {
      void fetchVoicePipeline()
        .then((p) => setPipe(p))
        .catch(() => {});
    }, 4000);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    const id = window.setInterval(() => {
      void (async () => {
        try {
          const s = await fetchVoiceStatus();
          setRingSec(s.buffered_seconds_estimate);
        } catch {
          setRingSec(0);
        }
      })();
    }, 1500);
    void fetchVoiceStatus().then((s) => setRingSec(s.buffered_seconds_estimate));
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    const id = window.setInterval(() => {
      void (async () => {
        try {
          const m = await fetchVoiceMeter(40);
          setLevels(m.levels);
          setMeterPeak(m.peak);
        } catch {
          setLevels([]);
          setMeterPeak(0);
        }
      })();
    }, 90);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    if (llmPreRef.current) llmPreRef.current.scrollTop = llmPreRef.current.scrollHeight;
  }, [llmOut]);

  const stopLive = useCallback(() => {
    liveAbortRef.current?.abort();
    liveAbortRef.current = null;
    liveOnRef.current = false;
    setLiveOn(false);
    setListening(false);
    try {
      sessionStorage.setItem(VOICE_SESSION_LIVE, "0");
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    return () => {
      liveAbortRef.current?.abort();
    };
  }, []);

  const startLive = useCallback(async () => {
    if (liveOnRef.current) return;
    liveOnRef.current = true;
    setLiveErr(null);
    setListening(false);
    setLiveOn(true);
    const ac = new AbortController();
    liveAbortRef.current = ac;
    try {
      const sync = await fetchVoiceConversation();
      if (sync.length > 0) setConversation(sync);
      const res = await fetch("/api/voice/live", { signal: ac.signal });
      if (!res.ok || !res.body) {
        const detail = (await res.text()).trim();
        throw new Error(detail || `live ${res.status}`);
      }
      try {
        sessionStorage.setItem(VOICE_SESSION_LIVE, "1");
      } catch {
        /* ignore */
      }
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let carry = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        carry += dec.decode(value, { stream: true });
        const { events, rest } = parseSseBuffer(carry);
        carry = rest;
        for (const ev of events) {
          if (ev.event === "utterance_start") setListening(true);
          if (ev.event === "utterance_end") {
            setListening(false);
            setLastUtterance(ev.text);
          }
          if (ev.event === "conversation") setConversation(ev.messages);
          if (ev.event === "llm_round_start") setLlmOut("");
          if (ev.event === "llm_token") setLlmOut((o) => o + ev.t);
          if (ev.event === "error") setLiveErr(ev.message);
        }
      }
      const tail = parseSseBuffer(carry + "\n\n");
      for (const ev of tail.events) {
        if (ev.event === "utterance_start") setListening(true);
        if (ev.event === "utterance_end") {
          setListening(false);
          setLastUtterance(ev.text);
        }
        if (ev.event === "conversation") setConversation(ev.messages);
        if (ev.event === "llm_round_start") setLlmOut("");
        if (ev.event === "llm_token") setLlmOut((o) => o + ev.t);
        if (ev.event === "error") setLiveErr(ev.message);
      }
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        setLiveErr(e instanceof Error ? e.message : "live failed");
      }
    } finally {
      liveOnRef.current = false;
      setLiveOn(false);
      setListening(false);
      liveAbortRef.current = null;
      void fetchVoicePipeline()
        .then((p) => setPipe(p))
        .catch(() => {});
    }
  }, []);

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
    void startLive();
  }, [pipe?.mlx_live_ready, startLive]);

  return (
    <section className="mt-14 space-y-6 md:mt-20">
      <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="font-mono text-[10px] font-medium uppercase tracking-[0.45em] text-secondary/90">
            cognition layer
          </p>
          <h2 className="font-display text-2xl font-bold tracking-wide text-glow md:text-3xl">VOICE · COGNITION</h2>
          <p className="mt-1 max-w-2xl font-sans text-sm text-muted-foreground">
            MLX Whisper segments speech by <strong className="text-foreground/90">silence</strong> (see{" "}
            <code className="font-mono text-[10px]">MLX_VOICE_*</code> env in run script), then sends each utterance to
            Ollama <code className="font-mono text-[10px]">/api/chat</code> with <strong className="text-foreground/90">full conversation context</strong>.
            Default model repo:{" "}
            <code className="font-mono text-[10px]">mlx-community/whisper-large-v3-mlx</code>.
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
          ) : cfgErr ? (
            <Badge variant="offline" className="font-mono text-[10px]">
              {cfgErr}
            </Badge>
          ) : (
            <Badge variant="ghost" className="font-mono text-[10px]">
              CONFIG…
            </Badge>
          )}
          <Badge variant="outline" className="font-mono text-[10px] tracking-wide">
            mic ring ≈ {ringSec.toFixed(1)}s
          </Badge>
          {pipe ? (
            <Badge variant={pipe.mlx_live_ready ? "default" : "secondary"} className="font-mono text-[10px]">
              mlx {pipe.mlx_live_ready ? "live" : "idle"}
            </Badge>
          ) : pipeErr ? (
            <Badge variant="offline" className="font-mono text-[10px]">
              {pipeErr}
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
          <CardTitle className="font-display text-lg tracking-wide">Live — MLX + Ollama (context)</CardTitle>
          <CardDescription className="text-xs leading-relaxed text-muted-foreground/95">
            {pipe?.mlx_whisper_import_ok === false
              ? "This server cannot import mlx_whisper — install Apple Silicon deps (requirements-robot-manage-mlx.txt)."
              : pipe?.mlx_live_ready
                ? "Speak in phrases; the server waits for silence before transcribing and updating the LLM context. Refresh restores Ollama context from the server when the session is still up; live reconnects if it was left on."
                : "Click Start live — the MLX pipeline starts on first connect when the robot mic ring is active."}
          </CardDescription>
          <Separator className="mt-3 bg-gradient-to-r from-transparent via-primary/30 to-transparent" />
        </CardHeader>
        <CardContent className="relative z-10 space-y-4">
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="space-y-2">
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
            <div className="space-y-2">
              <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Assistant (streaming)</p>
              <pre
                ref={llmPreRef}
                className="max-h-[min(28vh,240px)] min-h-[4.5rem] overflow-y-auto whitespace-pre-wrap break-words rounded-md border border-border/50 bg-black/45 p-3 font-mono text-xs text-foreground/95"
              >
                {llmOut || <span className="text-muted-foreground/55">{liveOn ? "…" : "Idle."}</span>}
              </pre>
            </div>
          </div>
          <div className="space-y-2">
            <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Ollama conversation context</p>
            <ConversationPanel messages={conversation} />
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
      </Card>
    </section>
  );
}
