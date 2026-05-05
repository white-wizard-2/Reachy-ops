import { useCallback, useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function CollapsibleSection({
  title,
  defaultOpen = true,
  className,
  children,
}: {
  title: string;
  defaultOpen?: boolean;
  className?: string;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const id = useId();
  const toggle = useCallback(() => setOpen((v) => !v), []);
  return (
    <div className={cn("space-y-2", className)}>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="h-auto w-full justify-between px-2 py-1.5 font-mono text-[10px] font-medium uppercase tracking-[0.35em] text-muted-foreground/90"
        aria-expanded={open}
        aria-controls={id}
        onClick={toggle}
      >
        <span>{title}</span>
        <span className="font-mono text-xs tracking-normal">{open ? "−" : "+"}</span>
      </Button>
      <div id={id} hidden={!open}>
        {children}
      </div>
    </div>
  );
}

