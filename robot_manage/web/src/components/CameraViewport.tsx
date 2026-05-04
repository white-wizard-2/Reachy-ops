import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import { PrimaryBrandBlock } from "@/components/PrimaryBrandBlock";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import type { CameraFeedInfo } from "@/types/camera";
import type { YoloDetectionsPayload, YoloVisionState } from "@/types/yoloVision";

function statusBadgeVariant(status: CameraFeedInfo["status"]) {
  if (status === "live") return "live" as const;
  if (status === "offline") return "offline" as const;
  return "ghost" as const;
}

function containTransform(natW: number, natH: number, dispW: number, dispH: number) {
  const scale = Math.min(dispW / natW, dispH / natH);
  const dw = natW * scale;
  const dh = natH * scale;
  const offX = (dispW - dw) * 0.5;
  const offY = (dispH - dh) * 0.5;
  return { scale, offX, offY, dw, dh };
}

function trackHue(id: number): string {
  const golden = 0.618033988749895;
  const h = (id * golden) % 1;
  return `hsl(${Math.round(h * 360)} 85% 52%)`;
}

export function CameraViewport({
  feed,
  className,
  showBrand = false,
  yoloVision,
  yoloDetections,
  yoloFollowEnabled = true,
  cameraEnabled = true,
  onToggleYoloFollow,
}: {
  feed: CameraFeedInfo;
  className?: string;
  showBrand?: boolean;
  yoloVision?: YoloVisionState | null;
  yoloDetections?: YoloDetectionsPayload | null;
  yoloFollowEnabled?: boolean;
  cameraEnabled?: boolean;
  onToggleYoloFollow?: () => void;
}) {
  const showStream = feed.stream_path != null && feed.status === "live";
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const cvRef = useRef<HTMLCanvasElement | null>(null);
  const [drawPayload, setDrawPayload] = useState<YoloDetectionsPayload | null>(null);

  useEffect(() => {
    if (!cameraEnabled || !showStream) {
      setDrawPayload(null);
      return;
    }
    if (yoloDetections == null) {
      return;
    }
    setDrawPayload(yoloDetections);
    const t = window.setTimeout(() => {
      setDrawPayload((cur) => (cur && cur.t_ms === yoloDetections.t_ms ? null : cur));
    }, 650);
    return () => window.clearTimeout(t);
  }, [yoloDetections, cameraEnabled, showStream]);

  const paint = useCallback(() => {
    const cv = cvRef.current;
    const wrap = wrapRef.current;
    if (!cv || !wrap || !drawPayload) {
      if (cv) {
        const c2 = cv.getContext("2d");
        if (c2) c2.clearRect(0, 0, cv.width, cv.height);
      }
      return;
    }
    const dpr = window.devicePixelRatio || 1;
    const [fh, fw] = drawPayload.frame_hw;
    if (fw <= 0 || fh <= 0) return;
    const rect = wrap.getBoundingClientRect();
    const w = Math.max(1, Math.floor(rect.width * dpr));
    const h = Math.max(1, Math.floor(rect.height * dpr));
    if (cv.width !== w || cv.height !== h) {
      cv.width = w;
      cv.height = h;
    }
    const ctx = cv.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, w, h);
    ctx.scale(dpr, dpr);
    const dispW = rect.width;
    const dispH = rect.height;
    const tr = containTransform(fw, fh, dispW, dispH);
    ctx.lineWidth = 2;
    ctx.font = "11px ui-monospace, monospace";
    for (const t of drawPayload.tracks) {
      const [x1, y1, x2, y2] = t.xyxy;
      const sx1 = tr.offX + (x1 / fw) * tr.dw;
      const sy1 = tr.offY + (y1 / fh) * tr.dh;
      const sx2 = tr.offX + (x2 / fw) * tr.dw;
      const sy2 = tr.offY + (y2 / fh) * tr.dh;
      const tid = t.id ?? 0;
      ctx.strokeStyle = trackHue(tid);
      ctx.strokeRect(sx1, sy1, sx2 - sx1, sy2 - sy1);
      const tag = `${t.label}${t.id != null ? ` #${t.id}` : ""} ${(t.conf * 100).toFixed(0)}%`;
      const tw = ctx.measureText(tag).width;
      ctx.fillStyle = "rgba(0,0,0,0.55)";
      ctx.fillRect(sx1, Math.max(0, sy1 - 14), tw + 6, 14);
      ctx.fillStyle = "#e8f7ff";
      ctx.fillText(tag, sx1 + 3, Math.max(10, sy1 - 3));
    }
  }, [drawPayload]);

  useLayoutEffect(() => {
    paint();
  }, [paint]);

  useEffect(() => {
    const ro = new ResizeObserver(() => paint());
    const w = wrapRef.current;
    if (w) ro.observe(w);
    return () => ro.disconnect();
  }, [paint]);

  const yoloActive = Boolean(yoloVision?.worker_running);
  const yoloReady = Boolean(yoloVision?.import_ok && yoloVision?.weights_path);

  return (
    <Card
      className={cn(
        "viewport-glass relative flex h-full min-h-0 flex-col overflow-hidden transition-shadow duration-500",
        showStream && "shadow-[0_0_48px_-8px_hsl(var(--primary)/0.35)]",
        className,
      )}
    >
      <div className="pointer-events-none absolute -right-8 -top-8 h-24 w-24 rounded-full bg-primary/15 blur-2xl" />
      <div className="pointer-events-none absolute -bottom-10 -left-10 h-28 w-28 rounded-full bg-secondary/20 blur-3xl" />
      <CardHeader className="relative z-10 space-y-3 pb-2">
        {showBrand ? (
          <>
            <PrimaryBrandBlock />
            <Separator className="bg-gradient-to-r from-transparent via-primary/20 to-transparent" />
          </>
        ) : null}
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="font-mono text-[10px] font-medium uppercase tracking-[0.35em] text-primary/80">
              {feed.channel}
            </p>
            <CardTitle className="font-display text-lg tracking-wide md:text-xl">{feed.label}</CardTitle>
            <CardDescription className="font-mono text-xs text-muted-foreground/90">
              Robot camera (MJPEG) · YOLO-MLX ByteTrack overlay
            </CardDescription>
            {yoloVision != null ? (
              <p className="mt-1 max-w-prose font-mono text-[10px] leading-relaxed text-muted-foreground">
                {yoloActive
                  ? `${drawPayload?.tracks.length ?? 0} track(s) · frame ${drawPayload?.frame_hw[1] ?? "—"}×${drawPayload?.frame_hw[0] ?? "—"}`
                  : yoloReady
                    ? "Weights configured — worker not running (check server logs)."
                    : yoloVision.import_ok
                      ? "Set ROBOT_MANAGE_YOLO_NPZ to a converted .npz on the Mac host."
                      : "Install yolo-mlx on the Apple Silicon host (see requirements-robot-manage-yolo.txt)."}
              </p>
            ) : null}
          </div>
          <div className="flex flex-col items-end gap-2">
            <Badge variant={statusBadgeVariant(feed.status)} className="font-mono uppercase tracking-wider">
              {feed.status}
            </Badge>
            {onToggleYoloFollow != null && yoloVision != null && yoloVision.import_ok && yoloVision.weights_path ? (
              <Button
                type="button"
                size="sm"
                variant={yoloFollowEnabled ? "secondary" : "outline"}
                className="font-mono text-[10px] uppercase tracking-wider"
                disabled={!yoloActive}
                title={
                  yoloActive
                    ? "Steer head toward moving tracked objects (ByteTrack + look_at_image)"
                    : "YOLO worker must be running"
                }
                onClick={() => onToggleYoloFollow()}
              >
                Follow track {yoloFollowEnabled ? "on" : "off"}
              </Button>
            ) : null}
          </div>
        </div>
        <Separator className="bg-gradient-to-r from-transparent via-primary/25 to-transparent" />
      </CardHeader>
      <CardContent className="relative z-10 flex min-h-0 flex-1 flex-col px-4 pb-4 pt-0 md:px-6 md:pb-6">
        <div
          ref={wrapRef}
          className={cn(
            "relative w-full shrink-0 overflow-hidden rounded-lg border border-border/60 bg-black/80",
            showStream ? "aspect-video" : "min-h-0 flex-1",
          )}
        >
          {showStream ? (
            <>
              <div className="viewport-scanlines absolute inset-0 z-10 rounded-lg" />
              <img
                src={feed.stream_path!}
                alt={feed.label}
                className="absolute inset-0 z-0 h-full w-full object-contain"
                onLoad={paint}
              />
              <canvas
                ref={cvRef}
                className="pointer-events-none absolute inset-0 z-[5] h-full w-full"
                aria-hidden
              />
              <div className="pointer-events-none absolute inset-0 rounded-lg ring-1 ring-inset ring-primary/20" />
            </>
          ) : (
            <Placeholder detail={feed.detail} channel={feed.channel} />
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function Placeholder({ detail, channel }: { detail: string | null; channel: string }) {
  return (
    <div className="relative flex h-full min-h-[12rem] flex-col items-center justify-center gap-4 bg-[radial-gradient(ellipse_at_center,_hsl(var(--secondary)/0.12)_0%,_transparent_65%)] p-6 text-center">
      <div className="absolute inset-0 bg-grid-fade bg-[length:24px_24px] opacity-60" />
      <div className="pointer-events-none absolute inset-0 overflow-hidden rounded-lg">
        <div className="absolute left-0 top-0 h-px w-full animate-scan bg-gradient-to-r from-transparent via-primary/50 to-transparent opacity-40" />
      </div>
      <div className="relative z-10 space-y-2">
        <p className="font-display text-2xl font-semibold tracking-[0.2em] text-glow md:text-3xl">NO SIGNAL</p>
        <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">{channel} — idle</p>
      </div>
      {detail ? (
        <p className="relative z-10 max-w-md font-sans text-sm leading-relaxed text-muted-foreground">{detail}</p>
      ) : null}
    </div>
  );
}
