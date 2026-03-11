import { apiSlice as api } from "./apiSlice";
export const addTagTypes = [
  "health",
  "convert",
  "devices",
  "jobs",
  "models",
  "pipelines",
  "tests",
  "videos",
  "cameras",
] as const;
const injectedRtkApi = api
  .enhanceEndpoints({
    addTagTypes,
  })
  .injectEndpoints({
    endpoints: (build) => ({
      getHealth: build.query<GetHealthApiResponse, GetHealthApiArg>({
        query: () => ({ url: `/health` }),
        providesTags: ["health"],
      }),
      getStatus: build.query<GetStatusApiResponse, GetStatusApiArg>({
        query: () => ({ url: `/status` }),
        providesTags: ["health"],
      }),
      toGraph: build.mutation<ToGraphApiResponse, ToGraphApiArg>({
        query: (queryArg) => ({
          url: `/convert/to-graph`,
          method: "POST",
          body: queryArg.pipelineDescription,
        }),
        invalidatesTags: ["convert"],
      }),
      toDescription: build.mutation<
        ToDescriptionApiResponse,
        ToDescriptionApiArg
      >({
        query: (queryArg) => ({
          url: `/convert/to-description`,
          method: "POST",
          body: queryArg.pipelineGraph,
        }),
        invalidatesTags: ["convert"],
      }),
      getDevices: build.query<GetDevicesApiResponse, GetDevicesApiArg>({
        query: () => ({ url: `/devices` }),
        providesTags: ["devices"],
      }),
      getPerformanceStatuses: build.query<
        GetPerformanceStatusesApiResponse,
        GetPerformanceStatusesApiArg
      >({
        query: () => ({ url: `/jobs/tests/performance/status` }),
        providesTags: ["jobs"],
      }),
      getPerformanceJobStatus: build.query<
        GetPerformanceJobStatusApiResponse,
        GetPerformanceJobStatusApiArg
      >({
        query: (queryArg) => ({
          url: `/jobs/tests/performance/${queryArg.jobId}/status`,
        }),
        providesTags: ["jobs"],
      }),
      getPerformanceJobSummary: build.query<
        GetPerformanceJobSummaryApiResponse,
        GetPerformanceJobSummaryApiArg
      >({
        query: (queryArg) => ({
          url: `/jobs/tests/performance/${queryArg.jobId}`,
        }),
        providesTags: ["jobs"],
      }),
      stopPerformanceTestJob: build.mutation<
        StopPerformanceTestJobApiResponse,
        StopPerformanceTestJobApiArg
      >({
        query: (queryArg) => ({
          url: `/jobs/tests/performance/${queryArg.jobId}`,
          method: "DELETE",
        }),
        invalidatesTags: ["jobs"],
      }),
      getDensityStatuses: build.query<
        GetDensityStatusesApiResponse,
        GetDensityStatusesApiArg
      >({
        query: () => ({ url: `/jobs/tests/density/status` }),
        providesTags: ["jobs"],
      }),
      getDensityJobStatus: build.query<
        GetDensityJobStatusApiResponse,
        GetDensityJobStatusApiArg
      >({
        query: (queryArg) => ({
          url: `/jobs/tests/density/${queryArg.jobId}/status`,
        }),
        providesTags: ["jobs"],
      }),
      getDensityJobSummary: build.query<
        GetDensityJobSummaryApiResponse,
        GetDensityJobSummaryApiArg
      >({
        query: (queryArg) => ({ url: `/jobs/tests/density/${queryArg.jobId}` }),
        providesTags: ["jobs"],
      }),
      stopDensityTestJob: build.mutation<
        StopDensityTestJobApiResponse,
        StopDensityTestJobApiArg
      >({
        query: (queryArg) => ({
          url: `/jobs/tests/density/${queryArg.jobId}`,
          method: "DELETE",
        }),
        invalidatesTags: ["jobs"],
      }),
      getOptimizationStatuses: build.query<
        GetOptimizationStatusesApiResponse,
        GetOptimizationStatusesApiArg
      >({
        query: () => ({ url: `/jobs/optimization/status` }),
        providesTags: ["jobs"],
      }),
      getOptimizationJobSummary: build.query<
        GetOptimizationJobSummaryApiResponse,
        GetOptimizationJobSummaryApiArg
      >({
        query: (queryArg) => ({ url: `/jobs/optimization/${queryArg.jobId}` }),
        providesTags: ["jobs"],
      }),
      getOptimizationJobStatus: build.query<
        GetOptimizationJobStatusApiResponse,
        GetOptimizationJobStatusApiArg
      >({
        query: (queryArg) => ({
          url: `/jobs/optimization/${queryArg.jobId}/status`,
        }),
        providesTags: ["jobs"],
      }),
      getValidationStatuses: build.query<
        GetValidationStatusesApiResponse,
        GetValidationStatusesApiArg
      >({
        query: () => ({ url: `/jobs/validation/status` }),
        providesTags: ["jobs"],
      }),
      getValidationJobSummary: build.query<
        GetValidationJobSummaryApiResponse,
        GetValidationJobSummaryApiArg
      >({
        query: (queryArg) => ({ url: `/jobs/validation/${queryArg.jobId}` }),
        providesTags: ["jobs"],
      }),
      getValidationJobStatus: build.query<
        GetValidationJobStatusApiResponse,
        GetValidationJobStatusApiArg
      >({
        query: (queryArg) => ({
          url: `/jobs/validation/${queryArg.jobId}/status`,
        }),
        providesTags: ["jobs"],
      }),
      getModels: build.query<GetModelsApiResponse, GetModelsApiArg>({
        query: () => ({ url: `/models` }),
        providesTags: ["models"],
      }),
      getPipelines: build.query<GetPipelinesApiResponse, GetPipelinesApiArg>({
        query: () => ({ url: `/pipelines` }),
        providesTags: ["pipelines"],
      }),
      createPipeline: build.mutation<
        CreatePipelineApiResponse,
        CreatePipelineApiArg
      >({
        query: (queryArg) => ({
          url: `/pipelines`,
          method: "POST",
          body: queryArg.pipelineDefinition,
        }),
        invalidatesTags: ["pipelines"],
      }),
      validatePipeline: build.mutation<
        ValidatePipelineApiResponse,
        ValidatePipelineApiArg
      >({
        query: (queryArg) => ({
          url: `/pipelines/validate`,
          method: "POST",
          body: queryArg.pipelineValidationInput,
        }),
        invalidatesTags: ["pipelines"],
      }),
      getPipeline: build.query<GetPipelineApiResponse, GetPipelineApiArg>({
        query: (queryArg) => ({ url: `/pipelines/${queryArg.pipelineId}` }),
        providesTags: ["pipelines"],
      }),
      updatePipeline: build.mutation<
        UpdatePipelineApiResponse,
        UpdatePipelineApiArg
      >({
        query: (queryArg) => ({
          url: `/pipelines/${queryArg.pipelineId}`,
          method: "PATCH",
          body: queryArg.pipelineUpdate,
        }),
        invalidatesTags: ["pipelines"],
      }),
      deletePipeline: build.mutation<
        DeletePipelineApiResponse,
        DeletePipelineApiArg
      >({
        query: (queryArg) => ({
          url: `/pipelines/${queryArg.pipelineId}`,
          method: "DELETE",
        }),
        invalidatesTags: ["pipelines"],
      }),
      optimizeVariant: build.mutation<
        OptimizeVariantApiResponse,
        OptimizeVariantApiArg
      >({
        query: (queryArg) => ({
          url: `/pipelines/${queryArg.pipelineId}/variants/${queryArg.variantId}/optimize`,
          method: "POST",
          body: queryArg.pipelineRequestOptimize,
        }),
        invalidatesTags: ["pipelines"],
      }),
      createVariant: build.mutation<
        CreateVariantApiResponse,
        CreateVariantApiArg
      >({
        query: (queryArg) => ({
          url: `/pipelines/${queryArg.pipelineId}/variants`,
          method: "POST",
          body: queryArg.variantCreate,
        }),
        invalidatesTags: ["pipelines"],
      }),
      deleteVariant: build.mutation<
        DeleteVariantApiResponse,
        DeleteVariantApiArg
      >({
        query: (queryArg) => ({
          url: `/pipelines/${queryArg.pipelineId}/variants/${queryArg.variantId}`,
          method: "DELETE",
        }),
        invalidatesTags: ["pipelines"],
      }),
      updateVariant: build.mutation<
        UpdateVariantApiResponse,
        UpdateVariantApiArg
      >({
        query: (queryArg) => ({
          url: `/pipelines/${queryArg.pipelineId}/variants/${queryArg.variantId}`,
          method: "PATCH",
          body: queryArg.variantUpdate,
        }),
        invalidatesTags: ["pipelines"],
      }),
      convertAdvancedToSimple: build.mutation<
        ConvertAdvancedToSimpleApiResponse,
        ConvertAdvancedToSimpleApiArg
      >({
        query: (queryArg) => ({
          url: `/pipelines/${queryArg.pipelineId}/variants/${queryArg.variantId}/convert-to-simple`,
          method: "POST",
          body: queryArg.pipelineGraph,
        }),
        invalidatesTags: ["pipelines"],
      }),
      convertSimpleToAdvanced: build.mutation<
        ConvertSimpleToAdvancedApiResponse,
        ConvertSimpleToAdvancedApiArg
      >({
        query: (queryArg) => ({
          url: `/pipelines/${queryArg.pipelineId}/variants/${queryArg.variantId}/convert-to-advanced`,
          method: "POST",
          body: queryArg.pipelineGraph,
        }),
        invalidatesTags: ["pipelines"],
      }),
      runPerformanceTest: build.mutation<
        RunPerformanceTestApiResponse,
        RunPerformanceTestApiArg
      >({
        query: (queryArg) => ({
          url: `/tests/performance`,
          method: "POST",
          body: queryArg.performanceTestSpec,
        }),
        invalidatesTags: ["tests"],
      }),
      runDensityTest: build.mutation<
        RunDensityTestApiResponse,
        RunDensityTestApiArg
      >({
        query: (queryArg) => ({
          url: `/tests/density`,
          method: "POST",
          body: queryArg.densityTestSpec,
        }),
        invalidatesTags: ["tests"],
      }),
      getVideos: build.query<GetVideosApiResponse, GetVideosApiArg>({
        query: () => ({ url: `/videos` }),
        providesTags: ["videos"],
      }),
      getCameras: build.query<GetCamerasApiResponse, GetCamerasApiArg>({
        query: () => ({ url: `/cameras` }),
        providesTags: ["cameras"],
      }),
      getCamera: build.query<GetCameraApiResponse, GetCameraApiArg>({
        query: (queryArg) => ({ url: `/cameras/${queryArg.cameraId}` }),
        providesTags: ["cameras"],
      }),
      loadCameraProfiles: build.mutation<
        LoadCameraProfilesApiResponse,
        LoadCameraProfilesApiArg
      >({
        query: (queryArg) => ({
          url: `/cameras/${queryArg.cameraId}/profiles`,
          method: "POST",
          body: queryArg.cameraProfilesRequest,
        }),
        invalidatesTags: ["cameras"],
      }),
    }),
    overrideExisting: false,
  });
export { injectedRtkApi as api };
export type GetHealthApiResponse =
  /** status 200 Successful Response */ HealthResponse;
export type GetHealthApiArg = void;
export type GetStatusApiResponse =
  /** status 200 Successful Response */ StatusResponse;
export type GetStatusApiArg = void;
export type ToGraphApiResponse =
  /** status 200 Conversion successful */ PipelineGraphResponse;
export type ToGraphApiArg = {
  pipelineDescription: PipelineDescription;
};
export type ToDescriptionApiResponse =
  /** status 200 Conversion successful */ PipelineDescription;
export type ToDescriptionApiArg = {
  pipelineGraph: PipelineGraph;
};
export type GetDevicesApiResponse =
  /** status 200 List of devices successfully retrieved. */ Device[];
export type GetDevicesApiArg = void;
export type GetPerformanceStatusesApiResponse =
  /** status 200 Successful Response */ PerformanceJobStatus[];
export type GetPerformanceStatusesApiArg = void;
export type GetPerformanceJobStatusApiResponse =
  /** status 200 Successful Response */ PerformanceJobStatus;
export type GetPerformanceJobStatusApiArg = {
  jobId: string;
};
export type GetPerformanceJobSummaryApiResponse =
  /** status 200 Successful Response */ PerformanceJobSummary;
export type GetPerformanceJobSummaryApiArg = {
  jobId: string;
};
export type StopPerformanceTestJobApiResponse =
  /** status 200 Successful Response */ MessageResponse;
export type StopPerformanceTestJobApiArg = {
  jobId: string;
};
export type GetDensityStatusesApiResponse =
  /** status 200 Successful Response */ DensityJobStatus[];
export type GetDensityStatusesApiArg = void;
export type GetDensityJobStatusApiResponse =
  /** status 200 Successful Response */ DensityJobStatus;
export type GetDensityJobStatusApiArg = {
  jobId: string;
};
export type GetDensityJobSummaryApiResponse =
  /** status 200 Successful Response */ DensityJobSummary;
export type GetDensityJobSummaryApiArg = {
  jobId: string;
};
export type StopDensityTestJobApiResponse =
  /** status 200 Successful Response */ MessageResponse;
export type StopDensityTestJobApiArg = {
  jobId: string;
};
export type GetOptimizationStatusesApiResponse =
  /** status 200 Successful Response */ OptimizationJobStatus[];
export type GetOptimizationStatusesApiArg = void;
export type GetOptimizationJobSummaryApiResponse =
  /** status 200 Successful Response */ OptimizationJobSummary;
export type GetOptimizationJobSummaryApiArg = {
  jobId: string;
};
export type GetOptimizationJobStatusApiResponse =
  /** status 200 Successful Response */ OptimizationJobStatus;
export type GetOptimizationJobStatusApiArg = {
  jobId: string;
};
export type GetValidationStatusesApiResponse =
  /** status 200 Successful Response */ ValidationJobStatus[];
export type GetValidationStatusesApiArg = void;
export type GetValidationJobSummaryApiResponse =
  /** status 200 Successful Response */ ValidationJobSummary;
export type GetValidationJobSummaryApiArg = {
  jobId: string;
};
export type GetValidationJobStatusApiResponse =
  /** status 200 Successful Response */ ValidationJobStatus;
export type GetValidationJobStatusApiArg = {
  jobId: string;
};
export type GetModelsApiResponse =
  /** status 200 Successful Response */ Model[];
export type GetModelsApiArg = void;
export type GetPipelinesApiResponse =
  /** status 200 Successful Response */ Pipeline[];
export type GetPipelinesApiArg = void;
export type CreatePipelineApiResponse =
  /** status 201 Pipeline created */ PipelineCreationResponse;
export type CreatePipelineApiArg = {
  pipelineDefinition: PipelineDefinition;
};
export type ValidatePipelineApiResponse =
  /** status 202 Pipeline validation started */ ValidationJobResponse;
export type ValidatePipelineApiArg = {
  pipelineValidationInput: PipelineValidation2;
};
export type GetPipelineApiResponse =
  /** status 200 Successful Response */ Pipeline;
export type GetPipelineApiArg = {
  pipelineId: string;
};
export type UpdatePipelineApiResponse =
  /** status 200 Pipeline updated */ Pipeline;
export type UpdatePipelineApiArg = {
  pipelineId: string;
  pipelineUpdate: PipelineUpdate;
};
export type DeletePipelineApiResponse =
  /** status 200 Pipeline deleted */ MessageResponse;
export type DeletePipelineApiArg = {
  pipelineId: string;
};
export type OptimizeVariantApiResponse =
  /** status 202 Variant optimization started */ OptimizationJobResponse;
export type OptimizeVariantApiArg = {
  pipelineId: string;
  variantId: string;
  pipelineRequestOptimize: PipelineRequestOptimize;
};
export type CreateVariantApiResponse =
  /** status 201 Variant created */ Variant;
export type CreateVariantApiArg = {
  pipelineId: string;
  variantCreate: VariantCreate;
};
export type DeleteVariantApiResponse =
  /** status 200 Variant deleted */ MessageResponse;
export type DeleteVariantApiArg = {
  pipelineId: string;
  variantId: string;
};
export type UpdateVariantApiResponse =
  /** status 200 Variant updated */ Variant;
export type UpdateVariantApiArg = {
  pipelineId: string;
  variantId: string;
  variantUpdate: VariantUpdate;
};
export type ConvertAdvancedToSimpleApiResponse =
  /** status 200 Converted simple graph */ PipelineGraph;
export type ConvertAdvancedToSimpleApiArg = {
  pipelineId: string;
  variantId: string;
  pipelineGraph: PipelineGraph;
};
export type ConvertSimpleToAdvancedApiResponse =
  /** status 200 Converted advanced graph */ PipelineGraph;
export type ConvertSimpleToAdvancedApiArg = {
  pipelineId: string;
  variantId: string;
  pipelineGraph: PipelineGraph;
};
export type RunPerformanceTestApiResponse =
  /** status 202 Performance test job created */ TestJobResponse;
export type RunPerformanceTestApiArg = {
  performanceTestSpec: PerformanceTestSpec;
};
export type RunDensityTestApiResponse =
  /** status 202 Density test job created */ TestJobResponse;
export type RunDensityTestApiArg = {
  densityTestSpec: DensityTestSpec;
};
export type GetVideosApiResponse =
  /** status 200 Successful Response */ Video[];
export type GetVideosApiArg = void;
export type GetCamerasApiResponse =
  /** status 200 List of all cameras successfully retrieved. */ Camera[];
export type GetCamerasApiArg = void;
export type GetCameraApiResponse =
  /** status 200 Camera successfully retrieved. */ Camera;
export type GetCameraApiArg = {
  cameraId: string;
};
export type LoadCameraProfilesApiResponse =
  /** status 200 Camera profiles loaded successfully. */ CameraAuthResponse;
export type LoadCameraProfilesApiArg = {
  cameraId: string;
  cameraProfilesRequest: CameraProfilesRequest;
};
export type HealthResponse = {
  healthy: boolean;
};
export type AppStatus = "starting" | "initializing" | "ready" | "shutdown";
export type StatusResponse = {
  status: AppStatus;
  message: string | null;
  ready: boolean;
};
export type Node = {
  id: string;
  type: string;
  data: {
    [key: string]: string;
  };
};
export type Edge = {
  id: string;
  source: string;
  target: string;
};
export type PipelineGraph = {
  /** List of pipeline nodes. */
  nodes: Node[];
  /** List of directed edges between nodes. */
  edges: Edge[];
};
export type PipelineGraphResponse = {
  /** Advanced graph view with all pipeline elements including technical plumbing. */
  pipeline_graph: PipelineGraph;
  /** Simplified graph view showing only sources, inference nodes, and sinks. */
  pipeline_graph_simple: PipelineGraph;
};
export type MessageResponse = {
  /** Human-readable error or status message. */
  message: string;
};
export type ValidationError = {
  loc: (string | number)[];
  msg: string;
  type: string;
  input?: any;
  ctx?: object;
};
export type HttpValidationError = {
  detail?: ValidationError[];
};
export type PipelineDescription = {
  /** GStreamer pipeline string with elements separated by '!'. */
  pipeline_description: string;
};
export type DeviceType = "DISCRETE" | "INTEGRATED";
export type DeviceFamily = "CPU" | "GPU" | "NPU";
export type Device = {
  device_name: string;
  full_device_name: string;
  device_type: DeviceType;
  device_family: DeviceFamily;
  gpu_id: number | null;
};
export type TestJobState = "RUNNING" | "COMPLETED" | "ERROR" | "ABORTED";
export type PipelineStreamSpec = {
  /** Pipeline identifier - variant path or synthetic graph ID. */
  id: string;
  /** Number of streams allocated to this pipeline. */
  streams: number;
};
export type PerformanceJobStatus = {
  id: string;
  start_time: number;
  elapsed_time: number;
  state: TestJobState;
  total_fps: number | null;
  per_stream_fps: number | null;
  total_streams: number | null;
  streams_per_pipeline: PipelineStreamSpec[] | null;
  video_output_paths: {
    [key: string]: string[];
  } | null;
  error_message: string | null;
  live_stream_urls: {
    [key: string]: string;
  } | null;
};
export type PerformanceJobSummary = {
  id: string;
  request: {
    [key: string]: any;
  };
};
export type DensityJobStatus = {
  id: string;
  start_time: number;
  elapsed_time: number;
  state: TestJobState;
  total_fps: number | null;
  per_stream_fps: number | null;
  total_streams: number | null;
  streams_per_pipeline: PipelineStreamSpec[] | null;
  video_output_paths: {
    [key: string]: string[];
  } | null;
  error_message: string | null;
};
export type DensityJobSummary = {
  id: string;
  request: {
    [key: string]: any;
  };
};
export type OptimizationType = "preprocess" | "optimize";
export type OptimizationJobState =
  | "RUNNING"
  | "COMPLETED"
  | "ERROR"
  | "ABORTED";
export type OptimizationJobStatus = {
  id: string;
  type: OptimizationType | null;
  start_time: number;
  elapsed_time: number;
  state: OptimizationJobState;
  total_fps: number | null;
  original_pipeline_graph: PipelineGraph;
  original_pipeline_graph_simple: PipelineGraph;
  optimized_pipeline_graph: PipelineGraph | null;
  optimized_pipeline_graph_simple: PipelineGraph | null;
  original_pipeline_description: string;
  optimized_pipeline_description: string | null;
  error_message: string | null;
};
export type PipelineRequestOptimize = {
  type: OptimizationType;
  parameters: {
    [key: string]: any;
  } | null;
};
export type OptimizationJobSummary = {
  id: string;
  request: PipelineRequestOptimize;
};
export type ValidationJobState = "RUNNING" | "COMPLETED" | "ERROR" | "ABORTED";
export type ValidationJobStatus = {
  id: string;
  start_time: number;
  elapsed_time: number;
  state: ValidationJobState;
  is_valid: boolean | null;
  error_message: string[] | null;
};
export type PipelineValidation = {
  pipeline_graph: PipelineGraph;
  parameters?: {
    [key: string]: any;
  } | null;
};
export type ValidationJobSummary = {
  id: string;
  request: PipelineValidation;
};
export type ModelCategory = "classification" | "detection";
export type Model = {
  name: string;
  display_name: string;
  category: ModelCategory | null;
  precision: string | null;
};
export type PipelineSource = "PREDEFINED" | "USER_CREATED";
export type Variant = {
  /** Unique variant identifier generated by the backend. */
  id: string;
  /** Variant name identifying the hardware target. */
  name: string;
  /** Whether the variant is read-only. Can only be true for PREDEFINED pipelines. */
  read_only?: boolean;
  /** Advanced graph view with all pipeline elements for this variant. */
  pipeline_graph: PipelineGraph;
  /** Simplified graph view for this variant. */
  pipeline_graph_simple: PipelineGraph;
  /** Creation timestamp as UTC datetime. Set by backend only. */
  created_at: string;
  /** Last modification timestamp as UTC datetime. Set by backend only. */
  modified_at: string;
};
export type Pipeline = {
  id: string;
  name: string;
  description: string;
  source: PipelineSource;
  /** List of tags for categorizing the pipeline. */
  tags?: string[];
  /** List of pipeline variants for different hardware targets. */
  variants: Variant[];
  /** Base64-encoded thumbnail image. Only for PREDEFINED pipelines. Redacted in logs. */
  thumbnail?: string | null;
  /** Creation timestamp as UTC datetime. Set by backend only. */
  created_at: string;
  /** Last modification timestamp as UTC datetime. Set by backend only. */
  modified_at: string;
};
export type PipelineCreationResponse = {
  id: string;
};
export type VariantCreate = {
  /** Variant name identifying the hardware target. */
  name: string;
  /** Advanced graph view with all pipeline elements for this variant. */
  pipeline_graph: PipelineGraph;
  /** Simplified graph view for this variant. */
  pipeline_graph_simple: PipelineGraph;
};
export type PipelineDefinition = {
  /** Non-empty pipeline name. */
  name: string;
  /** Non-empty human-readable text describing what the pipeline does. */
  description: string;
  source?: PipelineSource;
  /** List of tags for categorizing the pipeline. */
  tags?: string[];
  /** List of pipeline variants for different hardware targets. */
  variants: VariantCreate[];
};
export type ValidationJobResponse = {
  /** Identifier of the created validation job. */
  job_id: string;
};
export type PipelineValidation2 = {
  pipeline_graph: PipelineGraph;
  parameters?: {
    [key: string]: any;
  } | null;
};
export type PipelineUpdate = {
  name?: string | null;
  description?: string | null;
  tags?: string[] | null;
};
export type OptimizationJobResponse = {
  /** Identifier of the created optimization job. */
  job_id: string;
};
export type VariantUpdate = {
  /** New variant name. */
  name?: string | null;
  /** New advanced graph (mutually exclusive with pipeline_graph_simple). */
  pipeline_graph?: PipelineGraph | null;
  /** New simplified graph (mutually exclusive with pipeline_graph). */
  pipeline_graph_simple?: PipelineGraph | null;
};
export type TestJobResponse = {
  /** Identifier of the created test job. */
  job_id: string;
};
export type PipelineDescriptionSource = {
  source?: "description";
  /** GStreamer pipeline string with elements separated by '!'. */
  pipeline_description: string;
  /** Optional custom identifier for pipeline description. Must be URL-safe. */
  description_id?: string | null;
};
export type GraphInline = {
  source?: "graph";
  /** Optional custom identifier for inline graph. Must be URL-safe. */
  graph_id?: string | null;
  /** Inline pipeline graph to use for the test. */
  pipeline_graph: PipelineGraph;
};
export type VariantReference = {
  source?: "variant";
  /** ID of the pipeline containing the variant. */
  pipeline_id: string;
  /** ID of the variant within the pipeline. */
  variant_id: string;
};
export type PipelinePerformanceSpec = {
  /** Graph source - either a reference to existing variant or inline graph. */
  pipeline:
    | ({
        source: "description";
      } & PipelineDescriptionSource)
    | ({
        source: "graph";
      } & GraphInline)
    | ({
        source: "variant";
      } & VariantReference);
  /** Number of parallel streams for this pipeline. */
  streams?: number;
};
export type OutputMode = "disabled" | "file" | "live_stream";
export type ExecutionConfig = {
  /** Mode for pipeline output generation. */
  output_mode?: OutputMode;
  /** Maximum runtime in seconds (0 = run until EOS, >0 = time limit with looping for live_stream/disabled). */
  max_runtime?: number;
};
export type PerformanceTestSpec = {
  /** List of pipelines with number of streams for each. */
  pipeline_performance_specs: PipelinePerformanceSpec[];
  /** Execution configuration for output and runtime. */
  execution_config?: ExecutionConfig;
};
export type PipelineDensitySpec = {
  /** Graph source - either a reference to existing variant or inline graph. */
  pipeline:
    | ({
        source: "description";
      } & PipelineDescriptionSource)
    | ({
        source: "graph";
      } & GraphInline)
    | ({
        source: "variant";
      } & VariantReference);
  /** Relative share of total streams for this pipeline (percentage). */
  stream_rate?: number;
};
export type DensityTestSpec = {
  /** Minimum acceptable FPS per stream. */
  fps_floor: number;
  /** List of pipelines with relative stream_rate percentages that must sum to 100. */
  pipeline_density_specs: PipelineDensitySpec[];
  /** Execution configuration for output and runtime. */
  execution_config?: ExecutionConfig;
};
export type Video = {
  filename: string;
  width: number;
  height: number;
  fps: number;
  frame_count: number;
  codec: string;
  duration: number;
};
export type CameraType = "USB" | "NETWORK";
export type UsbCameraDetails = {
  device_path: string;
  resolution: string | null;
};
export type CameraProfileInfo = {
  name: string;
  rtsp_url?: string | null;
  resolution?: string | null;
  encoding?: string | null;
  framerate?: number | null;
  bitrate?: number | null;
};
export type NetworkCameraDetails = {
  ip: string;
  port: number;
  profiles: CameraProfileInfo[];
};
export type Camera = {
  device_id: string;
  device_name: string;
  device_type: CameraType;
  details: UsbCameraDetails | NetworkCameraDetails;
};
export type CameraAuthResponse = {
  /** Camera object with populated ONVIF profiles after successful authentication. */
  camera: Camera;
};
export type CameraProfilesRequest = {
  username: string;
  password: string;
};
export const {
  useGetHealthQuery,
  useLazyGetHealthQuery,
  useGetStatusQuery,
  useLazyGetStatusQuery,
  useToGraphMutation,
  useToDescriptionMutation,
  useGetDevicesQuery,
  useLazyGetDevicesQuery,
  useGetPerformanceStatusesQuery,
  useLazyGetPerformanceStatusesQuery,
  useGetPerformanceJobStatusQuery,
  useLazyGetPerformanceJobStatusQuery,
  useGetPerformanceJobSummaryQuery,
  useLazyGetPerformanceJobSummaryQuery,
  useStopPerformanceTestJobMutation,
  useGetDensityStatusesQuery,
  useLazyGetDensityStatusesQuery,
  useGetDensityJobStatusQuery,
  useLazyGetDensityJobStatusQuery,
  useGetDensityJobSummaryQuery,
  useLazyGetDensityJobSummaryQuery,
  useStopDensityTestJobMutation,
  useGetOptimizationStatusesQuery,
  useLazyGetOptimizationStatusesQuery,
  useGetOptimizationJobSummaryQuery,
  useLazyGetOptimizationJobSummaryQuery,
  useGetOptimizationJobStatusQuery,
  useLazyGetOptimizationJobStatusQuery,
  useGetValidationStatusesQuery,
  useLazyGetValidationStatusesQuery,
  useGetValidationJobSummaryQuery,
  useLazyGetValidationJobSummaryQuery,
  useGetValidationJobStatusQuery,
  useLazyGetValidationJobStatusQuery,
  useGetModelsQuery,
  useLazyGetModelsQuery,
  useGetPipelinesQuery,
  useLazyGetPipelinesQuery,
  useCreatePipelineMutation,
  useValidatePipelineMutation,
  useGetPipelineQuery,
  useLazyGetPipelineQuery,
  useUpdatePipelineMutation,
  useDeletePipelineMutation,
  useOptimizeVariantMutation,
  useCreateVariantMutation,
  useDeleteVariantMutation,
  useUpdateVariantMutation,
  useConvertAdvancedToSimpleMutation,
  useConvertSimpleToAdvancedMutation,
  useRunPerformanceTestMutation,
  useRunDensityTestMutation,
  useGetVideosQuery,
  useLazyGetVideosQuery,
  useGetCamerasQuery,
  useLazyGetCamerasQuery,
  useGetCameraQuery,
  useLazyGetCameraQuery,
  useLoadCameraProfilesMutation,
} = injectedRtkApi;
