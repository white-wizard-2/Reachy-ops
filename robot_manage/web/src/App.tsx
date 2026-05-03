import { useCallback, useEffect, useState } from "react";

import { CameraViewport } from "@/components/CameraViewport";
import { VoiceCognition } from "@/components/VoiceCognition";
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

export default function App() {
  const [layout, setLayout] = useState<CameraLayoutResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

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

  const feeds = layout?.feeds ?? [];

  return (
    <div className="relative min-h-screen overflow-hidden">
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(ellipse_120%_80%_at_50%_-20%,hsl(var(--primary)/0.14),transparent_50%),radial-gradient(ellipse_80%_50%_at_100%_50%,hsl(var(--secondary)/0.12),transparent_45%),radial-gradient(ellipse_60%_40%_at_0%_80%,hsl(var(--accent)/0.08),transparent_40%)]" />
      <div className="pointer-events-none fixed inset-0 bg-grid-fade bg-[length:32px_32px] opacity-[0.35]" />

      <div className="relative z-10 mx-auto max-w-7xl px-4 py-8 md:px-8 md:py-12">
        <header className="mb-10 flex flex-col gap-6 md:mb-14 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="mb-2 font-mono text-[11px] font-medium uppercase tracking-[0.5em] text-primary/70">
              Pollen robotics
            </p>
            <h1 className="font-display text-3xl font-bold tracking-tight text-glow md:text-4xl lg:text-5xl">
              REACHY<span className="text-primary"> // </span>OPS
            </h1>
            <p className="mt-3 max-w-xl font-sans text-sm text-muted-foreground md:text-base">
              Neural ops console — vision multiplex, robot microphone → MLX Whisper (silence-segmented) → Ollama
              /api/chat with conversation context and streamed replies. Dual camera tiles stay reserved for future stereo;
              simulators expose one video lane.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Badge variant="outline" className="font-mono text-[10px] tracking-widest">
              {loading ? "SYNC…" : layout?.sdk_single_stream ? "SINGLE MUX" : "MULTI"}
            </Badge>
            <Button variant="outline" size="sm" className="font-mono text-xs uppercase tracking-wider" onClick={() => void load()}>
              Resync layout
            </Button>
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

        <div className="grid gap-6 lg:grid-cols-2 lg:gap-8">
          {feeds.length > 0
            ? feeds.map((f) => <CameraViewport key={f.id} feed={f} />)
            : !loading && (
                <Card className="viewport-glass lg:col-span-2">
                  <CardHeader>
                    <CardTitle className="font-display">Waiting for robot</CardTitle>
                    <CardDescription className="font-mono text-xs">
                      {layout?.error === "robot_not_ready"
                        ? "Media daemon handshake pending."
                        : "No feed metadata from server."}
                    </CardDescription>
                  </CardHeader>
                </Card>
              )}
        </div>

        <Separator className="my-12 bg-gradient-to-r from-transparent via-primary/20 to-transparent md:my-16" />

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
