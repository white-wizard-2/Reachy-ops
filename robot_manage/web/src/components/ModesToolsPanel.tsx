import { useCallback } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";

export const MODES = [
  "Sentry Mode",
  "Silent Mode",
  "Teacher Mode",
  "Guardian Mode",
  "Mute Mode",
] as const;

export const TOOLS = ["Vision", "Voice", "Thinking", "Internet", "Actions"] as const;

export function ModesToolsPanel({
  className,
  activeMode,
  toolsOn,
  onActiveModeChange,
  onToolsOnChange,
}: {
  className?: string;
  activeMode: string | null;
  toolsOn: Set<string>;
  onActiveModeChange: (mode: string | null) => void;
  onToolsOnChange: (tools: Set<string>) => void;
}) {
  const toggleTool = useCallback(
    (name: string) => {
      const next = new Set(toolsOn);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      onToolsOnChange(next);
    },
    [toolsOn, onToolsOnChange],
  );

  return (
    <Card
      className={cn(
        "viewport-glass relative flex h-full min-h-0 flex-col overflow-hidden transition-shadow duration-500",
        className,
      )}
    >
      <div className="pointer-events-none absolute -right-8 -top-8 h-24 w-24 rounded-full bg-primary/15 blur-2xl" />
      <div className="pointer-events-none absolute -bottom-10 -left-10 h-28 w-28 rounded-full bg-secondary/20 blur-3xl" />
      <CardHeader className="relative z-10 space-y-3 pb-2">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="font-mono text-[10px] font-medium uppercase tracking-[0.35em] text-primary/80">CTL-01</p>
            <CardTitle className="font-display text-lg tracking-wide md:text-xl">Modes & tools</CardTitle>
            <CardDescription className="font-mono text-xs text-muted-foreground/90">
              Operating mode (one) and capability toggles — say &quot;activate&quot; or &quot;deactivate&quot; with a name
            </CardDescription>
          </div>
        </div>
        <Separator className="bg-gradient-to-r from-transparent via-primary/25 to-transparent" />
      </CardHeader>
      <CardContent className="relative z-10 flex min-h-0 flex-1 flex-col px-4 pb-4 pt-0 md:px-6 md:pb-6">
        <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border border-border/60 bg-black/80">
          <div className="pointer-events-none absolute inset-0 rounded-lg ring-1 ring-inset ring-primary/10" />
          <div className="relative z-10 flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-3 md:p-4">
            <div className="space-y-2">
              <p className="font-mono text-[10px] font-medium uppercase tracking-[0.35em] text-muted-foreground/90">
                Modes
              </p>
              <div className="grid grid-cols-3 gap-2" role="radiogroup" aria-label="Operating mode">
                {MODES.map((label) => {
                  const on = activeMode === label;
                  return (
                    <Button
                      key={label}
                      type="button"
                      size="sm"
                      variant={on ? "default" : "outline"}
                      className="h-auto min-h-8 justify-center px-2 py-1.5 text-center font-mono text-[11px] leading-tight tracking-wide"
                      role="radio"
                      aria-checked={on}
                      onClick={() => onActiveModeChange(on ? null : label)}
                    >
                      {label}
                    </Button>
                  );
                })}
              </div>
            </div>
            <Separator className="bg-border/50" />
            <div className="space-y-2">
              <p className="font-mono text-[10px] font-medium uppercase tracking-[0.35em] text-muted-foreground/90">
                Tools
              </p>
              <div className="grid grid-cols-3 gap-2">
                {TOOLS.map((label) => {
                  const on = toolsOn.has(label);
                  return (
                    <Button
                      key={label}
                      type="button"
                      size="sm"
                      variant={on ? "default" : "outline"}
                      className="font-mono text-[11px] tracking-wide"
                      aria-pressed={on}
                      onClick={() => toggleTool(label)}
                    >
                      {label}
                    </Button>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
