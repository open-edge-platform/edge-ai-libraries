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
