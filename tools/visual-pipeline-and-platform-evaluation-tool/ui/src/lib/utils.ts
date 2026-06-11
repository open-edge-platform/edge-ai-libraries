import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

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
