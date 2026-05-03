import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-md border px-2.5 py-0.5 text-xs font-semibold tracking-wide transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
  {
    variants: {
      variant: {
        default: "border-transparent bg-primary text-primary-foreground shadow [text-shadow:0_0_12px_hsl(var(--primary)/0.5)]",
        secondary: "border-border/60 bg-secondary/30 text-secondary-foreground backdrop-blur-sm",
        outline: "border-primary/40 text-foreground",
        destructive: "border-transparent bg-destructive text-destructive-foreground",
        live: "border-emerald-500/50 bg-emerald-500/15 text-emerald-300 shadow-[0_0_20px_hsl(160_84%_39%/0.35)]",
        offline: "border-amber-500/40 bg-amber-500/10 text-amber-200",
        ghost: "border-border/40 bg-muted/20 text-muted-foreground",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
