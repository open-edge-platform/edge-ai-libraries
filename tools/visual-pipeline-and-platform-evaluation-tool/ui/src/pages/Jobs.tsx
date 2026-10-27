// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router";
import {
  useGetAudioStatusesQuery,
  useGetDensityStatusesQuery,
  useGetOptimizationStatusesQuery,
  useGetPerformanceStatusesQuery,
  useStopAudioJobMutation,
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
import { PipelineName } from "@/features/pipelines/PipelineName.tsx";
import { formatElapsedTimeMillis, formatTimestamp } from "@/lib/timeUtils.ts";
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
  const [stoppingAudioJobIds, setStoppingAudioJobIds] = useState<Set<string>>(
    new Set(),
  );

  const [stopPerformanceTestJob] = useStopPerformanceTestJobMutation();
  const [stopDensityTestJob] = useStopDensityTestJobMutation();
  const [stopAudioJob] = useStopAudioJobMutation();

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

  const { data: audioJobs, isLoading: isLoadingAudio } =
    useGetAudioStatusesQuery(undefined, {
      pollingInterval: 2000,
      skip: currentTab !== "audio",
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

  useEffect(() => {
    if (!audioJobs) return;

    const activeIds = new Set(
      audioJobs
        .filter((job) => job.state === "QUEUED" || job.state === "RUNNING")
        .map((job) => job.id),
    );

    setStoppingAudioJobIds((prev) => {
      if (prev.size === 0) return prev;

      const next = new Set<string>();
      prev.forEach((id) => {
        if (activeIds.has(id)) {
          next.add(id);
        }
      });

      return next;
    });
  }, [audioJobs]);

  const tabs = [
    { id: "performance", label: "Performance", path: "/jobs/performance" },
    { id: "density", label: "Density", path: "/jobs/density" },
    { id: "optimize", label: "Optimize", path: "/jobs/optimize" },
    { id: "audio", label: "Audio", path: "/jobs/audio" },
  ];

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

  const handleStopAudioJob = async (jobId: string) => {
    setStoppingAudioJobIds((prev) => {
      const next = new Set(prev);
      next.add(jobId);
      return next;
    });

    try {
      await stopAudioJob({ jobId }).unwrap();
    } catch (error) {
      setStoppingAudioJobIds((prev) => {
        const next = new Set(prev);
        next.delete(jobId);
        return next;
      });
      handleApiError(error, "Failed to stop audio job");
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
        <div className="border-b border-border mb-6 overflow-x-auto">
          <nav
            className="flex w-max min-w-full justify-between gap-2 pr-2 sm:min-w-max sm:justify-start sm:gap-8"
            aria-label="Tabs"
          >
            {tabs.map((tab) => (
              <Link
                key={tab.id}
                to={tab.path}
                aria-current={currentTab === tab.id ? "page" : undefined}
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

          {currentTab === "audio" && (
            <div className="pb-16">
              <h2 className="text-xl font-semibold mb-4">Audio Jobs</h2>
              {isLoadingAudio ? (
                <p className="text-muted-foreground">Loading jobs...</p>
              ) : !audioJobs || audioJobs.length === 0 ? (
                <p className="text-muted-foreground">No audio jobs found</p>
              ) : (
                <div className="w-full overflow-x-auto">
                  <Table className="mb-10 min-w-[72rem] border-separate border-spacing-4">
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-[8.75rem]">Job ID</TableHead>
                        <TableHead>Pipeline</TableHead>
                        <TableHead>Operation</TableHead>
                        <TableHead>Variant</TableHead>
                        <TableHead>Device</TableHead>
                        <TableHead>State</TableHead>
                        <TableHead>Start Time</TableHead>
                        <TableHead>Elapsed Time</TableHead>
                        <TableHead>Service Latency</TableHead>
                        <TableHead>Artifact</TableHead>
                        <TableHead className="w-[11rem]">Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {audioJobs.map((job) => {
                        const active =
                          job.state === "QUEUED" || job.state === "RUNNING";
                        const startedAt = Date.parse(job.created_at);
                        const endedAt = active
                          ? Date.now()
                          : Date.parse(job.modified_at);

                        return (
                          <TableRow key={job.id}>
                            <TableCell className="font-mono text-xs max-w-[8.75rem]">
                              <Link
                                to={`/jobs/audio/${job.id}`}
                                className="block truncate text-status-link hover:text-status-link-hover hover:underline"
                              >
                                {job.id}
                              </Link>
                            </TableCell>
                            <TableCell>{job.pipeline_name}</TableCell>
                            <TableCell>
                              {job.operation === "speech_to_text"
                                ? "Speech to Text"
                                : "Text to Speech"}
                            </TableCell>
                            <TableCell>{job.variant_name}</TableCell>
                            <TableCell>{job.device}</TableCell>
                            <TableCell>
                              <span
                                className={cn(
                                  "px-2 py-1 text-xs font-medium bg-status-bg text-status-fg",
                                  job.state === "COMPLETED"
                                    ? "status-success"
                                    : active
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
                              {formatTimestamp(startedAt)}
                            </TableCell>
                            <TableCell>
                              {formatElapsedTimeMillis(
                                Math.max(0, endedAt - startedAt),
                              )}
                            </TableCell>
                            <TableCell>
                              {job.service_round_trip_ms == null
                                ? "-"
                                : `${job.service_round_trip_ms.toFixed(2)} ms`}
                            </TableCell>
                            <TableCell>
                              {job.artifact_available ? "Available" : "-"}
                            </TableCell>
                            <TableCell>
                              <div className="flex items-center gap-3">
                                <Link
                                  to={`/jobs/audio/${job.id}`}
                                  className="text-status-link hover:text-status-link-hover hover:underline"
                                >
                                  View
                                </Link>
                                {active && (
                                  <Button
                                    variant="destructive"
                                    size="sm"
                                    onClick={() =>
                                      void handleStopAudioJob(job.id)
                                    }
                                    disabled={stoppingAudioJobIds.has(job.id)}
                                  >
                                    {stoppingAudioJobIds.has(job.id)
                                      ? "Stopping..."
                                      : "Stop"}
                                  </Button>
                                )}
                              </div>
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </>
  );
};
