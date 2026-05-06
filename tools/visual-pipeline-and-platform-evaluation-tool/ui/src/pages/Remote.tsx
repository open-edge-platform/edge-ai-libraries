import { useEffect, useState } from "react";
import {
  useRunRemotePerformanceTestMutation,
  useStopRemotePerformanceTestJobMutation,
  useRunRemoteDensityTestMutation,
  useStopRemoteDensityTestJobMutation,
  useGetRemotePerformanceJobStatusQuery,
  useGetRemoteDensityJobStatusQuery,
} from "@/api/remoteApi";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatElapsedTimeMillis } from "@/lib/timeUtils.ts";
import { PipelineName } from "@/features/pipelines/PipelineName.tsx";
import { useAppSelector } from "@/store/hooks";
import { selectPipelines } from "@/store/reducers/pipelines";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group.tsx";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Plus, Square, X, Server } from "lucide-react";
import { StreamsSlider } from "@/features/pipeline-tests/StreamsSlider.tsx";
import { ParticipationSlider } from "@/features/pipeline-tests/ParticipationSlider.tsx";
import SaveOutputWarning from "@/features/pipeline-tests/SaveOutputWarning.tsx";
import {
  handleApiError,
  isAsyncJobError,
} from "@/lib/apiUtils";
import { formatErrorMessage } from "@/lib/utils.ts";
import { useStreamRateChange } from "@/hooks/useStreamRateChange.ts";
import type { Pipeline } from "@/api/api.generated";
import { API_BASE_URL } from "@/api/apiSlice.ts";

type TestType = "performance" | "density";

interface ServerInfo {
  uuid: string;
  ip_address: string;
  cpu_sku: string;
  ram_size: number;
  kernel_version: string;
}

interface PipelineSelection {
  pipelineId: string;
  variantId: string;
  streams?: number;
  stream_rate?: number;
  isRemoving?: boolean;
  isNew?: boolean;
}

interface ServerJobState {
  serverId: string;
  serverIp: string;
  jobId: string | null;
  isRunning: boolean;
  isStopping: boolean;
  status: any;
  result: any;
  error: string | null;
}

// Helper function to detect if a pipeline variant contains camera input
const containsCameraInputInPipeline = (
  pipeline: Pipeline,
  variantId: string,
): boolean => {
  const variant = pipeline.variants.find((v) => v.id === variantId);
  if (!variant) return false;

  const nodes =
    variant.pipeline_graph?.nodes || variant.pipeline_graph_simple?.nodes || [];
  return nodes.some((node) => {
    if (node.type === "source") {
      const sourceType = node.data?.source || "";
      return sourceType.startsWith("/dev/") || sourceType.startsWith("rtsp://");
    }
    return false;
  });
};

export const Remote = () => {
  const DEFAULT_LOOPING_RUNTIME_SECONDS = 60;
  const DEFAULT_DENSITY_RUNTIME_SECONDS = 10;
  const pipelines = useAppSelector(selectPipelines);
  
  const [servers, setServers] = useState<ServerInfo[]>([]);
  const [selectedServerIds, setSelectedServerIds] = useState<string[]>([]);
  const [isLoadingServers, setIsLoadingServers] = useState(true);
  const [testType, setTestType] = useState<TestType>("performance");
  
  const [pipelineSelections, setPipelineSelections] = useState<
    PipelineSelection[]
  >([]);
  
  // Performance test specific
  const [videoOutputEnabled, setVideoOutputEnabled] = useState(false);
  const [livePreviewEnabled, setLivePreviewEnabled] = useState(false);
  
  // Density test specific
  const [fpsFloor, setFpsFloor] = useState<number>(30);
  
  // Common
  const [loopingEnabled, setLoopingEnabled] = useState(false);
  const [loopingRuntimeSeconds, setLoopingRuntimeSeconds] = useState(
    DEFAULT_LOOPING_RUNTIME_SECONDS,
  );
  const [loopingRuntimeInput, setLoopingRuntimeInput] = useState(
    String(DEFAULT_LOOPING_RUNTIME_SECONDS),
  );
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<any>(null);
  
  // Multi-server job tracking
  const [serverJobs, setServerJobs] = useState<Record<string, ServerJobState>>({});
  
  const handleStreamRateChange = useStreamRateChange(setPipelineSelections);

  // Remote API mutation hooks (not using useAsyncJob for multi-server support)
  const [runPerformanceTest] = useRunRemotePerformanceTestMutation();
  const [runDensityTest] = useRunRemoteDensityTestMutation();
  const [stopPerformanceTest] = useStopRemotePerformanceTestJobMutation();
  const [stopDensityTest] = useStopRemoteDensityTestJobMutation();

  // Derive running state from serverJobs
  const isRunning = (Object.values(serverJobs) as ServerJobState[]).some((job) => job.isRunning);
  const isStopping = (Object.values(serverJobs) as ServerJobState[]).some((job) => job.isStopping);

  // Poll job status for each server
  useEffect(() => {
    const jobsToMonitor = (Object.values(serverJobs) as ServerJobState[]).filter(
      (job) => job.jobId && (job.isRunning || job.isStopping)
    );

    if (jobsToMonitor.length === 0) return;

    const interval = setInterval(async () => {
      for (const job of jobsToMonitor) {
        try {
          const response = await fetch(
            `http://${job.serverIp}/api/v1/jobs/tests/${testType}/${job.jobId}/status`
          );
          
          if (response.ok) {
            const status = await response.json();
            
            setServerJobs((prev) => ({
              ...prev,
              [job.serverId]: {
                ...prev[job.serverId],
                status,
                isRunning: status.state === "RUNNING",
                isStopping: prev[job.serverId].isStopping && status.state === "RUNNING",
              },
            }));
          }
        } catch (error) {
          console.error(`Failed to poll status for job ${job.jobId} on ${job.serverIp}:`, error);
        }
      }
    }, 2000); // Poll every 2 seconds

    return () => clearInterval(interval);
  }, [serverJobs, testType]);

  // Fetch servers on mount
  useEffect(() => {
    const fetchServers = async () => {
      setIsLoadingServers(true);
      try {
        const response = await fetch(`${API_BASE_URL}/servers`);
        if (!response.ok) {
          throw new Error("Failed to fetch servers");
        }
        const data = await response.json();
        setServers(data.servers || []);
        if (data.servers && data.servers.length > 0) {
          setSelectedServerIds([data.servers[0].uuid]);
        }
      } catch (error) {
        handleApiError(error, "Failed to load servers");
      } finally {
        setIsLoadingServers(false);
      }
    };

    fetchServers();
  }, []);

  // Initialize pipeline selections
  useEffect(() => {
    if (pipelines.length > 0 && pipelineSelections.length === 0) {
      const firstPipeline = pipelines[0];
      const firstVariant = firstPipeline.variants[0];
      setPipelineSelections([
        {
          pipelineId: firstPipeline.id,
          variantId: firstVariant.id,
          streams: testType === "performance" ? 8 : undefined,
          stream_rate: testType === "density" ? 100 : undefined,
          isNew: false,
        },
      ]);
    }
  }, [pipelines, pipelineSelections.length, testType]);

  // Update default runtime when test type changes
  useEffect(() => {
    const defaultRuntime =
      testType === "performance"
        ? DEFAULT_LOOPING_RUNTIME_SECONDS
        : DEFAULT_DENSITY_RUNTIME_SECONDS;
    setLoopingRuntimeSeconds(defaultRuntime);
    setLoopingRuntimeInput(String(defaultRuntime));
  }, [testType]);

  const handleAddPipeline = () => {
    if (pipelines.length > 0) {
      const usedPipelineIds = pipelineSelections.map((sel) => sel.pipelineId);
      const availablePipeline = pipelines.find(
        (p) => !usedPipelineIds.includes(p.id),
      );
      
      if (availablePipeline) {
        const firstVariant = availablePipeline.variants[0];
        setPipelineSelections((prev) => [
          ...prev,
          {
            pipelineId: availablePipeline.id,
            variantId: firstVariant.id,
            streams: testType === "performance" ? 8 : undefined,
            stream_rate: testType === "density" ? 100 : undefined,
            isNew: true,
          },
        ]);
        setTimeout(() => {
          setPipelineSelections((prev) =>
            prev.map((sel, idx) =>
              idx === prev.length - 1 ? { ...sel, isNew: false } : sel,
            ),
          );
        }, 300);
      }
    }
  };

  const handleRemovePipeline = (index: number) => {
    if (pipelineSelections.length > 1) {
      setPipelineSelections((prev) =>
        prev.map((sel, idx) =>
          idx === index ? { ...sel, isRemoving: true } : sel,
        ),
      );
      setTimeout(() => {
        setPipelineSelections((prev) => prev.filter((_, idx) => idx !== index));
      }, 300);
    }
  };

  const handlePipelineChange = (index: number, newPipelineId: string) => {
    setPipelineSelections((prev) =>
      prev.map((sel, idx) => {
        if (idx === index) {
          const newPipeline = pipelines.find((p) => p.id === newPipelineId);
          const firstVariant = newPipeline?.variants[0];
          return {
            ...sel,
            pipelineId: newPipelineId,
            variantId: firstVariant?.id || sel.variantId,
          };
        }
        return sel;
      }),
    );
  };

  const handleVariantChange = (index: number, newVariantId: string) => {
    setPipelineSelections((prev) =>
      prev.map((sel, idx) =>
        idx === index ? { ...sel, variantId: newVariantId } : sel,
      ),
    );
  };

  const handleStreamsChange = (index: number, streams: number) => {
    setPipelineSelections((prev) =>
      prev.map((sel, idx) =>
        idx === index ? { ...sel, streams } : sel,
      ),
    );
  };

  const handleRunTest = async () => {
    if (selectedServerIds.length === 0) {
      setErrorMessage("Please select at least one server");
      return;
    }

    setTestResult(null);
    setErrorMessage(null);

    // Initialize job state for all selected servers
    const initialJobs: Record<string, ServerJobState> = {};
    selectedServers.forEach((server) => {
      initialJobs[server.uuid] = {
        serverId: server.uuid,
        serverIp: server.ip_address,
        jobId: null,
        isRunning: true,
        isStopping: false,
        status: null,
        result: null,
        error: null,
      };
    });
    setServerJobs(initialJobs);

    // Build test spec once for all servers
    const hasCameraInput = pipelineSelections.some((selection) => {
      const pipeline = pipelines.find((p) => p.id === selection.pipelineId);
      return pipeline
        ? containsCameraInputInPipeline(pipeline, selection.variantId)
        : false;
    });

    // Run tests on all servers in parallel
    const testPromises = selectedServers.map(async (server) => {
      try {
        let jobResponse: any;
        
        if (testType === "performance") {
          const adjustedLivePreviewMaxRuntime = hasCameraInput ? 0 : 30 * 60;
          
          jobResponse = await runPerformanceTest({
            performanceTestSpec: {
              execution_config: {
                output_mode: livePreviewEnabled
                  ? "live_stream"
                  : videoOutputEnabled
                    ? "file"
                    : "disabled",
                max_runtime: livePreviewEnabled
                  ? adjustedLivePreviewMaxRuntime
                  : loopingEnabled
                    ? loopingRuntimeSeconds
                    : 0,
              },
              pipeline_performance_specs: pipelineSelections.map((selection) => ({
                pipeline: {
                  source: "variant",
                  pipeline_id: selection.pipelineId,
                  variant_id: selection.variantId,
                },
                streams: selection.streams || 1,
              })),
            },
            serverIp: server.ip_address,
          }).unwrap();
        } else {
          // Density test
          jobResponse = await runDensityTest({
            densityTestSpec: {
              execution_config: {
                output_mode: "disabled",
                max_runtime: loopingEnabled ? loopingRuntimeSeconds : 0,
              },
              pipeline_density_specs: pipelineSelections.map((selection) => ({
                pipeline: {
                  source: "variant",
                  pipeline_id: selection.pipelineId,
                  variant_id: selection.variantId,
                },
                stream_rate: selection.stream_rate || 100,
              })),
              fps_floor: fpsFloor,
            },
            serverIp: server.ip_address,
          }).unwrap();
        }

        // Store the job ID
        const jobId = jobResponse.job_id;
        setServerJobs((prev) => ({
          ...prev,
          [server.uuid]: {
            ...prev[server.uuid],
            jobId,
            isRunning: true,
            result: { message: `Test job ${jobId} started successfully` },
          },
        }));

        return { serverId: server.uuid, success: true, jobId };
      } catch (error) {
        const errorMsg = isAsyncJobError(error)
          ? formatErrorMessage((error as any)?.details, "Test failed")
          : handleApiError(error, "Test failed");

        // Update this server's job state with error
        setServerJobs((prev) => ({
          ...prev,
          [server.uuid]: {
            ...prev[server.uuid],
            isRunning: false,
            error: errorMsg,
          },
        }));

        return { serverId: server.uuid, success: false, error: errorMsg };
      }
    });

    // Wait for all tests to complete
    const results = await Promise.allSettled(testPromises);
    
    // Check if all tests failed
    const allFailed = results.every(
      (r) => r.status === "rejected" || (r.status === "fulfilled" && !r.value.success)
    );
    
    if (allFailed) {
      setErrorMessage("All server tests failed");
    } else {
      setErrorMessage(null);
    }
  };

  const handleStopTest = async () => {
    // Stop all running jobs across all servers
    const runningJobs = (Object.values(serverJobs) as ServerJobState[]).filter(
      (job) => job.isRunning && job.jobId
    );

    if (runningJobs.length === 0) return;

    // Mark all as stopping
    setServerJobs((prev) => {
      const updated = { ...prev };
      runningJobs.forEach((job) => {
        updated[job.serverId] = { ...updated[job.serverId], isStopping: true };
      });
      return updated;
    });

    // Stop all jobs in parallel
    const stopPromises = runningJobs.map(async (job) => {
      try {
        if (testType === "performance") {
          await stopPerformanceTest({
            jobId: job.jobId!,
            serverIp: job.serverIp,
          }).unwrap();
        } else {
          await stopDensityTest({
            jobId: job.jobId!,
            serverIp: job.serverIp,
          }).unwrap();
        }

        // Update job state to stopped
        setServerJobs((prev) => ({
          ...prev,
          [job.serverId]: {
            ...prev[job.serverId],
            isRunning: false,
            isStopping: false,
          },
        }));
      } catch (error) {
        handleApiError(error, `Failed to stop test on ${job.serverIp}`);
        
        // Still mark as not running even if stop failed
        setServerJobs((prev) => ({
          ...prev,
          [job.serverId]: {
            ...prev[job.serverId],
            isRunning: false,
            isStopping: false,
          },
        }));
      }
    });

    await Promise.allSettled(stopPromises);
  };

  const selectedServers = servers.filter((s) =>
    selectedServerIds.includes(s.uuid),
  );

  const toggleServerSelection = (serverId: string) => {
    setSelectedServerIds((prev) =>
      prev.includes(serverId)
        ? prev.filter((id) => id !== serverId)
        : [...prev, serverId],
    );
  };

  const selectAllServers = () => {
    setSelectedServerIds(servers.map((s) => s.uuid));
  };

  const deselectAllServers = () => {
    setSelectedServerIds([]);
  };

  if (pipelines.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <p>Loading pipelines...</p>
      </div>
    );
  }

  return (
    <div className="container pl-16 mx-auto py-10">
      <div className="mb-6">
        <h1 className="text-3xl font-bold">Remote Tests</h1>
        <p className="text-muted-foreground mt-2">
          Run performance or density tests on remote servers
        </p>
      </div>

      {/* Server Selection */}
      <div className="mb-6 p-4 border bg-card">
        <div className="flex items-center justify-between mb-3">
          <label className="text-sm font-medium">
            Select Remote Servers ({selectedServerIds.length} selected)
          </label>
          {servers.length > 0 && (
            <div className="flex gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={selectAllServers}
                disabled={isRunning}
              >
                Select All
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={deselectAllServers}
                disabled={isRunning}
              >
                Deselect All
              </Button>
            </div>
          )}
        </div>
        {isLoadingServers ? (
          <p className="text-sm text-muted-foreground">Loading servers...</p>
        ) : servers.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No servers available. Please register a server first.
          </p>
        ) : (
          <>
            <div className="space-y-2 mb-3">
              {servers.map((server) => (
                <label
                  key={server.uuid}
                  className={`flex items-center gap-3 p-3 border rounded-md cursor-pointer transition-colors ${
                    selectedServerIds.includes(server.uuid)
                      ? "bg-primary/5 border-primary"
                      : "hover:bg-muted/50"
                  } ${isRunning ? "opacity-50 cursor-not-allowed" : ""}`}
                >
                  <Checkbox
                    checked={selectedServerIds.includes(server.uuid)}
                    disabled={isRunning}
                    onCheckedChange={() => toggleServerSelection(server.uuid)}
                  />
                  <Server className="w-4 h-4 text-muted-foreground" />
                  <div className="flex-1">
                    <div className="font-medium text-sm">
                      {server.ip_address}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {server.cpu_sku} • {server.ram_size}GB RAM • {server.kernel_version}
                    </div>
                  </div>
                </label>
              ))}
            </div>
            
            {selectedServers.length > 0 && (
              <div className="mt-3 p-3 bg-muted/50 rounded-md">
                <p className="text-xs font-medium text-muted-foreground mb-2">
                  Selected Servers Summary:
                </p>
                <div className="space-y-1">
                  {selectedServers.map((server) => (
                    <div key={server.uuid} className="text-xs">
                      <span className="font-mono">{server.ip_address}</span>
                      {" • "}
                      <span className="text-muted-foreground">
                        {server.cpu_sku}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* Test Type Selection */}
      <div className="mb-6 p-4 border bg-card">
        <label className="block text-sm font-medium mb-3">Test Type</label>
        <RadioGroup
          value={testType}
          onValueChange={(value: TestType) => {
            setTestType(value);
            // Reset test-specific options
            setVideoOutputEnabled(false);
            setLivePreviewEnabled(false);
            setLoopingEnabled(false);
          }}
          disabled={isRunning}
        >
          <div className="flex items-center space-x-2">
            <RadioGroupItem value="performance" id="performance" />
            <label htmlFor="performance" className="text-sm cursor-pointer">
              Performance Test - Measures total and per-stream FPS
            </label>
          </div>
          <div className="flex items-center space-x-2">
            <RadioGroupItem value="density" id="density" />
            <label htmlFor="density" className="text-sm cursor-pointer">
              Density Test - Finds maximum streams at target FPS
            </label>
          </div>
        </RadioGroup>
      </div>

      {/* Pipeline Configuration */}
      <div className="space-y-3 mb-6">
        {pipelineSelections.map((selection, index) => {
          const selectedPipeline = pipelines.find(
            (p) => p.id === selection.pipelineId,
          );
          return (
            <div
              key={`${selection.pipelineId}-${index}`}
              className={`flex items-center gap-3 p-2 border bg-card transition-all duration-300 ${
                selection.isRemoving
                  ? "opacity-0 -translate-y-2"
                  : selection.isNew
                    ? "animate-in fade-in slide-in-from-top-2"
                    : ""
              }`}
            >
              <div className="flex-1 flex items-center gap-4">
                <div className="flex-1">
                  <label className="block text-sm font-medium mb-1">
                    Pipeline
                  </label>
                  <Select
                    value={selection.pipelineId}
                    disabled={isRunning}
                    onValueChange={(value) =>
                      handlePipelineChange(index, value)
                    }
                  >
                    <SelectTrigger className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {pipelines.map((pipeline) => (
                        <SelectItem key={pipeline.id} value={pipeline.id}>
                          {pipeline.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="flex-1">
                  <label className="block text-sm font-medium mb-1">
                    Variant
                  </label>
                  <Select
                    value={selection.variantId}
                    disabled={isRunning}
                    onValueChange={(value) =>
                      handleVariantChange(index, value)
                    }
                  >
                    <SelectTrigger className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {selectedPipeline?.variants.map((variant) => (
                        <SelectItem key={variant.id} value={variant.id}>
                          {variant.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="flex-1">
                  {testType === "performance" ? (
                    <>
                      <label className="block text-sm font-medium mb-1">
                        Streams
                      </label>
                      <StreamsSlider
                        value={selection.streams || 8}
                        onChange={(val) => handleStreamsChange(index, val)}
                        min={1}
                        max={64}
                        disabled={isRunning}
                      />
                    </>
                  ) : (
                    <>
                      <label className="block text-sm font-medium mb-1">
                        Participation
                      </label>
                      <ParticipationSlider
                        value={selection.stream_rate || 100}
                        onChange={(val) =>
                          handleStreamRateChange(index, val)
                        }
                        disabled={isRunning}
                      />
                    </>
                  )}
                </div>
              </div>

              {pipelineSelections.length > 1 && (
                <Button
                  onClick={() => handleRemovePipeline(index)}
                  variant="ghost"
                  size="icon"
                  className="text-destructive"
                  disabled={isRunning}
                >
                  <X className="w-5 h-5" />
                </Button>
              )}
            </div>
          );
        })}

        <Button
          onClick={handleAddPipeline}
          variant="outline"
          disabled={isRunning || (testType === "density" && pipelineSelections.length >= pipelines.length)}
        >
          <Plus className="w-5 h-5" />
          <span>Add Pipeline</span>
        </Button>
      </div>

      {/* Test Options */}
      <div className="my-4 flex flex-col gap-2">
        <div className="flex items-center gap-6 flex-wrap">
          {testType === "performance" && (
            <>
              <Tooltip>
                <TooltipTrigger asChild>
                  <label className="flex items-center gap-2 cursor-pointer h-[42px]">
                    <Checkbox
                      checked={videoOutputEnabled}
                      disabled={isRunning}
                      onCheckedChange={(checked) => {
                        const isChecked = checked === true;
                        setVideoOutputEnabled(isChecked);
                        if (isChecked) {
                          setLivePreviewEnabled(false);
                          setLoopingEnabled(false);
                        }
                      }}
                    />
                    <span className="text-sm font-medium">
                      Keep pipeline output
                    </span>
                  </label>
                </TooltipTrigger>
                <TooltipContent side="bottom">
                  <p>Save pipeline output to files for viewing</p>
                </TooltipContent>
              </Tooltip>

              <Tooltip>
                <TooltipTrigger asChild>
                  <label className="flex items-center gap-2 cursor-pointer h-[42px]">
                    <Checkbox
                      checked={livePreviewEnabled}
                      disabled={isRunning}
                      onCheckedChange={(checked) => {
                        const isChecked = checked === true;
                        setLivePreviewEnabled(isChecked);
                        if (isChecked) {
                          setVideoOutputEnabled(false);
                          setLoopingEnabled(false);
                        }
                      }}
                    />
                    <span className="text-sm font-medium">
                      Enable live preview
                    </span>
                  </label>
                </TooltipTrigger>
                <TooltipContent side="bottom">
                  <p>Stream pipeline output live</p>
                </TooltipContent>
              </Tooltip>
            </>
          )}

          {testType === "density" && (
            <div className="flex items-center gap-2">
              <label className="text-sm font-medium">Target FPS:</label>
              <Input
                type="number"
                value={fpsFloor}
                disabled={isRunning}
                onChange={(e) => setFpsFloor(Number(e.target.value))}
                className="h-9 w-24"
                min={1}
              />
            </div>
          )}

          <Tooltip>
            <TooltipTrigger asChild>
              <label className="flex items-center gap-2 cursor-pointer h-[42px]">
                <Checkbox
                  checked={loopingEnabled}
                  disabled={
                    isRunning ||
                    pipelineSelections.some((selection) => {
                      const pipeline = pipelines.find(
                        (p) => p.id === selection.pipelineId,
                      );
                      return pipeline
                        ? containsCameraInputInPipeline(
                            pipeline,
                            selection.variantId,
                          )
                        : false;
                    })
                  }
                  onCheckedChange={(checked) => {
                    const isChecked = checked === true;
                    setLoopingEnabled(isChecked);
                    if (isChecked && testType === "performance") {
                      setVideoOutputEnabled(false);
                      setLivePreviewEnabled(false);
                    }
                  }}
                />
                <span className="text-sm font-medium">
                  Run pipeline in loop
                </span>
              </label>
            </TooltipTrigger>
            <TooltipContent side="bottom">
              <p>Run test in loop mode for a selected duration</p>
            </TooltipContent>
          </Tooltip>
        </div>

        {loopingEnabled && (
          <div className="ml-6 flex items-center gap-2">
            <span className="text-xs text-muted-foreground">Duration</span>
            <Input
              type="text"
              inputMode="numeric"
              pattern="[0-9]*"
              value={loopingRuntimeInput}
              disabled={isRunning}
              onChange={(event) => {
                const value = event.target.value;
                if (value !== "" && !/^\d+$/.test(value)) {
                  return;
                }
                setLoopingRuntimeInput(value);
                if (value !== "") {
                  setLoopingRuntimeSeconds(Number.parseInt(value, 10));
                }
              }}
              onBlur={() => {
                const defaultRuntime =
                  testType === "performance"
                    ? DEFAULT_LOOPING_RUNTIME_SECONDS
                    : DEFAULT_DENSITY_RUNTIME_SECONDS;
                const parsedValue =
                  loopingRuntimeInput.trim().length === 0
                    ? Number.NaN
                    : Number.parseInt(loopingRuntimeInput, 10);
                const normalizedValue =
                  Number.isFinite(parsedValue) && parsedValue >= 1
                    ? parsedValue
                    : defaultRuntime;

                setLoopingRuntimeSeconds(normalizedValue);
                setLoopingRuntimeInput(String(normalizedValue));
              }}
              className="h-8 w-24 px-2 text-xs"
            />
            <span className="text-xs text-muted-foreground">s</span>
          </div>
        )}

        {videoOutputEnabled && <SaveOutputWarning />}
      </div>

      {/* Run/Stop Button */}
      {isRunning ? (
        <button
          onClick={handleStopTest}
          disabled={isStopping}
          className="w-[160px] bg-red-600 dark:bg-[#f88f8f] dark:text-[#242528] dark:hover:bg-red-400 font-medium hover:bg-red-700 disabled:bg-gray-400 text-white px-3 py-2 shadow-lg transition-colors flex items-center justify-center gap-2"
        >
          <Square className="w-5 h-5" />
          <span>{isStopping ? "Stopping..." : "Stop"}</span>
        </button>
      ) : (
        <Button
          onClick={handleRunTest}
          disabled={
            isRunning ||
            selectedServerIds.length === 0 ||
            pipelineSelections.length === 0
          }
          className="self-start"
        >
          {isRunning
            ? "Starting..."
            : `Run ${testType === "performance" ? "performance" : "density"} test on ${selectedServerIds.length} server${selectedServerIds.length !== 1 ? "s" : ""}`}
        </Button>
      )}

      {/* Error Message */}
      {errorMessage && (
        <div className="my-4 p-3 bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800">
          <p className="text-sm font-medium text-red-900 dark:text-red-100 mb-2">
            Test Failed
          </p>
          <p className="text-xs text-red-700 dark:text-red-300">
            {errorMessage}
          </p>
        </div>
      )}

      {/* Test Results */}
      {testResult && (
        <div className="my-4 p-3 bg-green-50 dark:bg-green-950 border border-green-200 dark:border-green-800">
          <p className="text-sm font-medium text-green-900 dark:text-green-100 mb-2">
            Test Completed Successfully
          </p>
          <div className="space-y-1 text-sm">
            {testType === "performance" ? (
              <>
                <p className="text-green-800 dark:text-green-200">
                  <span className="font-medium">Total FPS:</span>{" "}
                  {testResult.total_fps?.toFixed(2) ?? "N/A"}
                </p>
                <p className="text-green-800 dark:text-green-200">
                  <span className="font-medium">Per Stream FPS:</span>{" "}
                  {testResult.per_stream_fps?.toFixed(2) ?? "N/A"}
                </p>
              </>
            ) : (
              <>
                <p className="text-green-800 dark:text-green-200">
                  <span className="font-medium">Total Streams:</span>{" "}
                  {testResult.total_streams ?? "N/A"}
                </p>
                <p className="text-green-800 dark:text-green-200">
                  <span className="font-medium">Per Stream FPS:</span>{" "}
                  {testResult.per_stream_fps?.toFixed(2) ?? "N/A"}
                </p>
                {testResult.streams_per_pipeline && (
                  <div className="mt-3">
                    <PipelineStreamsSummary
                      streams_per_pipeline={testResult.streams_per_pipeline}
                    />
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}

      {/* Server Job Comparison Table */}
      {Object.keys(serverJobs).length > 0 && (
        <div className="my-6">
          {console.log("serverJobs:", serverJobs)}
          <h3 className="text-xl font-semibold mb-4">Server Test Comparison</h3>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[180px]">Server</TableHead>
                <TableHead className="w-[140px]">Job ID</TableHead>
                <TableHead className="w-[220px]">Input Streams</TableHead>
                <TableHead>State</TableHead>
                <TableHead>Elapsed Time</TableHead>
                {testType === "performance" ? (
                  <>
                    <TableHead>Total FPS</TableHead>
                    <TableHead>Per Stream FPS</TableHead>
                    <TableHead>Total Streams</TableHead>
                  </>
                ) : (
                  <>
                    <TableHead>Total Streams</TableHead>
                    <TableHead>Per Stream FPS</TableHead>
                    <TableHead>FPS Floor</TableHead>
                  </>
                )}
                <TableHead>Error</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {Object.values(serverJobs).map((job) => {
                const server = servers.find((s) => s.uuid === job.serverId);
                if (!server) return null;

                return (
                  <TableRow key={job.serverId}>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <Server className="w-4 h-4 text-muted-foreground" />
                        <div>
                          <div className="font-medium text-sm">
                            {server.ip_address}
                          </div>
                          <div className="text-xs text-muted-foreground">
                            {server.cpu_sku}
                          </div>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {job.jobId ? (
                        <span className="text-classic-blue dark:text-energy-blue">
                          {job.jobId}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">-</span>
                      )}
                    </TableCell>
                    <TableCell className="max-w-[220px] whitespace-normal">
                      <div className="flex flex-col">
                        {pipelineSelections.map((selection) => (
                          <div
                            key={selection.pipelineId}
                            className="text-sm truncate"
                          >
                            <PipelineName pipelineId={selection.pipelineId} />
                            <span className="text-muted-foreground ml-1">
                              ({testType === "performance" ? selection.streams || 1 : `${selection.stream_rate || 100}%`})
                            </span>
                          </div>
                        ))}
                      </div>
                    </TableCell>
                    <TableCell>
                      <span
                        className={`px-2 py-1 text-xs font-medium rounded ${
                          job.error
                            ? "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200"
                            : job.status?.state === "RUNNING"
                              ? "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200"
                              : job.status?.state === "COMPLETED"
                                ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
                                : job.status?.state === "FAILED"
                                  ? "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200"
                                  : "bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200"
                        }`}
                      >
                        {job.error
                          ? "FAILED"
                          : job.status?.state || "-"}
                      </span>
                    </TableCell>
                    <TableCell>
                      {job.status?.elapsed_time !== undefined
                        ? formatElapsedTimeMillis(job.status.elapsed_time)
                        : "-"}
                    </TableCell>
                    {testType === "performance" ? (
                      <>
                        <TableCell>
                          {job.status?.total_fps !== null && job.status?.total_fps !== undefined
                            ? job.status.total_fps.toFixed(2)
                            : "-"}
                        </TableCell>
                        <TableCell>
                          {job.status?.per_stream_fps !== null && job.status?.per_stream_fps !== undefined
                            ? job.status.per_stream_fps.toFixed(2)
                            : "-"}
                        </TableCell>
                        <TableCell>
                          {job.status?.total_streams ?? "-"}
                        </TableCell>
                      </>
                    ) : (
                      <>
                        <TableCell>
                          {job.status?.total_streams ?? "-"}
                        </TableCell>
                        <TableCell>
                          {job.status?.per_stream_fps !== null && job.status?.per_stream_fps !== undefined
                            ? job.status.per_stream_fps.toFixed(2)
                            : "-"}
                        </TableCell>
                        <TableCell>
                          {fpsFloor}
                        </TableCell>
                      </>
                    )}
                    <TableCell className="max-w-[200px]">
                      {job.error ? (
                        <span className="text-xs text-red-700 dark:text-red-300 truncate block">
                          {job.error}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">-</span>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
};
