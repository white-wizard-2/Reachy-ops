import { ReachyOpsBar } from "@/components/ReachyOpsBar";

/** Shared title block for the primary optical column. */
export function PrimaryBrandBlock() {
  return (
    <div className="flex min-w-0 flex-wrap items-start justify-between gap-3">
      <div className="min-w-0 space-y-1">
        <p className="font-mono text-[11px] font-medium uppercase tracking-[0.5em] text-primary/70">WHITE WIZARDRY</p>
        <h2 className="font-display text-2xl font-bold tracking-tight text-glow md:text-3xl lg:text-4xl">
          REACHY<span className="text-primary"> // </span>OPS
        </h2>
      </div>
      <ReachyOpsBar />
    </div>
  );
}
