import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router";
import {
  useGetDensityStatusesQuery,
  useGetOptimizationStatusesQuery,
  useGetPerformanceStatusesQuery,
  useStopDensityTestJobMutation,
  useStopPerformanceTestJobMutation,
} from "@/api/api.generated";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { format } from "date-fns";
import { PipelineName } from "@/features/pipelines/PipelineName.tsx";
import { formatElapsedTimeMillis } from "@/lib/timeUtils.ts";
import { handleApiError } from "@/lib/apiUtils.ts";
import { cn } from "@/lib/utils";

export const Jobs = () => {
  const location = useLocation();
  const currentTab = location.pathname.split("/").pop() || "performance";
  const [stoppingPerformanceJobIds, setStoppingPerformanceJobIds] = useState<
    Set<string>
  >(new Set());
  const [stoppingDensityJobIds, setStoppingDensityJobIds] = useState<
    Set<string>
  >(new Set());

  const [stopPerformanceTestJob] = useStopPerformanceTestJobMutation();
  const [stopDensityTestJob] = useStopDensityTestJobMutation();

  const { data: performanceJobs, isLoading: isLoadingPerformance } =
    useGetPerformanceStatusesQuery(undefined, {
      pollingInterval: 2000,
      skip: currentTab !== "performance",
    });

  const { data: densityJobs, isLoading: isLoadingDensity } =
    useGetDensityStatusesQuery(undefined, {
      pollingInterval: 2000,
      skip: currentTab !== "density",
    });

  const { data: optimizationJobs, isLoading: isLoadingOptimization } =
    useGetOptimizationStatusesQuery(undefined, {
      pollingInterval: 2000,
      skip: currentTab !== "optimize",
    });

  useEffect(() => {
    if (!performanceJobs) return;

    const runningIds = new Set(
      performanceJobs
        .filter((job) => job.state === "RUNNING")
        .map((job) => job.id),
    );

    setStoppingPerformanceJobIds((prev) => {
      if (prev.size === 0) return prev;

      const next = new Set<string>();
      prev.forEach((id) => {
        if (runningIds.has(id)) {
          next.add(id);
        }
      });

      return next;
    });
  }, [performanceJobs]);

  useEffect(() => {
    if (!densityJobs) return;

    const runningIds = new Set(
      densityJobs.filter((job) => job.state === "RUNNING").map((job) => job.id),
    );

    setStoppingDensityJobIds((prev) => {
      if (prev.size === 0) return prev;

      const next = new Set<string>();
      prev.forEach((id) => {
        if (runningIds.has(id)) {
          next.add(id);
        }
      });

      return next;
    });
  }, [densityJobs]);

  const tabs = [
    { id: "performance", label: "Performance", path: "/jobs/performance" },
    { id: "density", label: "Density", path: "/jobs/density" },
    { id: "optimize", label: "Optimize", path: "/jobs/optimize" },
  ];

  const formatTimestamp = (timestamp: number) => {
    return format(new Date(timestamp), "MMM d, yyyy HH:mm:ss");
  };

  const handleStopPerformanceJob = async (jobId: string) => {
    setStoppingPerformanceJobIds((prev) => {
      const next = new Set(prev);
      next.add(jobId);
      return next;
    });

    try {
      await stopPerformanceTestJob({ jobId }).unwrap();
    } catch (error) {
      handleApiError(error, "Failed to stop performance job");
    }
  };

  const handleStopDensityJob = async (jobId: string) => {
    setStoppingDensityJobIds((prev) => {
      const next = new Set(prev);
      next.add(jobId);
      return next;
    });

    try {
      await stopDensityTestJob({ jobId }).unwrap();
    } catch (error) {
      handleApiError(error, "Failed to stop density job");
    }
  };

  return (
    <>
      <div className="container pl-16 mx-auto pt-10 pb-16">
        <div className="mb-6">
          <h1 className="text-3xl font-bold">Jobs</h1>
          <p className="text-muted-foreground mt-2">
            Monitor and manage pipeline jobs
          </p>
        </div>

        {/* Tabs */}
        <div className="border-b border-border mb-6">
          <nav className="flex space-x-8" aria-label="Tabs">
            {tabs.map((tab) => (
              <Link
                key={tab.id}
                to={tab.path}
                className={cn(
                  "py-4 px-1 border-b-2 font-medium text-sm transition-colors",
                  currentTab === tab.id
                    ? "border-foreground text-foreground"
                    : "border-transparent text-foreground/50 hover:text-foreground hover:border-foreground",
                )}
              >
                {tab.label}
              </Link>
            ))}
          </nav>
        </div>

        {/* Tab Content */}
        <div className="mt-6">
          {currentTab === "performance" && (
            <div>
              <h2 className="text-xl font-semibold mb-4">Performance Jobs</h2>
              {isLoadingPerformance ? (
                <p className="text-muted-foreground">Loading jobs...</p>
              ) : !performanceJobs || performanceJobs.length === 0 ? (
                <p className="text-muted-foreground">
                  No performance jobs found
                </p>
              ) : (
                <Table className="mb-10 border-separate border-spacing-4">
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-[8.75rem]">Job ID</TableHead>
                      <TableHead className="w-[13.75rem]">
                        Input Streams
                      </TableHead>
                      <TableHead>State</TableHead>
                      <TableHead>Start Time</TableHead>
                      <TableHead>Elapsed Time</TableHead>
                      <TableHead>Total FPS</TableHead>
                      <TableHead className="max-w-[4.375rem] whitespace-normal">
                        Per Stream FPS
                      </TableHead>
                      <TableHead>Total Streams</TableHead>
                      <TableHead className="w-[7.5rem] min-w-[7.5rem]">
                        Actions
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {performanceJobs.map((job) => (
                      <TableRow key={job.id}>
                        <TableCell className="font-mono text-xs max-w-[8.75rem]">
                          <Link
                            to={`/jobs/performance/${job.id}`}
                            className="block truncate text-brand-accent hover:text-brand-accent-hover hover:underline"
                          >
                            {job.id}
                          </Link>
                        </TableCell>
                        <TableCell className="max-w-[10.625rem] whitespace-normal">
                          <div className="flex flex-col">
                            {job.streams_per_pipeline?.map((pipeline) => (
                              <div
                                key={pipeline.id}
                                className="text-sm truncate"
                              >
                                <PipelineName pipelineId={pipeline.id} />
                                <span className="text-muted-foreground ml-1">
                                  ({pipeline.streams})
                                </span>
                              </div>
                            ))}
                          </div>
                        </TableCell>
                        <TableCell>
                          <span
                            className={cn(
                              "px-2 py-1 text-xs font-medium bg-status-bg text-status-fg",
                              job.state === "COMPLETED"
                                ? "status-success"
                                : job.state === "RUNNING"
                                  ? "status-info"
                                  : job.state === "FAILED"
                                    ? "status-error"
                                    : "bg-status-neutral-bg text-status-neutral-fg",
                            )}
                          >
                            {job.state}
                          </span>
                        </TableCell>
                        <TableCell className="text-xs">
                          {formatTimestamp(job.start_time)}
                        </TableCell>
                        <TableCell>
                          {formatElapsedTimeMillis(job.elapsed_time)}
                        </TableCell>
                        <TableCell>
                          {job.total_fps !== null
                            ? job.total_fps.toFixed(2)
                            : "-"}
                        </TableCell>
                        <TableCell>
                          {job.per_stream_fps !== null
                            ? job.per_stream_fps.toFixed(2)
                            : "-"}
                        </TableCell>
                        <TableCell>{job.total_streams ?? "-"}</TableCell>
                        <TableCell className="w-[7.5rem] min-w-[7.5rem]">
                          {job.state === "RUNNING" ? (
                            <Button
                              variant="destructive"
                              size="sm"
                              className="w-full"
                              onClick={() =>
                                void handleStopPerformanceJob(job.id)
                              }
                              disabled={stoppingPerformanceJobIds.has(job.id)}
                            >
                              {stoppingPerformanceJobIds.has(job.id)
                                ? "Stopping..."
                                : "Stop"}
                            </Button>
                          ) : (
                            <span className="text-muted-foreground">-</span>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </div>
          )}

          {currentTab === "density" && (
            <div className="pb-6 mb-16">
              <h2 className="text-xl font-semibold mb-4">Density Jobs</h2>
              {isLoadingDensity ? (
                <p className="text-muted-foreground">Loading jobs...</p>
              ) : !densityJobs || densityJobs.length === 0 ? (
                <p className="text-muted-foreground">No density jobs found</p>
              ) : (
                <Table className="mb-10 border-spacing-4">
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-[8.75rem]">Job ID</TableHead>
                      <TableHead>State</TableHead>
                      <TableHead>Start Time</TableHead>
                      <TableHead>Elapsed Time</TableHead>
                      <TableHead>Total FPS</TableHead>
                      <TableHead className="max-w-[4.375rem] whitespace-normal">
                        Per Stream FPS
                      </TableHead>
                      <TableHead className="w-[13.75rem]">
                        Stream Distribution
                      </TableHead>
                      <TableHead className="w-[7.5rem] min-w-[7.5rem]">
                        Actions
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {densityJobs.map((job) => (
                      <TableRow key={job.id}>
                        <TableCell className="font-mono text-xs max-w-[8.75rem]">
                          <Link
                            to={`/jobs/density/${job.id}`}
                            className="block truncate text-status-link hover:text-status-link-hover hover:underline"
                          >
                            {job.id}
                          </Link>
                        </TableCell>
                        <TableCell>
                          <span
                            className={cn(
                              "px-2 py-1 text-xs font-medium bg-status-bg text-status-fg",
                              job.state === "COMPLETED"
                                ? "status-success"
                                : job.state === "RUNNING"
                                  ? "status-info"
                                  : job.state === "FAILED"
                                    ? "status-error"
                                    : "bg-status-neutral-bg text-status-neutral-fg",
                            )}
                          >
                            {job.state}
                          </span>
                        </TableCell>
                        <TableCell className="text-xs">
                          {formatTimestamp(job.start_time)}
                        </TableCell>
                        <TableCell>
                          {formatElapsedTimeMillis(job.elapsed_time)}
                        </TableCell>
                        <TableCell>
                          {job.total_fps !== null
                            ? job.total_fps.toFixed(2)
                            : "-"}
                        </TableCell>
                        <TableCell>
                          {job.per_stream_fps !== null
                            ? job.per_stream_fps.toFixed(2)
                            : "-"}
                        </TableCell>
                        <TableCell className="max-w-[13.75rem] whitespace-normal">
                          <div className="flex flex-col">
                            {job.streams_per_pipeline?.map((pipeline) => (
                              <div key={pipeline.id} className="text-sm">
                                <PipelineName pipelineId={pipeline.id} />
                                <span className="text-muted-foreground ml-1">
                                  ({pipeline.streams})
                                </span>
                              </div>
                            ))}
                          </div>
                        </TableCell>
                        <TableCell className="w-[7.5rem] min-w-[7.5rem]">
                          {job.state === "RUNNING" ? (
                            <Button
                              variant="destructive"
                              size="sm"
                              className="w-full"
                              onClick={() => void handleStopDensityJob(job.id)}
                              disabled={stoppingDensityJobIds.has(job.id)}
                            >
                              {stoppingDensityJobIds.has(job.id)
                                ? "Stopping..."
                                : "Stop"}
                            </Button>
                          ) : (
                            <span className="text-muted-foreground">-</span>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </div>
          )}

          {currentTab === "optimize" && (
            <div className="pb-16">
              <h2 className="text-xl font-semibold mb-4">Optimization Jobs</h2>
              {isLoadingOptimization ? (
                <p className="text-muted-foreground">Loading jobs...</p>
              ) : !optimizationJobs || optimizationJobs.length === 0 ? (
                <p className="text-muted-foreground">
                  No optimization jobs found
                </p>
              ) : (
                <Table className="mb-10 border-separate border-spacing-4">
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-[8.75rem]">Job ID</TableHead>
                      <TableHead>Type</TableHead>
                      <TableHead>State</TableHead>
                      <TableHead>Start Time</TableHead>
                      <TableHead>Elapsed Time</TableHead>
                      <TableHead>Total FPS</TableHead>
                      <TableHead className="w-[7.5rem] min-w-[7.5rem]">
                        Actions
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {optimizationJobs.map((job) => (
                      <TableRow key={job.id}>
                        <TableCell className="font-mono text-xs max-w-[8.75rem]">
                          <Link
                            to={`/jobs/optimize/${job.id}`}
                            className="block truncate text-status-link hover:text-status-link-hover hover:underline"
                          >
                            {job.id}
                          </Link>
                        </TableCell>
                        <TableCell>
                          <span className="status-accent px-2 py-1 bg-status-bg text-status-fg text-xs font-medium">
                            {job.type ?? "-"}
                          </span>
                        </TableCell>
                        <TableCell>
                          <span
                            className={cn(
                              "px-2 py-1 text-xs font-medium bg-status-bg text-status-fg",
                              job.state === "COMPLETED"
                                ? "status-success"
                                : job.state === "RUNNING"
                                  ? "status-info"
                                  : job.state === "FAILED"
                                    ? "status-error"
                                    : "bg-status-neutral-bg text-status-neutral-fg",
                            )}
                          >
                            {job.state}
                          </span>
                        </TableCell>
                        <TableCell className="text-xs">
                          {formatTimestamp(job.start_time)}
                        </TableCell>
                        <TableCell>
                          {formatElapsedTimeMillis(job.elapsed_time)}
                        </TableCell>
                        <TableCell>
                          {job.total_fps !== null
                            ? job.total_fps.toFixed(2)
                            : "-"}
                        </TableCell>
                        <TableCell className="w-[7.5rem] min-w-[7.5rem]">
                          <span className="text-muted-foreground">-</span>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </div>
          )}
        </div>
      </div>
    </>
  );
};
