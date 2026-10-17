// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
//
// Minimal fallback Card. Once the app is scaffolded, prefer regenerating this
// file with `npx shadcn@latest add card` to stay in sync with the upstream
// shadcn/ui primitive.

import { cn } from "@/lib/utils";

export function Card({ className, ...props }) {
  return (
    <div
      data-slot="card"
      className={cn(
        "flex flex-col gap-4 overflow-hidden rounded-xl bg-card py-4 text-sm text-card-foreground shadow-(--shadow-card)",
        className
      )}
      {...props}
    />
  );
}

export function CardHeader({ className, ...props }) {
  return <div data-slot="card-header" className={cn("grid gap-1 px-4", className)} {...props} />;
}

export function CardTitle({ className, ...props }) {
  return <div data-slot="card-title" className={cn("text-base leading-snug font-medium", className)} {...props} />;
}

export function CardDescription({ className, ...props }) {
  return <div data-slot="card-description" className={cn("text-sm text-muted-foreground", className)} {...props} />;
}

export function CardContent({ className, ...props }) {
  return <div data-slot="card-content" className={cn("px-4", className)} {...props} />;
}

export function CardFooter({ className, ...props }) {
  return (
    <div
      data-slot="card-footer"
      className={cn("flex items-center rounded-b-xl border-t bg-muted/50 p-4", className)}
      {...props}
    />
  );
}
