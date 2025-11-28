import { apiSlice as api } from "./apiSlice";
export const addTagTypes = [
  "convert",
  "devices",
  "jobs",
  "models",
  "pipelines",
  "tests",
  "videos",
] as const;
const injectedRtkApi = api
  .enhanceEndpoints({
    addTagTypes,
  })
  .injectEndpoints({
    endpoints: (build) => ({
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
          body: queryArg.pipelineValidation,
        }),
        invalidatesTags: ["pipelines"],
      }),
      getPipeline: build.query<GetPipelineApiResponse, GetPipelineApiArg>({
        query: (queryArg) => ({ url: `/pipelines/${queryArg.pipelineId}` }),
        providesTags: ["pipelines"],
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
      optimizePipeline: build.mutation<
        OptimizePipelineApiResponse,
        OptimizePipelineApiArg
      >({
        query: (queryArg) => ({
          url: `/pipelines/${queryArg.pipelineId}/optimize`,
          method: "POST",
          body: queryArg.pipelineRequestOptimize,
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
    }),
    overrideExisting: false,
  });
export { injectedRtkApi as api };
export type ToGraphApiResponse =
  /** status 200 Conversion successful */ PipelineGraph;
export type ToGraphApiArg = {
  pipelineDescription: PipelineDescription;
};
export type ToDescriptionApiResponse =
  /** status 200 Conversion successful */ PipelineDescription;
export type ToDescriptionApiArg = {
  pipelineGraph: PipelineGraph;
};
export type GetDevicesApiResponse =
  /** status 200 Successful Response */ Device[];
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
export type GetModelsApiResponse =
  /** status 200 Successful Response */ Model[];
export type GetModelsApiArg = void;
export type GetPipelinesApiResponse =
  /** status 200 Successful Response */ Pipeline[];
export type GetPipelinesApiArg = void;
export type CreatePipelineApiResponse =
  /** status 201 Pipeline created */ MessageResponse;
export type CreatePipelineApiArg = {
  pipelineDefinition: PipelineDefinition;
};
export type ValidatePipelineApiResponse =
  /** status 200 Pipeline is valid */ MessageResponse;
export type ValidatePipelineApiArg = {
  pipelineValidation: PipelineValidation;
};
export type GetPipelineApiResponse =
  /** status 200 Successful Response */ Pipeline;
export type GetPipelineApiArg = {
  pipelineId: string;
};
export type DeletePipelineApiResponse =
  /** status 200 Pipeline deleted */ MessageResponse;
export type DeletePipelineApiArg = {
  pipelineId: string;
};
export type OptimizePipelineApiResponse =
  /** status 200 Successful Response */
  any | /** status 202 Pipeline optimization started */ OptimizationJobResponse;
export type OptimizePipelineApiArg = {
  pipelineId: string;
  pipelineRequestOptimize: PipelineRequestOptimize;
};
export type RunPerformanceTestApiResponse =
  /** status 202 Successful Response */ TestJobResponse;
export type RunPerformanceTestApiArg = {
  performanceTestSpec: PerformanceTestSpec;
};
export type RunDensityTestApiResponse =
  /** status 202 Successful Response */ TestJobResponse;
export type RunDensityTestApiArg = {
  densityTestSpec: DensityTestSpec;
};
export type GetVideosApiResponse =
  /** status 200 Successful Response */ Video[];
export type GetVideosApiArg = void;
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
  nodes: Node[];
  edges: Edge[];
};
export type MessageResponse = {
  message: string;
};
export type ValidationError = {
  loc: (string | number)[];
  msg: string;
  type: string;
};
export type HttpValidationError = {
  detail?: ValidationError[];
};
export type PipelineDescription = {
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
export type PipelinePerformanceSpec = {
  id: string;
  streams?: number;
};
export type PerformanceJobStatus = {
  id: string;
  start_time: number;
  elapsed_time: number;
  state: TestJobState;
  total_fps: number | null;
  per_stream_fps: number | null;
  total_streams: number | null;
  streams_per_pipeline: PipelinePerformanceSpec[] | null;
  error_message: string | null;
};
export type PerformanceTestSpec = {
  pipeline_performance_specs: PipelinePerformanceSpec[];
};
export type PerformanceJobSummary = {
  id: string;
  request: PerformanceTestSpec;
};
export type DensityJobStatus = {
  id: string;
  start_time: number;
  elapsed_time: number;
  state: TestJobState;
  total_fps: number | null;
  per_stream_fps: number | null;
  total_streams: number | null;
  streams_per_pipeline: PipelinePerformanceSpec[] | null;
  error_message: string | null;
};
export type PipelineDensitySpec = {
  id: string;
  stream_rate?: number;
};
export type DensityTestSpec = {
  fps_floor: number;
  pipeline_density_specs: PipelineDensitySpec[];
};
export type DensityJobSummary = {
  id: string;
  request: DensityTestSpec;
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
  optimized_pipeline_graph: PipelineGraph | null;
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
export type ModelCategory = "classification" | "detection";
export type Model = {
  name: string;
  display_name: string;
  category: ModelCategory | null;
  precision: string | null;
};
export type PipelineSource = "PREDEFINED" | "USER_CREATED";
export type PipelineType = "GStreamer" | "FFmpeg";
export type PipelineParameters = {
  default: {
    [key: string]: any;
  } | null;
};
export type Pipeline = {
  id: string;
  name: string;
  version: number;
  description: string;
  source: PipelineSource;
  type: PipelineType;
  pipeline_graph: PipelineGraph;
  parameters: PipelineParameters | null;
};
export type PipelineDefinition = {
  name: string;
  version?: number;
  description: string;
  source?: PipelineSource;
  type: PipelineType;
  pipeline_description: string;
  parameters: PipelineParameters | null;
};
export type PipelineValidation = {
  type: PipelineType;
  pipeline_description: string;
  parameters: PipelineParameters | null;
};
export type OptimizationJobResponse = {
  job_id: string;
};
export type TestJobResponse = {
  job_id: string;
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
export const {
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
  useGetModelsQuery,
  useLazyGetModelsQuery,
  useGetPipelinesQuery,
  useLazyGetPipelinesQuery,
  useCreatePipelineMutation,
  useValidatePipelineMutation,
  useGetPipelineQuery,
  useLazyGetPipelineQuery,
  useDeletePipelineMutation,
  useOptimizePipelineMutation,
  useRunPerformanceTestMutation,
  useRunDensityTestMutation,
  useGetVideosQuery,
  useLazyGetVideosQuery,
} = injectedRtkApi;
