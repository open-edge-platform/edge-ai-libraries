import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Shared CSS class for all card grid layouts (pipelines, benchmarks, etc.) */
export const CARDS_GRID_CLASS =
  "grid gap-4 grid-cols-[repeat(auto-fit,minmax(18.75rem,1fr))]";

export const formatErrorMessage = (
  errorMessage: string[] | string | null | undefined,
  defaultMessage: string = "Unknown error",
): string => {
  if (!errorMessage) return defaultMessage;
  if (Array.isArray(errorMessage)) {
    return errorMessage.join(", ") ?? defaultMessage;
  }
  return errorMessage ?? defaultMessage;
};

/**
 * Format device names by replacing trademark notations with symbols
 * Converts (R), (TM), (C) to ®, ™, © respectively
 */
export const formatDeviceName = (name: string | undefined | null): string => {
  if (!name) return "";

  return name
    .replace(/\(R\)/g, "®")
    .replace(/\(TM\)/g, "™")
    .replace(/\(C\)/g, "©");
};

/**
 * Convert a slug to a human-readable title.
 * Replaces hyphens and underscores with spaces and title-cases each word.
 * Example: "my-benchmark-suite" → "My Benchmark Suite"
 */
export const unslug = (slug: string): string =>
  slug.replace(/[-_]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
