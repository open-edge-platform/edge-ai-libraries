import type { MessageResponse } from "@/api/api.generated";
import type { AsyncJobStatus } from "@/hooks/useAsyncJob";
import { toast } from "@/lib/toast";
import { formatErrorMessage } from "@/lib/utils.ts";

type RTKQueryError = {
  status: number;
  data: MessageResponse;
};

export const isApiError = (error: unknown): error is RTKQueryError =>
  typeof error === "object" &&
  error !== null &&
  "status" in error &&
  "data" in error &&
  typeof (error as RTKQueryError).data === "object" &&
  (error as RTKQueryError).data !== null &&
  "message" in (error as RTKQueryError).data;

export const isAsyncJobError = (error: unknown): error is AsyncJobStatus =>
  error !== null &&
  typeof error === "object" &&
  "state" in error &&
  "details" in error;

export const handleAsyncJobError = (
  error: AsyncJobStatus,
  titlePrefix: string,
) => {
  if (error.state === "FAILED") {
    const description = formatErrorMessage(error.details);
    toast.error(`${titlePrefix} error`, {
      description,
    });
  } else if (
    error.state === "COMPLETED" &&
    error.details?.some((detail) => detail.includes("Cancelled by user"))
  ) {
    const description = formatErrorMessage(
      error.details,
      "Operation cancelled",
    );
    toast.error(`${titlePrefix} cancelled`, {
      description,
    });
  }
};

export const handleApiError = (error: unknown, title: string) => {
  const errorMessage = getErrorMessage(error, "Unknown error");
  toast.error(title, {
    description: errorMessage,
  });

  return errorMessage;
};

export const getErrorMessage = (
  error: unknown,
  defaultMessage: string = "Unknown error",
): string => {
  if (error == null) return defaultMessage;
  if (typeof error === "string") return error;
  if (error instanceof Error) return error.message || defaultMessage;
  if (isApiError(error)) return error.data.message || defaultMessage;

  if (typeof error === "object") {
    if ("message" in error && typeof error.message === "string") {
      return error.message || defaultMessage;
    }

    if ("detail" in error) {
      const detail = error.detail;
      if (typeof detail === "string") return detail || defaultMessage;
      if (Array.isArray(detail)) {
        return formatErrorMessage(detail, defaultMessage);
      }
    }

    if ("data" in error && typeof error.data === "string") {
      return error.data || defaultMessage;
    }

    try {
      return JSON.stringify(error) ?? defaultMessage;
    } catch {
      return defaultMessage;
    }
  }

  return String(error) || defaultMessage;
};
