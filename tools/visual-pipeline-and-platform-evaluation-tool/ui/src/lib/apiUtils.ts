import type { MessageResponse } from "@/api/api.generated";
import type { AsyncJobStatus } from "@/hooks/useAsyncJob";

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
