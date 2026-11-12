// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
//
// Minimal fallback Button. Once the app is scaffolded, prefer regenerating this
// file with `npx shadcn@latest add button` to stay in sync with the upstream
// shadcn/ui primitive (variants, a11y, data-slot plumbing).

import { cva } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center rounded-lg border border-transparent text-sm font-medium whitespace-nowrap transition-all outline-none select-none disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/80",
        outline: "border-border bg-background hover:bg-muted",
        secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/80",
        ghost: "hover:bg-muted hover:text-foreground",
        destructive: "bg-destructive/10 text-destructive hover:bg-destructive/20",
      },
      size: {
        default: "h-8 gap-1.5 px-3",
        sm: "h-7 gap-1 px-2.5 text-[0.8rem]",
        lg: "h-9 gap-1.5 px-3",
        icon: "size-8",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  }
);

export function Button({ className, variant = "default", size = "default", ...props }) {
  return (
    <button
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  );
}
