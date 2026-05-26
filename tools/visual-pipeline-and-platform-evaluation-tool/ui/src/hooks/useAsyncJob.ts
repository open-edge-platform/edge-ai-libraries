import { useCallback, useEffect, useRef, useState } from "react";

export interface AsyncJobStatus {
  id: string;
  start_time: number;
  elapsed_time: number;
  state: "RUNNING" | "COMPLETED" | "FAILED";
  details?: string[];
}

/** Aggregate result returned by `execute()` when `multiple: true`. */
export type MultiJobResult<TStatus> = {
  /** Jobs that reached COMPLETED state. */
  completed: TStatus[];
  /** Jobs that reached FAILED state. */
  failed: TStatus[];
  /** Models whose download request was rejected by the server before a job was created. */
  rejected: Array<{ name: string; message: string }>;
};

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

type LazyStatusCheckHook<TArgs, TData> = () => [
  (args: TArgs) => { unwrap: () => Promise<TData> },
  ...unknown[],
];

interface UseAsyncJobOptionsBase<
  TMutationArgs,
  TMutationResponse,
  TStatus extends AsyncJobStatus,
  TResult = void,
> {
  asyncJobHook: AsyncJobHook<TMutationArgs, TMutationResponse>;
  pollingInterval?: number;
  onSuccess?: (status: TStatus) => Promise<TResult> | TResult;
  onError?: (status: TStatus) => void;
  onAbort?: (status: TStatus) => void;
  onFinally?: () => void;
}

interface UseAsyncJobOptionsSingle<
  TMutationArgs,
  TMutationResponse,
  TStatus extends AsyncJobStatus,
  TResult = void,
> extends UseAsyncJobOptionsBase<
    TMutationArgs,
    TMutationResponse,
    TStatus,
    TResult
  > {
  multiple?: false;
  /** RTK Query subscription hook used to poll the job status. */
  statusCheckHook: StatusCheckHook<{ jobId: string }, TStatus>;
  /**
   * Extract the job ID from the mutation response. Use this when the response
   * shape does not have a top-level `job_id` field. May throw to signal that
   * the job was rejected by the server before it could start.
   */
  extractJobId?: (response: TMutationResponse) => string | null | undefined;
}

interface UseAsyncJobOptionsMultiple<
  TMutationArgs,
  TMutationResponse,
  TStatus extends AsyncJobStatus,
> extends UseAsyncJobOptionsBase<TMutationArgs, TMutationResponse, TStatus> {
  /**
   * When `true`, the mutation response is expected to have a `jobs` field
   * (`{ [name]: { job_id, status_code, message } }`). Accepted jobs are
   * polled in parallel.
   */
  multiple: true;
  // lazy version needed here
  statusCheckHook: LazyStatusCheckHook<{ jobId: string }, TStatus>;
  /** Called as each individual job settles (COMPLETED or FAILED), before the overall `execute()` promise resolves. */
  onJobComplete?: (status: TStatus) => void;
  extractJobId?: never;
}

type UseAsyncJobReturnBase<TStatus extends AsyncJobStatus> = {
  isLoading: boolean;
  isMutating: boolean;
  isPolling: boolean;
  jobId: string | null;
  jobStatus: TStatus | undefined;
  reset: () => void;
  isJobCancelled: (status: TStatus) => boolean;
};

// Overload: multiple jobs — execute() resolves with MultiJobResult
export function useAsyncJob<
  TMutationArgs,
  TMutationResponse,
  TStatus extends AsyncJobStatus,
>(
  options: UseAsyncJobOptionsMultiple<
    TMutationArgs,
    TMutationResponse,
    TStatus
  >,
): UseAsyncJobReturnBase<TStatus> & {
  execute: (args: TMutationArgs) => Promise<MultiJobResult<TStatus>>;
};

// Overload: single job — execute() resolves with TStatus
export function useAsyncJob<
  TMutationArgs,
  TMutationResponse,
  TStatus extends AsyncJobStatus,
  TResult = void,
>(
  options: UseAsyncJobOptionsSingle<
    TMutationArgs,
    TMutationResponse,
    TStatus,
    TResult
  >,
): UseAsyncJobReturnBase<TStatus> & {
  execute: (args: TMutationArgs) => Promise<TStatus>;
};

export function useAsyncJob<
  TMutationArgs,
  TMutationResponse,
  TStatus extends AsyncJobStatus,
  TResult = void,
>(
  options:
    | UseAsyncJobOptionsSingle<
        TMutationArgs,
        TMutationResponse,
        TStatus,
        TResult
      >
    | UseAsyncJobOptionsMultiple<TMutationArgs, TMutationResponse, TStatus>,
) {
  const isMultipleRef = useRef(options.multiple === true);

  // Single-job state & refs
  const [jobId, setJobId] = useState<string | null>(null);
  const lastJobIdRef = useRef<string | null>(null);
  const jobResolveRef = useRef<((status: TStatus) => void) | null>(null);
  const jobRejectRef = useRef<((status: TStatus) => void) | null>(null);

  // Multiple-jobs state
  const [isPollingMultiple, setIsPollingMultiple] = useState(false);
  const abortMultipleRef = useRef(false);

  const [triggerMutation, { isLoading: isMutating }] = options.asyncJobHook();

  // Use refs to avoid adding callbacks to useEffect dependencies
  const onSuccessRef = useRef(options.onSuccess);
  const onErrorRef = useRef(options.onError);
  const onAbortRef = useRef(options.onAbort);
  const onFinallyRef = useRef(options.onFinally);
  const onJobCompleteRef = useRef(
    (
      options as UseAsyncJobOptionsMultiple<
        TMutationArgs,
        TMutationResponse,
        TStatus
      >
    ).onJobComplete,
  );

  // Keep refs up to date
  useEffect(() => {
    onSuccessRef.current = options.onSuccess;
    onErrorRef.current = options.onError;
    onAbortRef.current = options.onAbort;
    onFinallyRef.current = options.onFinally;
    onJobCompleteRef.current = (
      options as UseAsyncJobOptionsMultiple<
        TMutationArgs,
        TMutationResponse,
        TStatus
      >
    ).onJobComplete;
  });

  // Subscription-based polling — only active in single mode.
  // In multiple mode, the lazy hook is called with no args to get the trigger fn.
  const triggerStatusRef = useRef<
    | ((args: { jobId: string }) => { unwrap: () => Promise<TStatus> })
    | undefined
  >(undefined);

  let jobStatus: TStatus | undefined;
  if (!isMultipleRef.current) {
    const { data } = (
      options as UseAsyncJobOptionsSingle<
        TMutationArgs,
        TMutationResponse,
        TStatus,
        TResult
      >
    ).statusCheckHook(
      { jobId: jobId! },
      { skip: !jobId, pollingInterval: options.pollingInterval ?? 1000 },
    );
    jobStatus = data;
  } else {
    const [lazyTrigger] = (
      options as UseAsyncJobOptionsMultiple<
        TMutationArgs,
        TMutationResponse,
        TStatus
      >
    ).statusCheckHook();
    triggerStatusRef.current = lazyTrigger;
  }

  const isJobCancelled = useCallback(
    (status: TStatus): boolean =>
      status.state === "COMPLETED" &&
      status.details?.[0]?.includes("Cancelled by user") === true,
    [],
  );

  // Single-job completion handler
  useEffect(() => {
    if (!jobStatus || !jobId) return;
    if (jobStatus.id !== jobId || lastJobIdRef.current === jobId) return;
    if (jobStatus.state !== "COMPLETED" && jobStatus.state !== "FAILED") return;

    const handleJobCompletion = async () => {
      lastJobIdRef.current = jobId;

      try {
        if (jobStatus.state === "COMPLETED") {
          if (isJobCancelled(jobStatus)) {
            onAbortRef.current?.(jobStatus);
            jobResolveRef.current?.(jobStatus);
          } else {
            await onSuccessRef.current?.(jobStatus);
            jobResolveRef.current?.(jobStatus);
          }
        } else if (jobStatus.state === "FAILED") {
          onErrorRef.current?.(jobStatus);
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
  }, [jobStatus, jobId, isJobCancelled]);

  const execute = async (args: TMutationArgs) => {
    const response = await triggerMutation(args).unwrap();

    if (isMultipleRef.current) {
      const pollingInterval = options.pollingInterval ?? 1000;

      const jobsMap =
        (
          response as {
            jobs?: Record<
              string,
              { job_id?: string | null; status_code: number; message: string }
            >;
          }
        ).jobs ?? {};

      const acceptedJobIds: string[] = [];
      const rejected: Array<{ name: string; message: string }> = [];

      for (const [name, job] of Object.entries(jobsMap)) {
        if (job.status_code === 202 && job.job_id) {
          acceptedJobIds.push(job.job_id);
        } else {
          rejected.push({ name, message: job.message });
        }
      }

      if (acceptedJobIds.length === 0) {
        return {
          completed: [],
          failed: [],
          rejected,
        } as MultiJobResult<TStatus>;
      }

      abortMultipleRef.current = false;
      setIsPollingMultiple(true);

      // Poll each job independently via recursive setTimeout calls,
      // all running in parallel via Promise.allSettled.
      const pollJob = (id: string): Promise<TStatus> =>
        new Promise((resolve, reject) => {
          const tick = async () => {
            if (abortMultipleRef.current) {
              reject(new Error("Aborted"));
              return;
            }
            try {
              const status = await triggerStatusRef.current!({
                jobId: id,
              }).unwrap();
              if (status.state === "COMPLETED" || status.state === "FAILED") {
                onJobCompleteRef.current?.(status);
                resolve(status);
              } else {
                setTimeout(tick, pollingInterval);
              }
            } catch (err) {
              reject(err);
            }
          };
          setTimeout(tick, pollingInterval);
        });

      try {
        const settlements = await Promise.allSettled(
          acceptedJobIds.map(pollJob),
        );

        const completed: TStatus[] = [];
        const failed: TStatus[] = [];

        for (const s of settlements) {
          if (s.status === "fulfilled") {
            if (s.value.state === "COMPLETED") completed.push(s.value);
            else failed.push(s.value);
          }
          // Network / abort errors are silently dropped; the model list
          // refreshes via invalidateTags in the caller.
        }

        onFinallyRef.current?.();
        return { completed, failed, rejected } as MultiJobResult<TStatus>;
      } finally {
        setIsPollingMultiple(false);
      }
    }

    // Single-job mode
    const { extractJobId } = options as UseAsyncJobOptionsSingle<
      TMutationArgs,
      TMutationResponse,
      TStatus,
      TResult
    >;
    const id = extractJobId
      ? extractJobId(response)
      : "job_id" in (response as object)
        ? (response as unknown as AsyncJobResponse).job_id
        : null;

    if (!id) {
      throw new Error("Response does not contain job_id");
    }

    setJobId(id);

    return new Promise<TStatus>((resolve, reject) => {
      jobResolveRef.current = resolve;
      jobRejectRef.current = reject;
    });
  };

  const reset = () => {
    lastJobIdRef.current = null;
    setJobId(null);
    if (isMultipleRef.current) {
      abortMultipleRef.current = true;
      setIsPollingMultiple(false);
    }
  };

  const isPolling = isMultipleRef.current
    ? isPollingMultiple
    : !!jobId &&
      (!jobStatus ||
        jobStatus.id !== jobId ||
        (jobStatus.state !== "COMPLETED" && jobStatus.state !== "FAILED"));

  return {
    execute,
    isLoading: isMutating || isPolling,
    isMutating,
    isPolling,
    jobId,
    jobStatus,
    reset,
    isJobCancelled,
  };
}
