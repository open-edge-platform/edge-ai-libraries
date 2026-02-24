import type { MessageResponse } from "@/api/api.generated";
import type { AsyncJobStatus } from "@/hooks/useAsyncJob";
import { toast } from "sonner";
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
  "error_message" in error;

export const handleAsyncJobError = (
  error: AsyncJobStatus,
  titlePrefix: string,
) => {
  if (error.state === "ERROR") {
    const description = formatErrorMessage(error.error_message);
    toast.error(`${titlePrefix} error`, {
      description,
    });
  } else if (error.state === "ABORTED") {
    const description = formatErrorMessage(
      error.error_message,
      "Operation aborted",
    );
    toast.error(`${titlePrefix} aborted`, {
      description,
    });
  }
};

export const handleApiError = (error: unknown, title: string) => {
  const errorMessage = isApiError(error) ? error.data.message : "Unknown error";
  toast.error(title, {
    description: errorMessage,
  });
};
