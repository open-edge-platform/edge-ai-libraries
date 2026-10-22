import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Shared CSS class for primary page content containers. */
export const CONTENT_CONTAINER_CLASS = "container px-12 mx-auto py-8";

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

const CORE_ULTRA_GENERATIONS: Record<string, string> = {
  1: "Meteor Lake",
  2: "Arrow Lake",
  3: "Panther Lake",
};

/**
 * Derive the Core Ultra generation from a detected CPU name.
 * Example: "Intel(R) Core(TM) Ultra 9 285H" → "Core Ultra Series 2 (Arrow Lake)"
 */
export const cpuGeneration = (cpu: string | undefined | null): string => {
  if (!cpu) return "";
  // The SKU's leading digit is the series: 1xx Series 1, 2xx Series 2, 3xx Series 3.
  const sku = cpu.match(/Ultra\s+\w+\s+(\d)\d{2}/i);
  const codename = sku ? CORE_ULTRA_GENERATIONS[sku[1]] : undefined;
  if (!codename) return "";
  return `Core Ultra Series ${sku?.[1]} (${codename})`;
};
