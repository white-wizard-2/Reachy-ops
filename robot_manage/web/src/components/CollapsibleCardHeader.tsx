import { useCallback, useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function useCollapsibleCard(defaultOpen: boolean = true) {
  const [open, setOpen] = useState(defaultOpen);
  const contentId = useId();
  const toggle = useCallback(() => setOpen((v) => !v), []);
  return { open, toggle, contentId };
}

export function CollapsibleCardToggle({
  open,
  onToggle,
  controlsId,
  className,
}: {
  open: boolean;
  onToggle: () => void;
  controlsId: string;
  className?: string;
}) {
  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      className={cn(
        "h-8 w-8 px-0 font-mono text-xs pointer-events-auto border border-border/50 bg-black/40 hover:bg-black/55",
        className,
      )}
      aria-expanded={open}
      aria-controls={controlsId}
      title={open ? "Collapse" : "Expand"}
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onToggle();
      }}
    >
      {open ? "−" : "+"}
    </Button>
  );
}

