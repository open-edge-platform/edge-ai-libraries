import { useEffect, useRef } from "react";

interface AsyncJobStatus {
  id: string;
  state: "PENDING" | "RUNNING" | "COMPLETED" | "ERROR" | "ABORTED";
  is_valid?: boolean;
  error_message?: string[];
}

// RTK Query hook return type
type QueryResult<TData> = {
  data: TData | undefined;
  error?: unknown;
  isLoading: boolean;
  isSuccess: boolean;
  isError: boolean;
};

// RTK Query hook type
type QueryHook<TArgs, TData> = (
  args: TArgs,
  options?: {
    skip?: boolean;
    pollingInterval?: number;
  },
) => QueryResult<TData>;

interface UseAsyncJobOptions<TStatus extends AsyncJobStatus, TResult = void> {
  jobId: string | null;
  queryHook: QueryHook<{ jobId: string }, TStatus>;
  queryOptions?: {
    pollingInterval?: number;
    skip?: boolean;
  };
  onComplete?: (status: TStatus) => Promise<TResult> | TResult;
  onError?: (status: TStatus) => void;
  onAbort?: (status: TStatus) => void;
  onFinally?: () => void;
}

/**
 * Hook to manage async job polling lifecycle
 *
 * @example
 * const { isPolling, reset } = useAsyncJob({
 *   jobId: validationJobId,
 *   queryHook: useGetValidationJobStatusQuery,
 *   onComplete: async (status) => {
 *     if (status.is_valid) {
 *       await createPipeline(...);
 *     } else {
 *       toast.error("Validation failed");
 *     }
 *   },
 *   onError: (status) => {
 *     toast.error(status.error_message?.join(", "));
 *   },
 *   onFinally: () => {
 *     setValidationJobId(null); // Clean up - runs after any outcome
 *   }
 * });
 */
export function useAsyncJob<TStatus extends AsyncJobStatus, TResult = void>({
  jobId,
  queryHook,
  queryOptions = {},
  onComplete,
  onError,
  onAbort,
  onFinally,
}: UseAsyncJobOptions<TStatus, TResult>) {
  const { pollingInterval = 1000, skip = false } = queryOptions;
  const lastJobIdRef = useRef<string | null>(null);

  const { data: jobStatus } = queryHook(
    { jobId: jobId! },
    {
      skip: !jobId || skip,
      pollingInterval,
    },
  );

  useEffect(() => {
    if (!jobStatus || !jobId) return;

    // Prevent double-execution if job_id hasn't changed
    if (jobStatus.id !== jobId || lastJobIdRef.current === jobId) return;

    const handleJobCompletion = async () => {
      lastJobIdRef.current = jobId;

      try {
        if (jobStatus.state === "COMPLETED") {
          await onComplete?.(jobStatus);
        } else if (jobStatus.state === "ERROR") {
          onError?.(jobStatus);
        } else if (jobStatus.state === "ABORTED") {
          onAbort?.(jobStatus);
        }
      } finally {
        onFinally?.();
      }
    };

    handleJobCompletion();
  }, [jobStatus, jobId, onComplete, onError, onAbort, onFinally]);

  const reset = () => {
    lastJobIdRef.current = null;
  };

  return {
    jobStatus,
    isPolling:
      !!jobId &&
      (!jobStatus ||
        (jobStatus.state !== "COMPLETED" &&
          jobStatus.state !== "ERROR" &&
          jobStatus.state !== "ABORTED")),
    reset,
  };
}
