import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import type { CameraFeedInfo } from "@/types/camera";

function statusBadgeVariant(status: CameraFeedInfo["status"]) {
  if (status === "live") return "live" as const;
  if (status === "offline") return "offline" as const;
  return "ghost" as const;
}

export function CameraViewport({ feed }: { feed: CameraFeedInfo }) {
  const showStream = feed.stream_path != null && feed.status === "live";
  const showPlaceholder = !showStream;

  return (
    <Card
      className={cn(
        "viewport-glass relative overflow-hidden transition-shadow duration-500",
        showStream && "shadow-[0_0_48px_-8px_hsl(var(--primary)/0.35)]",
      )}
    >
      <div className="pointer-events-none absolute -right-8 -top-8 h-24 w-24 rounded-full bg-primary/15 blur-2xl" />
      <div className="pointer-events-none absolute -bottom-10 -left-10 h-28 w-28 rounded-full bg-secondary/20 blur-3xl" />
      <CardHeader className="relative z-10 space-y-3 pb-2">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="font-mono text-[10px] font-medium uppercase tracking-[0.35em] text-primary/80">
              {feed.channel}
            </p>
            <CardTitle className="font-display text-lg tracking-wide md:text-xl">{feed.label}</CardTitle>
            <CardDescription className="font-mono text-xs text-muted-foreground/90">
              {feed.id === "primary" ? "Main scene tensor" : "Reserved stereoscopic lane"}
            </CardDescription>
          </div>
          <Badge variant={statusBadgeVariant(feed.status)} className="font-mono uppercase tracking-wider">
            {feed.status}
          </Badge>
        </div>
        <Separator className="bg-gradient-to-r from-transparent via-primary/25 to-transparent" />
      </CardHeader>
      <CardContent className="relative z-10 px-4 pb-4 pt-0 md:px-6 md:pb-6">
        <div
          className={cn(
            "relative overflow-hidden rounded-lg border border-border/60 bg-black/80",
            "aspect-video w-full",
          )}
        >
          {showStream ? (
            <>
              <div className="viewport-scanlines absolute inset-0 z-10 rounded-lg" />
              <img
                src={feed.stream_path!}
                alt={feed.label}
                className="relative z-0 h-full w-full object-contain"
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
    <div className="relative flex h-full min-h-[200px] flex-col items-center justify-center gap-4 bg-[radial-gradient(ellipse_at_center,_hsl(var(--secondary)/0.12)_0%,_transparent_65%)] p-6 text-center md:min-h-[240px]">
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
