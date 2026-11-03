// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import type { SVGProps } from "react";

import { cn } from "@/lib/utils";

/**
 * CPU core pinning icon: a push pin on a processor die.
 *
 * Drawn on the same 24x24 grid and with the same stroke weight as the lucide
 * icons used elsewhere in the toolbar, so it lines up with them at any size.
 */
export const CpuPinIcon = ({
  className,
  ...props
}: SVGProps<SVGSVGElement>) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={2}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={cn("shrink-0", className)}
    aria-hidden="true"
    focusable="false"
    {...props}
  >
    <rect x="3" y="3" width="18" height="18" rx="2" />
    <path d="M7 3V1" />
    <path d="M17 3V1" />
    <path d="M3 7H1" />
    <path d="M3 17H1" />
    <path d="M7 21v2" />
    <path d="M17 21v2" />
    <path d="M21 7h2" />
    <path d="M21 17h2" />
    <path d="M8 7h8" />
    <path d="M10 7v3.5L8 12.5h8L14 10.5V7" />
    <path d="M12 12.5V17" />
  </svg>
);

export default CpuPinIcon;
