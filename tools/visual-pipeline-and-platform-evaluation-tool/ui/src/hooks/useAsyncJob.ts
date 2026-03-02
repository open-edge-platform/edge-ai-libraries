import { useEffect, useRef, useState } from "react";

export interface AsyncJobStatus {
  id: string;
  start_time: number;
  elapsed_time: number;
  state: "RUNNING" | "COMPLETED" | "ERROR" | "ABORTED";
  error_message?: string[] | string | null;
}

interface AsyncJobResponse {
  job_id: string;
}

type QueryResult<TData> = {
  data?: TData;
  error?: unknown;
  isLoading: boolean;
  isSuccess: boolean;
  isError: boolean;
  [key: string]: unknown;
};

type AsyncJobHook<TArgs, TData> = () => readonly [
  (args: TArgs) => PromiseLike<unknown> & { unwrap: () => Promise<TData> },
  {
    readonly isLoading: boolean;
    readonly [key: string]: unknown;
  },
];

type StatusCheckHook<TArgs, TData> = (
  args: TArgs,
  options?: {
    skip?: boolean;
    pollingInterval?: number;
  },
) => QueryResult<TData>;

interface UseAsyncJobOptions<
  TMutationArgs,
  TMutationResponse extends AsyncJobResponse,
  TStatus extends AsyncJobStatus,
  TResult = void,
> {
  asyncJobHook: AsyncJobHook<TMutationArgs, TMutationResponse>;
  statusCheckHook: StatusCheckHook<{ jobId: string }, TStatus>;
  pollingInterval?: number;
  onSuccess?: (status: TStatus) => Promise<TResult> | TResult;
  onError?: (status: TStatus) => void;
  onAbort?: (status: TStatus) => void;
  onFinally?: () => void;
}

/**
 * Hook to manage async mutation + job polling lifecycle
 * Completely hides polling complexity - just call execute() with your mutation payload
 *
 * @example
 * const { execute, isLoading } = useAsyncJob({
 *   asyncJobHook: useValidatePipelineMutation,
 *   statusCheckHook: useGetValidationJobStatusQuery,
 *   onSuccess: async (status) => {
 *     await createPipeline(...);
 *     toast.success("Pipeline created successfully");
 *   },
 *   onError: (status) => {
 *     toast.error(status.error_message?.join(", "));
 *   },
 * });
 *
 * // Later, when you want to start the job:
 * // execute() returns the complete status object when the job completes
 * const result = await execute({
 *   pipelineValidationInput: { pipeline_graph: graphData }
 * });
 * // result.state === "COMPLETED"
 * // result.id, result.error_message, and other fields are available
 */
export function useAsyncJob<
  TMutationArgs,
  TMutationResponse extends AsyncJobResponse,
  TStatus extends AsyncJobStatus,
  TResult = void,
>({
  asyncJobHook,
  statusCheckHook,
  pollingInterval = 1000,
  onSuccess,
  onError,
  onAbort,
  onFinally,
}: UseAsyncJobOptions<TMutationArgs, TMutationResponse, TStatus, TResult>) {
  const [jobId, setJobId] = useState<string | null>(null);
  const lastJobIdRef = useRef<string | null>(null);

  const jobResolveRef = useRef<((status: TStatus) => void) | null>(null);
  const jobRejectRef = useRef<((status: TStatus) => void) | null>(null);

  const [triggerMutation, { isLoading: isMutating }] = asyncJobHook();

  // Use refs to avoid adding callbacks to useEffect dependencies
  const onSuccessRef = useRef(onSuccess);
  const onErrorRef = useRef(onError);
  const onAbortRef = useRef(onAbort);
  const onFinallyRef = useRef(onFinally);

  // Keep refs up to date
  useEffect(() => {
    onSuccessRef.current = onSuccess;
    onErrorRef.current = onError;
    onAbortRef.current = onAbort;
    onFinallyRef.current = onFinally;
  });

  const { data: jobStatus } = statusCheckHook(
    { jobId: jobId! },
    {
      skip: !jobId,
      pollingInterval,
    },
  );

  useEffect(() => {
    if (!jobStatus || !jobId) return;

    if (jobStatus.id !== jobId || lastJobIdRef.current === jobId) return;

    if (
      jobStatus.state !== "COMPLETED" &&
      jobStatus.state !== "ERROR" &&
      jobStatus.state !== "ABORTED"
    ) {
      return;
    }

    const handleJobCompletion = async () => {
      lastJobIdRef.current = jobId;

      try {
        if (jobStatus.state === "COMPLETED") {
          await onSuccessRef.current?.(jobStatus);
          jobResolveRef.current?.(jobStatus);
        } else if (jobStatus.state === "ERROR") {
          onErrorRef.current?.(jobStatus);
          jobRejectRef.current?.(jobStatus);
        } else if (jobStatus.state === "ABORTED") {
          onAbortRef.current?.(jobStatus);
          jobRejectRef.current?.(jobStatus);
        }
      } finally {
        onFinallyRef.current?.();
        jobResolveRef.current = null;
        jobRejectRef.current = null;
        setJobId(null);
      }
    };

    handleJobCompletion();
  }, [jobStatus, jobId]);

  const execute = async (args: TMutationArgs): Promise<TStatus> => {
    const response = await triggerMutation(args).unwrap();

    if ("job_id" in response) {
      setJobId(response.job_id);

      return new Promise<TStatus>((resolve, reject) => {
        jobResolveRef.current = resolve;
        jobRejectRef.current = reject;
      });
    }

    throw new Error("Response does not contain job_id");
  };

  const reset = () => {
    lastJobIdRef.current = null;
    setJobId(null);
  };

  const isPolling =
    !!jobId &&
    (!jobStatus ||
      (jobStatus.state !== "COMPLETED" &&
        jobStatus.state !== "ERROR" &&
        jobStatus.state !== "ABORTED"));

  return {
    execute,
    isLoading: isMutating || isPolling,
    isMutating,
    jobStatus,
    reset,
  };
}
