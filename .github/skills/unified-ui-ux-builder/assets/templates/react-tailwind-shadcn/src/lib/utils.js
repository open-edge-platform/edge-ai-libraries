// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { clsx } from "clsx";
import { twMerge } from "tailwind-merge"

// Shared className combinator used by every component — merges conditional
// Tailwind classes without duplicate/conflicting utility collisions.
export function cn(...inputs) {
  return twMerge(clsx(inputs));
}
