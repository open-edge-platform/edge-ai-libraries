import { Link, useLocation } from "react-router";
import {
  useGetDensityStatusesQuery,
  useGetOptimizationStatusesQuery,
  useGetPerformanceStatusesQuery,
} from "@/api/api.generated";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { format } from "date-fns";
import { PipelineName } from "@/features/pipelines/PipelineName.tsx";
import { formatElapsedTimeMillis } from "@/lib/timeUtils.ts";

export const Jobs = () => {
  const location = useLocation();
  const currentTab = location.pathname.split("/").pop() || "performance";

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

  const tabs = [
    { id: "performance", label: "Performance", path: "/jobs/performance" },
    { id: "density", label: "Density", path: "/jobs/density" },
    { id: "optimize", label: "Optimize", path: "/jobs/optimize" },
  ];

  const formatTimestamp = (timestamp: number) => {
    return format(new Date(timestamp), "MMM d, yyyy HH:mm:ss");
  };

  return (
    <>
      <div className="container mx-auto py-10">
        <div className="mb-6">
          <h1 className="text-3xl font-bold">Jobs</h1>
          <p className="text-muted-foreground mt-2">
            Monitor and manage pipeline jobs
          </p>
        </div>

        {/* Tabs */}
        <div className="border-b border-gray-200 dark:border-gray-700 mb-6">
          <nav className="flex space-x-8" aria-label="Tabs">
            {tabs.map((tab) => (
              <Link
                key={tab.id}
                to={tab.path}
                className={`
                  py-4 px-1 border-b-2 font-medium text-sm transition-colors
                  ${
                    currentTab === tab.id
                      ? "border-foreground text-foreground"
                      : "border-transparent text-foreground/50 hover:text-foreground hover:border-foreground dark:text-foreground/50 dark:hover:text-foreground"
                  }
                `}
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
                <div className="border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Job ID</TableHead>
                        <TableHead>Input Streams</TableHead>
                        <TableHead>State</TableHead>
                        <TableHead>Start Time</TableHead>
                        <TableHead>Elapsed Time</TableHead>
                        <TableHead>Total FPS</TableHead>
                        <TableHead>Per Stream FPS</TableHead>
                        <TableHead>Total Streams</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {performanceJobs.map((job) => (
                        <TableRow key={job.id}>
                          <TableCell className="font-mono text-xs">
                            <Link
                              to={`/jobs/performance/${job.id}`}
                              className="text-classic-blue hover:text-classic-blue-hover dark:text-energy-blue dark:hover:text-energy-blue-shade-1 hover:underline"
                            >
                              {job.id}
                            </Link>
                          </TableCell>
                          <TableCell>
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
                          <TableCell>
                            <span
                              className={`px-2 py-1 text-xs font-medium ${
                                job.state === "COMPLETED"
                                  ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
                                  : job.state === "RUNNING"
                                    ? "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200"
                                    : job.state === "ERROR"
                                      ? "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200"
                                      : "bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200"
                              }`}
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
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </div>
          )}

          {currentTab === "density" && (
            <div>
              <h2 className="text-xl font-semibold mb-4">Density Jobs</h2>
              {isLoadingDensity ? (
                <p className="text-muted-foreground">Loading jobs...</p>
              ) : !densityJobs || densityJobs.length === 0 ? (
                <p className="text-muted-foreground">No density jobs found</p>
              ) : (
                <div className="border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Job ID</TableHead>
                        <TableHead>State</TableHead>
                        <TableHead>Start Time</TableHead>
                        <TableHead>Elapsed Time</TableHead>
                        <TableHead>Total FPS</TableHead>
                        <TableHead>Per Stream FPS</TableHead>
                        <TableHead>Stream Distribution</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {densityJobs.map((job) => (
                        <TableRow key={job.id}>
                          <TableCell className="font-mono text-xs">
                            <Link
                              to={`/jobs/density/${job.id}`}
                              className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 hover:underline"
                            >
                              {job.id}
                            </Link>
                          </TableCell>
                          <TableCell>
                            <span
                              className={`px-2 py-1 text-xs font-medium ${
                                job.state === "COMPLETED"
                                  ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
                                  : job.state === "RUNNING"
                                    ? "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200"
                                    : job.state === "ERROR"
                                      ? "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200"
                                      : "bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200"
                              }`}
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
                          <TableCell>
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
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </div>
          )}

          {currentTab === "optimize" && (
            <div>
              <h2 className="text-xl font-semibold mb-4">Optimization Jobs</h2>
              {isLoadingOptimization ? (
                <p className="text-muted-foreground">Loading jobs...</p>
              ) : !optimizationJobs || optimizationJobs.length === 0 ? (
                <p className="text-muted-foreground">
                  No optimization jobs found
                </p>
              ) : (
                <div className="border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Job ID</TableHead>
                        <TableHead>Type</TableHead>
                        <TableHead>State</TableHead>
                        <TableHead>Start Time</TableHead>
                        <TableHead>Elapsed Time</TableHead>
                        <TableHead>Total FPS</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {optimizationJobs.map((job) => (
                        <TableRow key={job.id}>
                          <TableCell className="font-mono text-xs">
                            <Link
                              to={`/jobs/optimize/${job.id}`}
                              className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 hover:underline"
                            >
                              {job.id}
                            </Link>
                          </TableCell>
                          <TableCell>
                            <span className="px-2 py-1 bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200 text-xs font-medium">
                              {job.type ?? "-"}
                            </span>
                          </TableCell>
                          <TableCell>
                            <span
                              className={`px-2 py-1 text-xs font-medium ${
                                job.state === "COMPLETED"
                                  ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
                                  : job.state === "RUNNING"
                                    ? "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200"
                                    : job.state === "ERROR"
                                      ? "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200"
                                      : "bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200"
                              }`}
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
                        </TableRow>
                      ))}
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
