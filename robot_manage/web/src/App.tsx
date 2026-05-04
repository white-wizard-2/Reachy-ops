import { useCallback, useEffect, useMemo, useState } from "react";

import { CameraViewport } from "@/components/CameraViewport";
import { ModesToolsPanel } from "@/components/ModesToolsPanel";
import { REACHY_MODES_TOOLS_EVENT, VoiceCognition } from "@/components/VoiceCognition";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import type { CameraLayoutResponse } from "@/types/camera";

async function fetchLayout(): Promise<CameraLayoutResponse> {
  const res = await fetch("/api/camera/layout");
  if (!res.ok) {
    throw new Error(`layout ${res.status}`);
  }
  return res.json() as Promise<CameraLayoutResponse>;
}

async function fetchModesTools(): Promise<{ mode: string | null; tools: string[] }> {
  const res = await fetch("/api/voice/modes-tools");
  if (!res.ok) return { mode: null, tools: [] };
  const j = (await res.json()) as { mode?: string | null; tools?: string[] };
  return { mode: j.mode ?? null, tools: Array.isArray(j.tools) ? j.tools : [] };
}

export default function App() {
  const [layout, setLayout] = useState<CameraLayoutResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [modesTools, setModesTools] = useState<{ mode: string | null; tools: string[] }>({
    mode: null,
    tools: [],
  });

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const data = await fetchLayout();
      setLayout(data);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "failed");
      setLayout(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    void fetchModesTools().then(setModesTools);
  }, []);

  useEffect(() => {
    const onMt = (e: Event) => {
      const ce = e as CustomEvent<{ mode: string | null; tools: string[] }>;
      if (ce.detail) setModesTools({ mode: ce.detail.mode, tools: ce.detail.tools });
    };
    window.addEventListener(REACHY_MODES_TOOLS_EVENT, onMt);
    return () => window.removeEventListener(REACHY_MODES_TOOLS_EVENT, onMt);
  }, []);

  const persistModesTools = useCallback(async (next: { mode: string | null; tools: string[] }) => {
    setModesTools(next);
    try {
      const res = await fetch("/api/voice/modes-tools", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(next),
      });
      if (!res.ok) void fetchModesTools().then(setModesTools);
    } catch {
      void fetchModesTools().then(setModesTools);
    }
  }, []);

  const toolsOnSet = useMemo(() => new Set(modesTools.tools), [modesTools.tools]);

  const feeds = layout?.feeds ?? [];
  const primaryFeed = feeds[0];

  return (
    <div className="relative min-h-screen overflow-hidden">
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(ellipse_120%_80%_at_50%_-20%,hsl(var(--primary)/0.14),transparent_50%),radial-gradient(ellipse_80%_50%_at_100%_50%,hsl(var(--secondary)/0.12),transparent_45%),radial-gradient(ellipse_60%_40%_at_0%_80%,hsl(var(--accent)/0.08),transparent_40%)]" />
      <div className="pointer-events-none fixed inset-0 bg-grid-fade bg-[length:32px_32px] opacity-[0.35]" />

      <div className="relative z-10 w-full px-4 py-8 sm:px-6 md:py-12 lg:px-10 xl:px-12">
        <header className="mb-10 md:mb-14">
          <div className="flex flex-col gap-4 lg:grid lg:grid-cols-[minmax(0,22rem)_1fr] lg:items-start lg:gap-x-8 xl:grid-cols-[minmax(0,24rem)_1fr]">
            <div className="order-1 flex min-w-0 flex-col gap-3 lg:order-1">
              <div>
                <p className="mb-2 font-mono text-[11px] font-medium uppercase tracking-[0.5em] text-primary/70">
                  WHITE WIZARDRY
                </p>
                <h1 className="font-display text-3xl font-bold tracking-tight text-glow md:text-4xl lg:text-5xl">
                  REACHY<span className="text-primary"> // </span>OPS
                </h1>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <Badge variant="outline" className="font-mono text-[10px] tracking-widest">
                  {loading ? "SYNC…" : layout?.sdk_single_stream ? "SINGLE MUX" : "MULTI"}
                </Badge>
                <Button
                  variant="outline"
                  size="sm"
                  className="font-mono text-xs uppercase tracking-wider"
                  onClick={() => void load()}
                >
                  Resync layout
                </Button>
              </div>
              <p className="font-sans text-sm text-muted-foreground md:text-base">
                Neural ops console — robot camera, microphone → MLX Whisper (silence-segmented) → Ollama /api/chat with
                conversation context and streamed replies.
              </p>
            </div>
            <div className="order-2 flex min-h-0 w-full min-w-0 flex-col gap-4 lg:order-2 lg:grid lg:min-h-0 lg:grid-cols-[1fr_min(100%,30rem)] lg:items-stretch lg:gap-x-6 xl:gap-x-8">
              <div className="flex h-full min-h-0 min-w-0">
                <ModesToolsPanel
                  className="w-full min-w-0"
                  activeMode={modesTools.mode}
                  toolsOn={toolsOnSet}
                  onActiveModeChange={(m) => void persistModesTools({ mode: m, tools: modesTools.tools })}
                  onToolsOnChange={(s) => void persistModesTools({ mode: modesTools.mode, tools: [...s] })}
                />
              </div>
              <div className="flex h-full min-h-0 min-w-0">
                {loading ? (
                  <Card className="viewport-glass flex h-full min-h-0 w-full flex-col">
                    <CardHeader className="shrink-0 pb-2">
                      <CardTitle className="font-display text-base">Primary optical</CardTitle>
                      <CardDescription className="font-mono text-xs">Loading layout…</CardDescription>
                    </CardHeader>
                    <CardContent className="flex min-h-0 flex-1 flex-col">
                      <div className="aspect-video w-full shrink-0 animate-pulse rounded-lg bg-muted/30" />
                    </CardContent>
                  </Card>
                ) : primaryFeed ? (
                  <CameraViewport feed={primaryFeed} className="w-full min-w-0" />
                ) : (
                  <Card className="viewport-glass flex h-full min-h-0 w-full min-w-0 flex-col">
                    <CardHeader className="shrink-0 pb-2">
                      <CardTitle className="font-display text-base">Primary optical</CardTitle>
                      <CardDescription className="font-mono text-xs">
                        {layout?.error === "robot_not_ready"
                          ? "Media daemon handshake pending."
                          : "No feed metadata from server."}
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="flex min-h-0 flex-1 flex-col">
                      <div className="min-h-0 flex-1 rounded-lg border border-dashed border-border/60 bg-muted/20" />
                    </CardContent>
                  </Card>
                )}
              </div>
            </div>
          </div>
        </header>

        {err ? (
          <Card className="viewport-glass mb-8 border-destructive/40">
            <CardHeader>
              <CardTitle className="font-display text-destructive">Telemetry fault</CardTitle>
              <CardDescription className="font-mono text-xs">{err}</CardDescription>
            </CardHeader>
            <CardContent>
              <Button variant="default" onClick={() => void load()}>
                Retry
              </Button>
            </CardContent>
          </Card>
        ) : null}

        <Separator className="my-10 bg-gradient-to-r from-transparent via-primary/20 to-transparent md:my-14" />

        <VoiceCognition />

        <footer className="mt-14 md:mt-20">
          <Separator className="mb-8 bg-gradient-to-r from-transparent via-border to-transparent" />
          <p className="text-center font-mono text-[10px] uppercase tracking-[0.4em] text-muted-foreground/70">
            robot_manage · vision + ollama voice
          </p>
        </footer>
      </div>
    </div>
  );
}
