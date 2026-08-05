import {
  useGetBenchmarkJobStatusQuery,
  useGetBenchmarkStatusesQuery,
  useRunBenchmarkSuiteMutation,
  useStopBenchmarkJobMutation,
} from "@/api/api.generated.ts";
import { Button } from "@/components/ui/button";
import {
  Progress,
  ProgressIndicator,
  ProgressTrack,
} from "@/components/ui/progress";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { handleApiError } from "@/lib/apiUtils";
import { Loader2, Play, Square } from "lucide-react";
import { useEffect, useState } from "react";
import { unslug } from "@/lib/utils";

type RunBenchmarkButtonProps = {
  suiteSlug: string;
};

export const RunBenchmarkButton = ({ suiteSlug }: RunBenchmarkButtonProps) => {
  const [newJobId, setNewJobId] = useState<string | null>(null);
  const [stoppingJobId, setStoppingJobId] = useState<string | null>(null);
  const [displayProgress, setDisplayProgress] = useState(0);
  const [runBenchmark, { isLoading: isMutating }] =
    useRunBenchmarkSuiteMutation();
  const [stopBenchmark, { isLoading: isStopping }] =
    useStopBenchmarkJobMutation();

  const { data: allStatuses } = useGetBenchmarkStatusesQuery(undefined, {
    pollingInterval: 2000,
  });

  const runningJob = allStatuses?.find((job) => job.state === "RUNNING");
  const isThisSuiteRunning = runningJob?.suite_slug === suiteSlug;
  const isOtherSuiteRunning = !!runningJob && !isThisSuiteRunning;

  const activeJobId = isThisSuiteRunning ? runningJob!.id : newJobId;

  const { data: activeJobStatus } = useGetBenchmarkJobStatusQuery(
    { jobId: activeJobId ?? "" },
    { skip: !activeJobId, pollingInterval: 2000 },
  );

  const jobFinished =
    activeJobStatus?.state === "COMPLETED" ||
    activeJobStatus?.state === "FAILED";
  if (jobFinished && newJobId) {
    setNewJobId(null);
  }
  if (!isThisSuiteRunning && stoppingJobId) {
    setStoppingJobId(null);
  }

  const handleRun = async () => {
    try {
      setDisplayProgress(0);
      const response = await runBenchmark({ suiteSlug }).unwrap();
      setNewJobId(response.job_id);
    } catch (error) {
      handleApiError(error, "Failed to run benchmark");
      console.error("Failed to run benchmark:", error);
    }
  };

  const handleStop = async () => {
    if (!activeJobId) return;
    try {
      setStoppingJobId(activeJobId);
      await stopBenchmark({ jobId: activeJobId }).unwrap();
    } catch (error) {
      setStoppingJobId(null);
      handleApiError(error, "Failed to stop benchmark");
      console.error("Failed to stop benchmark:", error);
    }
  };

  // Keep displayProgress in sync with polled status for the active job only
  useEffect(() => {
    if (
      isThisSuiteRunning &&
      activeJobStatus &&
      activeJobStatus.total_test_cases > 0
    ) {
      setDisplayProgress(
        (activeJobStatus.completed_test_cases /
          activeJobStatus.total_test_cases) *
          100,
      );
    }
  }, [activeJobStatus, isThisSuiteRunning]);

  const button = (
    <Button
      type="button"
      onClick={isThisSuiteRunning ? handleStop : handleRun}
      disabled={
        (isThisSuiteRunning && (isStopping || !!stoppingJobId)) ||
        (!isThisSuiteRunning &&
          (isMutating || !!newJobId || isOtherSuiteRunning)) ||
        !suiteSlug
      }
      variant={isThisSuiteRunning ? "destructive" : "default"}
    >
      {isThisSuiteRunning && (isStopping || !!stoppingJobId) ? (
        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
      ) : isThisSuiteRunning ? (
        <Square className="mr-2 h-4 w-4" />
      ) : isMutating || !!newJobId ? (
        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
      ) : (
        <Play className="mr-2 h-4 w-4" />
      )}
      {isThisSuiteRunning ? "Stop Benchmark" : "Run Benchmark"}
    </Button>
  );

  if (isOtherSuiteRunning) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          {/* span captures pointer events that the disabled button swallows */}
          <span className="inline-flex cursor-not-allowed">{button}</span>
        </TooltipTrigger>
        <TooltipContent>
          Another benchmark is currently running (
          {unslug(runningJob!.suite_slug)}). Please wait for it to finish.
        </TooltipContent>
      </Tooltip>
    );
  }

  return (
    <div className="flex flex-col gap-0">
      {isThisSuiteRunning && (
        <Progress value={displayProgress} className="w-full rounded-none">
          <ProgressTrack className="h-0.5 rounded-none bg-primary/20">
            <ProgressIndicator className="bg-primary transition-all duration-700" />
          </ProgressTrack>
        </Progress>
      )}
      {button}
    </div>
  );
};
