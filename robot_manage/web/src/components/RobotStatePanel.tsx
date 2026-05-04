import { useMemo, type ReactNode } from "react";

import type { RobotStateMsg } from "@/AppSocketContext";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";

function asFiniteNumber(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/** `2026-05-04T08:02:57.772182+00:00` or `...777884Z` → `2026-05-04 08:02:57`. */
function formatCompactTs(raw: string): string {
  const m = raw.match(/^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})/);
  if (m) return `${m[1]} ${m[2]}`;
  return raw;
}

type HeadPose = {
  x: number;
  y: number;
  z: number;
  roll: number;
  pitch: number;
  yaw: number;
};

function parseHeadPose(v: unknown): HeadPose | null {
  if (typeof v !== "object" || v === null) return null;
  const o = v as Record<string, unknown>;
  const x = asFiniteNumber(o.x);
  const y = asFiniteNumber(o.y);
  const z = asFiniteNumber(o.z);
  const roll = asFiniteNumber(o.roll);
  const pitch = asFiniteNumber(o.pitch);
  const yaw = asFiniteNumber(o.yaw);
  if (x === null || y === null || z === null || roll === null || pitch === null || yaw === null) return null;
  return { x, y, z, roll, pitch, yaw };
}

function parseNumberArray(v: unknown): number[] | null {
  if (!Array.isArray(v)) return null;
  const out: number[] = [];
  for (const x of v) {
    const n = asFiniteNumber(x);
    if (n === null) return null;
    out.push(n);
  }
  return out;
}

const cellFrame =
  "min-w-0 border-b border-border/30 py-1.5 font-mono text-[10px] leading-snug md:text-[11px]";

/** Positive → green, negative → red, zero → default; null → em dash. */
function SignedNumber({
  value,
  digits = 4,
  align = "inline",
}: {
  value: number | null;
  digits?: number;
  align?: "end" | "center" | "inline";
}) {
  if (align === "inline") {
    if (value === null || !Number.isFinite(value)) {
      return <span className="inline tabular-nums text-muted-foreground">—</span>;
    }
    const text = value.toFixed(digits);
    if (value > 0) {
      return <span className="inline tabular-nums text-emerald-400">{text}</span>;
    }
    if (value < 0) {
      return <span className="inline tabular-nums text-red-400">{text}</span>;
    }
    return <span className="inline tabular-nums text-foreground/90">{text}</span>;
  }

  const alignCls = align === "center" ? "text-center" : "text-right";
  if (value === null || !Number.isFinite(value)) {
    return <span className={cn("tabular-nums", alignCls, "text-muted-foreground")}>—</span>;
  }
  const text = value.toFixed(digits);
  if (value > 0) {
    return <span className={cn("tabular-nums", alignCls, "text-emerald-400")}>{text}</span>;
  }
  if (value < 0) {
    return <span className={cn("tabular-nums", alignCls, "text-red-400")}>{text}</span>;
  }
  return <span className={cn("tabular-nums", alignCls, "text-foreground/90")}>{text}</span>;
}

function KvNeutral({ children, danger }: { children: ReactNode; danger?: boolean }) {
  return (
    <span className={cn("break-all text-foreground/90", danger && "text-destructive")}>{children}</span>
  );
}

/** Single cell: `key` · `value` on one line (same UI as before: muted key, colored / neutral value). */
function KvInline({ k, children, nowrap }: { k: string; children: ReactNode; nowrap?: boolean }) {
  return (
    <div
      className={cn(
        cellFrame,
        nowrap && "overflow-x-auto whitespace-nowrap",
      )}
    >
      <span className="text-muted-foreground">{k}</span>
      <span className="px-1.5 text-muted-foreground/45">·</span>
      <span className="inline align-baseline">{children}</span>
    </div>
  );
}

/** Three columns per row; fills row-wise. */
function TriGrid({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-3 gap-x-2 gap-y-0">{children}</div>;
}

function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <p className="font-mono text-[10px] font-medium uppercase tracking-[0.35em] text-muted-foreground/90">{children}</p>
  );
}

export function RobotStatePanel({
  robotState,
  className,
}: {
  robotState: RobotStateMsg | null;
  className?: string;
}) {
  const parsed = useMemo(() => {
    const data = robotState?.data;
    if (!data || typeof data !== "object") return null;
    const d = data as Record<string, unknown>;
    const controlMode = typeof d.control_mode === "string" ? d.control_mode : null;
    const pose = parseHeadPose(d.head_pose);
    const headJoints = parseNumberArray(d.head_joints);
    const bodyYaw = asFiniteNumber(d.body_yaw);
    const antennas = parseNumberArray(d.antennas_position);
    const ts = typeof d.timestamp === "string" ? d.timestamp : null;
    return { controlMode, pose, headJoints, bodyYaw, antennas, ts };
  }, [robotState?.data]);

  const jointCells =
    parsed?.headJoints?.map((j, i) => (
      <KvInline key={`j${i + 1}`} k={`j${i + 1}_rad`}>
        <SignedNumber value={j} />
      </KvInline>
    )) ?? [];

  return (
    <Card
      className={cn(
        "viewport-glass relative flex min-h-0 min-w-0 flex-col overflow-hidden transition-shadow duration-500",
        className,
      )}
    >
      <div className="pointer-events-none absolute -right-8 -top-8 h-24 w-24 rounded-full bg-primary/15 blur-2xl" />
      <div className="pointer-events-none absolute -bottom-10 -left-10 h-28 w-28 rounded-full bg-secondary/20 blur-3xl" />
      <CardHeader className="relative z-10 shrink-0 space-y-3 pb-2">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="font-mono text-[10px] font-medium uppercase tracking-[0.35em] text-primary/80">STATE-01</p>
            <CardTitle className="font-display text-lg tracking-wide md:text-xl">Robot state</CardTitle>
            <CardDescription className="font-mono text-xs text-muted-foreground/90">
              Daemon <code className="text-[10px]">/api/state/full</code> via <code className="text-[10px]">/ws/app</code>{" "}
              · server poll 10s
            </CardDescription>
          </div>
        </div>
        <Separator className="bg-gradient-to-r from-transparent via-primary/25 to-transparent" />
      </CardHeader>
      <CardContent className="relative z-10 flex min-h-0 flex-1 flex-col px-4 pb-4 pt-0 md:px-6 md:pb-6">
        <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border border-border/60 bg-black/80">
          <div className="pointer-events-none absolute inset-0 rounded-lg ring-1 ring-inset ring-primary/10" />
          <div className="relative z-10 flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-3 md:p-4">
            {(robotState?.fetched_at || robotState?.error) && (
              <TriGrid>
                {robotState?.fetched_at ? (
                  <div
                    className={cn("min-w-0", robotState?.error ? "col-span-2" : "col-span-3")}
                  >
                    <KvInline k="fetched_at" nowrap>
                      <KvNeutral>{formatCompactTs(robotState.fetched_at)}</KvNeutral>
                    </KvInline>
                  </div>
                ) : null}
                {robotState?.error ? (
                  <KvInline k="error">
                    <KvNeutral danger>{robotState.error}</KvNeutral>
                  </KvInline>
                ) : null}
              </TriGrid>
            )}

            {!parsed && !robotState?.error ? (
              <p className="font-mono text-xs text-muted-foreground/70">Waiting for first snapshot…</p>
            ) : null}

            {parsed ? (
              <>
                <div className="space-y-1.5">
                  <SectionLabel>Control</SectionLabel>
                  <TriGrid>
                    <KvInline k="control_mode">
                      <KvNeutral>{parsed.controlMode ?? "—"}</KvNeutral>
                    </KvInline>
                    {parsed.ts ? (
                      <div className="col-span-2 min-w-0">
                        <KvInline k="timestamp" nowrap>
                          <KvNeutral>{formatCompactTs(parsed.ts)}</KvNeutral>
                        </KvInline>
                      </div>
                    ) : null}
                  </TriGrid>
                </div>

                <Separator className="bg-border/50" />

                <div className="space-y-1.5">
                  <SectionLabel>Head pose</SectionLabel>
                  {parsed.pose ? (
                    <TriGrid>
                      <KvInline k="x_m">
                        <SignedNumber value={parsed.pose.x} digits={5} />
                      </KvInline>
                      <KvInline k="y_m">
                        <SignedNumber value={parsed.pose.y} digits={5} />
                      </KvInline>
                      <KvInline k="z_m">
                        <SignedNumber value={parsed.pose.z} digits={5} />
                      </KvInline>
                      <KvInline k="roll_rad">
                        <SignedNumber value={parsed.pose.roll} />
                      </KvInline>
                      <KvInline k="pitch_rad">
                        <SignedNumber value={parsed.pose.pitch} />
                      </KvInline>
                      <KvInline k="yaw_rad">
                        <SignedNumber value={parsed.pose.yaw} />
                      </KvInline>
                    </TriGrid>
                  ) : (
                    <TriGrid>
                      <KvInline k="head_pose">
                        <KvNeutral>—</KvNeutral>
                      </KvInline>
                    </TriGrid>
                  )}
                </div>

                <Separator className="bg-border/50" />

                <div className="space-y-1.5">
                  <SectionLabel>Joints</SectionLabel>
                  <TriGrid>
                    {jointCells}
                    <KvInline k="body_yaw_rad">
                      <SignedNumber value={parsed.bodyYaw} />
                    </KvInline>
                    <KvInline k="ant_L_rad">
                      <SignedNumber value={parsed.antennas?.[0] ?? null} />
                    </KvInline>
                    <KvInline k="ant_R_rad">
                      <SignedNumber value={parsed.antennas?.[1] ?? null} />
                    </KvInline>
                  </TriGrid>
                </div>
              </>
            ) : null}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
