import { apiSlice as api } from "./apiSlice";
export const addTagTypes = [
  "pipelines",
  "devices",
  "models",
  "metrics",
] as const;
const injectedRtkApi = api
  .enhanceEndpoints({
    addTagTypes,
  })
  .injectEndpoints({
    endpoints: (build) => ({
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
      getPipelineStatuses: build.query<
        GetPipelineStatusesApiResponse,
        GetPipelineStatusesApiArg
      >({
        query: () => ({ url: `/pipelines/status` }),
        providesTags: ["pipelines"],
      }),
      getPipelineInstanceSummary: build.query<
        GetPipelineInstanceSummaryApiResponse,
        GetPipelineInstanceSummaryApiArg
      >({
        query: (queryArg) => ({ url: `/pipelines/${queryArg.instanceId}` }),
        providesTags: ["pipelines"],
      }),
      stopPipelineInstance: build.mutation<
        StopPipelineInstanceApiResponse,
        StopPipelineInstanceApiArg
      >({
        query: (queryArg) => ({
          url: `/pipelines/${queryArg.instanceId}`,
          method: "DELETE",
        }),
        invalidatesTags: ["pipelines"],
      }),
      getPipelineInstanceStatus: build.query<
        GetPipelineInstanceStatusApiResponse,
        GetPipelineInstanceStatusApiArg
      >({
        query: (queryArg) => ({
          url: `/pipelines/${queryArg.instanceId}/status`,
        }),
        providesTags: ["pipelines"],
      }),
      getPipeline: build.query<GetPipelineApiResponse, GetPipelineApiArg>({
        query: (queryArg) => ({
          url: `/pipelines/${queryArg.name}/${queryArg.version}`,
        }),
        providesTags: ["pipelines"],
      }),
      runPipeline: build.mutation<RunPipelineApiResponse, RunPipelineApiArg>({
        query: (queryArg) => ({
          url: `/pipelines/${queryArg.name}/${queryArg.version}`,
          method: "POST",
          body: queryArg.pipelineRequestRunInput,
        }),
        invalidatesTags: ["pipelines"],
      }),
      deletePipeline: build.mutation<
        DeletePipelineApiResponse,
        DeletePipelineApiArg
      >({
        query: (queryArg) => ({
          url: `/pipelines/${queryArg.name}/${queryArg.version}`,
          method: "DELETE",
        }),
        invalidatesTags: ["pipelines"],
      }),
      benchmarkPipeline: build.mutation<
        BenchmarkPipelineApiResponse,
        BenchmarkPipelineApiArg
      >({
        query: (queryArg) => ({
          url: `/pipelines/${queryArg.name}/${queryArg.version}/benchmark`,
          method: "POST",
          body: queryArg.pipelineRequestBenchmarkInput,
        }),
        invalidatesTags: ["pipelines"],
      }),
      optimizePipeline: build.mutation<
        OptimizePipelineApiResponse,
        OptimizePipelineApiArg
      >({
        query: (queryArg) => ({
          url: `/pipelines/${queryArg.name}/${queryArg.version}/optimize`,
          method: "POST",
          body: queryArg.pipelineRequestOptimize,
        }),
        invalidatesTags: ["pipelines"],
      }),
      getDevices: build.query<GetDevicesApiResponse, GetDevicesApiArg>({
        query: () => ({ url: `/devices` }),
        providesTags: ["devices"],
      }),
      getModels: build.query<GetModelsApiResponse, GetModelsApiArg>({
        query: () => ({ url: `/models` }),
        providesTags: ["models"],
      }),
      getMetrics: build.query<GetMetricsApiResponse, GetMetricsApiArg>({
        query: () => ({ url: `/metrics` }),
        providesTags: ["metrics"],
      }),
    }),
    overrideExisting: false,
  });
export { injectedRtkApi as api };
export type GetPipelinesApiResponse =
  /** status 200 Successful Response */ Pipeline[];
export type GetPipelinesApiArg = void;
export type CreatePipelineApiResponse = /** status 201 Pipeline created */ any;
export type CreatePipelineApiArg = {
  pipelineDefinition: PipelineDefinition;
};
export type ValidatePipelineApiResponse =
  /** status 200 Pipeline is valid */ any;
export type ValidatePipelineApiArg = {
  pipelineValidation: PipelineValidation;
};
export type GetPipelineStatusesApiResponse =
  /** status 200 Successful Response */ PipelineInstanceStatus[];
export type GetPipelineStatusesApiArg = void;
export type GetPipelineInstanceSummaryApiResponse =
  /** status 200 Successful Response */ PipelineInstanceSummary;
export type GetPipelineInstanceSummaryApiArg = {
  instanceId: string;
};
export type StopPipelineInstanceApiResponse =
  /** status 200 Successful Response */ PipelineInstanceStatus[];
export type StopPipelineInstanceApiArg = {
  instanceId: string;
};
export type GetPipelineInstanceStatusApiResponse =
  /** status 200 Successful Response */ PipelineInstanceStatus;
export type GetPipelineInstanceStatusApiArg = {
  instanceId: string;
};
export type GetPipelineApiResponse =
  /** status 200 Successful Response */ Pipeline;
export type GetPipelineApiArg = {
  name: string;
  version: string;
};
export type RunPipelineApiResponse = /** status 200 Successful Response */
  | any
  | /** status 202 Pipeline execution started */ Blob;
export type RunPipelineApiArg = {
  name: string;
  version: string;
  pipelineRequestRunInput: PipelineRequestRun2;
};
export type DeletePipelineApiResponse = /** status 200 Pipeline deleted */ any;
export type DeletePipelineApiArg = {
  name: string;
  version: string;
};
export type BenchmarkPipelineApiResponse =
  /** status 200 Successful Response */ any;
export type BenchmarkPipelineApiArg = {
  name: string;
  version: string;
  pipelineRequestBenchmarkInput: PipelineRequestBenchmark2;
};
export type OptimizePipelineApiResponse =
  /** status 200 Successful Response */ any;
export type OptimizePipelineApiArg = {
  name: string;
  version: string;
  pipelineRequestOptimize: PipelineRequestOptimize;
};
export type GetDevicesApiResponse =
  /** status 200 Successful Response */ Device[];
export type GetDevicesApiArg = void;
export type GetModelsApiResponse =
  /** status 200 Successful Response */ Model[];
export type GetModelsApiArg = void;
export type GetMetricsApiResponse =
  /** status 200 Successful Response */ MetricSample[];
export type GetMetricsApiArg = void;
export type PipelineType = "GStreamer" | "FFmpeg";
export type PipelineParameters = {
  default: {
    [key: string]: any;
  } | null;
};
export type Pipeline = {
  name: string;
  version: string;
  description: string;
  type: PipelineType;
  launch_config: {
    [key: string]: any;
  };
  parameters: PipelineParameters | null;
};
export type ValidationError = {
  loc: (string | number)[];
  msg: string;
  type: string;
};
export type HttpValidationError = {
  detail?: ValidationError[];
};
export type PipelineDefinition = {
  name: string;
  version: string;
  description: string;
  type: PipelineType;
  launch_string: string;
  parameters: PipelineParameters | null;
};
export type PipelineValidation = {
  type: PipelineType;
  launch_string: string;
  parameters: PipelineParameters | null;
};
export type PipelineInstanceState =
  | "RUNNING"
  | "COMPLETED"
  | "ERROR"
  | "ABORTED";
export type PipelineInstanceStatus = {
  id: string;
  start_time: number;
  elapsed_time: number;
  state: PipelineInstanceState;
  total_fps: number | null;
  per_stream_fps: number | null;
  ai_streams: number | null;
  non_ai_streams: number | null;
};
export type SourceType = "uri" | "gst";
export type Source = {
  type: SourceType;
  uri: string | null;
};
export type PipelineParametersRun = {
  inferencing_channels?: number;
  recording_channels?: number;
  launch_config: string;
};
export type PipelineRequestRun = {
  async_?: boolean | null;
  source: Source;
  parameters: PipelineParametersRun;
  tags: {
    [key: string]: string;
  } | null;
};
export type PipelineParametersBenchmark = {
  fps_floor?: number;
  ai_stream_rate?: number;
  launch_config: string;
};
export type PipelineRequestBenchmark = {
  async_?: boolean | null;
  source: Source;
  parameters: PipelineParametersBenchmark;
  tags: {
    [key: string]: string;
  } | null;
};
export type PipelineInstanceSummary = {
  id: string;
  request: PipelineRequestRun | PipelineRequestBenchmark;
  type: string;
};
export type PipelineRequestRun2 = {
  async_?: boolean | null;
  source: Source;
  parameters: PipelineParametersRun;
  tags: {
    [key: string]: string;
  } | null;
};
export type PipelineRequestBenchmark2 = {
  async_?: boolean | null;
  source: Source;
  parameters: PipelineParametersBenchmark;
  tags: {
    [key: string]: string;
  } | null;
};
export type PipelineRequestOptimize = {
  async_?: boolean | null;
  source: Source;
  parameters: {
    [key: string]: any;
  } | null;
  tags: {
    [key: string]: string;
  } | null;
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
export type ModelCategory = "classification" | "detection";
export type Model = {
  name: string;
  display_name: string;
  category: ModelCategory;
  precision: string | null;
};
export type MetricSample = {
  name: string;
  description: string;
  timestamp: number;
  value: number;
};
export const {
  useGetPipelinesQuery,
  useLazyGetPipelinesQuery,
  useCreatePipelineMutation,
  useValidatePipelineMutation,
  useGetPipelineStatusesQuery,
  useLazyGetPipelineStatusesQuery,
  useGetPipelineInstanceSummaryQuery,
  useLazyGetPipelineInstanceSummaryQuery,
  useStopPipelineInstanceMutation,
  useGetPipelineInstanceStatusQuery,
  useLazyGetPipelineInstanceStatusQuery,
  useGetPipelineQuery,
  useLazyGetPipelineQuery,
  useRunPipelineMutation,
  useDeletePipelineMutation,
  useBenchmarkPipelineMutation,
  useOptimizePipelineMutation,
  useGetDevicesQuery,
  useLazyGetDevicesQuery,
  useGetModelsQuery,
  useLazyGetModelsQuery,
  useGetMetricsQuery,
  useLazyGetMetricsQuery,
} = injectedRtkApi;
