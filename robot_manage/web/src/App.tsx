import { useCallback, useMemo } from "react";

import { useAppSocket } from "@/AppSocketContext";
import { CameraViewport } from "@/components/CameraViewport";
import { ModesToolsPanel } from "@/components/ModesToolsPanel";
import { PrimaryBrandBlock } from "@/components/PrimaryBrandBlock";
import { RobotStatePanel } from "@/components/RobotStatePanel";
import { VoiceCognition } from "@/components/VoiceCognition";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

export default function App() {
  const { state, send } = useAppSocket();
  const layout = state.layout;
  const loading = !state.connected || layout === null;
  const err = layout?.error && layout.error !== "robot_not_ready" ? layout.error : null;

  const persistModesTools = useCallback(
    (next: { mode: string | null; tools: string[] }) => {
      send({ type: "modes_tools_set", mode: next.mode, tools: next.tools });
    },
    [send],
  );

  const toolsOnSet = useMemo(() => new Set(state.modesTools.tools), [state.modesTools.tools]);

  const feeds = layout?.feeds ?? [];
  const primaryFeed = feeds[0];

  const primaryOptical = (
    <>
      {loading ? (
        <Card className="viewport-glass flex h-full min-h-0 w-full min-w-0 flex-col">
          <CardHeader className="shrink-0 space-y-3 pb-2">
            <PrimaryBrandBlock />
            <Separator className="bg-gradient-to-r from-transparent via-primary/20 to-transparent" />
            <CardTitle className="font-display text-base">Primary optical</CardTitle>
            <CardDescription className="font-mono text-xs">
              {!state.connected ? "Connecting WebSocket…" : "Loading layout…"}
            </CardDescription>
          </CardHeader>
          <CardContent className="flex min-h-0 flex-1 flex-col">
            <div className="aspect-video w-full shrink-0 animate-pulse rounded-lg bg-muted/30" />
          </CardContent>
        </Card>
      ) : primaryFeed ? (
        <CameraViewport
          feed={primaryFeed}
          showBrand
          className="h-full min-h-0 w-full min-w-0"
          yoloVision={state.yoloVision}
          yoloDetections={state.yoloDetections}
          yoloFollowEnabled={state.deviceControls.yolo_follow_enabled}
          cameraEnabled={state.deviceControls.camera_enabled}
          onToggleYoloFollow={() => send({ type: "device_toggle", device: "yolo_follow" })}
        />
      ) : (
        <Card className="viewport-glass flex h-full min-h-0 w-full min-w-0 flex-col">
          <CardHeader className="shrink-0 space-y-3 pb-2">
            <PrimaryBrandBlock />
            <Separator className="bg-gradient-to-r from-transparent via-primary/20 to-transparent" />
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
    </>
  );

  return (
    <div className="relative min-h-screen overflow-hidden">
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(ellipse_120%_80%_at_50%_-20%,hsl(var(--primary)/0.14),transparent_50%),radial-gradient(ellipse_80%_50%_at_100%_50%,hsl(var(--secondary)/0.12),transparent_45%),radial-gradient(ellipse_60%_40%_at_0%_80%,hsl(var(--accent)/0.08),transparent_40%)]" />
      <div className="pointer-events-none fixed inset-0 bg-grid-fade bg-[length:32px_32px] opacity-[0.35]" />

      <div className="relative z-10 w-full px-4 py-8 sm:px-6 md:py-12 lg:px-10 xl:px-12">
        <header className="mb-4 md:mb-5">
          <div className="grid min-h-0 grid-cols-1 items-stretch gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_min(100%,30%)] lg:gap-6 xl:gap-8">
            <div className="flex min-h-0 min-w-0 flex-col lg:min-h-[min(42vh,20rem)]">
              {primaryOptical}
            </div>
            <div className="flex min-h-0 min-w-0 flex-col lg:min-h-0">
              <RobotStatePanel robotState={state.robotState} className="min-h-0 flex-1" />
            </div>
            <div className="flex min-h-0 min-w-0 w-full max-w-full flex-col lg:w-full">
              <ModesToolsPanel
                className="h-full min-h-0 w-full min-w-0"
                activeMode={state.modesTools.mode}
                toolsOn={toolsOnSet}
                onActiveModeChange={(m) => void persistModesTools({ mode: m, tools: state.modesTools.tools })}
                onToolsOnChange={(s) => void persistModesTools({ mode: state.modesTools.mode, tools: [...s] })}
              />
            </div>
          </div>
        </header>

        {err ? (
          <Card className="viewport-glass mb-8 border-destructive/40">
            <CardHeader>
              <CardTitle className="font-display text-destructive">Telemetry fault</CardTitle>
              <CardDescription className="font-mono text-xs">{err}</CardDescription>
            </CardHeader>
          </Card>
        ) : null}

        <Separator className="my-4 bg-gradient-to-r from-transparent via-primary/20 to-transparent md:my-5" />

        <VoiceCognition />

        <footer className="mt-14 md:mt-20">
          <Separator className="mb-8 bg-gradient-to-r from-transparent via-border to-transparent" />
          <p className="text-center font-mono text-[10px] uppercase tracking-[0.4em] text-muted-foreground/70">
            REACHY // OPS - White Wizardry          </p>
        </footer>
      </div>
    </div>
  );
}
