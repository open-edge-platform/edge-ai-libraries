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

type ValidationErrorItem = { loc?: unknown[]; msg?: string };

// FastAPI reports request-validation failures as `detail`, not `message`.
const getValidationErrorMessage = (error: unknown): string | null => {
  if (typeof error !== "object" || error === null || !("data" in error)) {
    return null;
  }
  const data = (error as { data?: unknown }).data;
  if (typeof data !== "object" || data === null || !("detail" in data)) {
    return null;
  }
  const detail = (data as { detail?: unknown }).detail;
  if (typeof detail === "string") {
    return detail;
  }
  if (!Array.isArray(detail)) {
    return null;
  }
  const described = (detail as ValidationErrorItem[])
    .map((item) => {
      const field = Array.isArray(item.loc) ? item.loc.join(" > ") : "";
      return field ? `${field}: ${item.msg ?? "invalid value"}` : item.msg;
    })
    .filter(Boolean);
  return described.length > 0 ? described.join("; ") : null;
};

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
  const errorMessage = isApiError(error)
    ? error.data.message
    : (getValidationErrorMessage(error) ?? "Unknown error");
  toast.error(title, {
    description: errorMessage,
  });

  return errorMessage;
};
