import { apiModelDownloadSlice as api } from "./apiModelDownloadSlice";
export const addTagTypes = ["Health", "Models", "Jobs", "Plugins"] as const;
const injectedRtkApi = api
  .enhanceEndpoints({
    addTagTypes,
  })
  .injectEndpoints({
    endpoints: (build) => ({
      healthCheck: build.query<HealthCheckApiResponse, HealthCheckApiArg>({
        query: () => ({ url: `/health` }),
        providesTags: ["Health"],
      }),
      downloadModels: build.mutation<
        DownloadModelsApiResponse,
        DownloadModelsApiArg
      >({
        query: (queryArg) => ({
          url: `/models/download`,
          method: "POST",
          body: queryArg.modelDownloadRequest,
          params: {
            download_path: queryArg.downloadPath,
          },
        }),
        invalidatesTags: ["Models"],
      }),
      getJobStatus: build.query<GetJobStatusApiResponse, GetJobStatusApiArg>({
        query: (queryArg) => ({ url: `/jobs/${queryArg.jobId}` }),
        providesTags: ["Jobs"],
      }),
      listJobs: build.query<ListJobsApiResponse, ListJobsApiArg>({
        query: () => ({ url: `/jobs` }),
        providesTags: ["Jobs"],
      }),
      getModelJobs: build.query<GetModelJobsApiResponse, GetModelJobsApiArg>({
        query: (queryArg) => ({
          url: `/models/jobs`,
          params: {
            model_name: queryArg.modelName,
          },
        }),
        providesTags: ["Jobs"],
      }),
      getModelResults: build.query<
        GetModelResultsApiResponse,
        GetModelResultsApiArg
      >({
        query: () => ({ url: `/models/results` }),
        providesTags: ["Models"],
      }),
      uploadModel: build.mutation<UploadModelApiResponse, UploadModelApiArg>({
        query: (queryArg) => ({
          url: `/models/upload`,
          method: "POST",
          body: queryArg.body,
        }),
        invalidatesTags: ["Models"],
      }),
      listPlugins: build.query<ListPluginsApiResponse, ListPluginsApiArg>({
        query: () => ({ url: `/plugins` }),
        providesTags: ["Plugins"],
      }),
    }),
    overrideExisting: false,
  });
export { injectedRtkApi as apiModelDownload };
export type HealthCheckApiResponse =
  /** status 200 Service is healthy */ HealthResponse;
export type HealthCheckApiArg = void;
export type DownloadModelsApiResponse =
  /** status 200 Request accepted and processing started */ DownloadResponse;
export type DownloadModelsApiArg = {
  /** Base path/subdirectory for model downloads (relative to MODELS_DIR) */
  downloadPath: string;
  modelDownloadRequest: ModelDownloadRequest;
};
export type GetJobStatusApiResponse =
  /** status 200 Job details retrieved successfully */ Job;
export type GetJobStatusApiArg = {
  /** The unique job identifier */
  jobId: string;
};
export type ListJobsApiResponse =
  /** status 200 List of all jobs */ JobListResponse;
export type ListJobsApiArg = void;
export type GetModelJobsApiResponse =
  /** status 200 Jobs for the model retrieved successfully */ JobListResponse;
export type GetModelJobsApiArg = {
  /** The model name */
  modelName: string;
};
export type GetModelResultsApiResponse =
  /** status 200 List of completed operations */ ModelResultsResponse;
export type GetModelResultsApiArg = void;
export type UploadModelApiResponse =
  /** status 200 Model uploaded successfully */ UploadResponse;
export type UploadModelApiArg = {
  body: {
    /** ZIP file containing `model.xml` and `model.bin` */
    file: Blob;
    /** Model name provided by user */
    model_name: string;
    /** Provider segment in target path */
    provider?: string;
    /** Framework segment in target path */
    framework?: string;
    /** Optional precision folder (for example FP16, FP32, or INT8) */
    precision?: string | null;
  };
};
export type ListPluginsApiResponse =
  /** status 200 Plugins information retrieved successfully */ PluginsResponse;
export type ListPluginsApiArg = void;
export type HealthResponse = {
  /** Health status of the service */
  status?: "ok";
};
export type DownloadResponse = {
  /** Status message */
  message?: string;
  /** List of job IDs created for the request */
  job_ids?: string[];
  /** Overall status of the request */
  status?: "processing";
};
export type ModelHub =
  | "huggingface"
  | "ollama"
  | "ultralytics"
  | "openvino"
  | "geti"
  | "hls";
export type ModelType = "llm" | "embeddings" | "reranker" | "vlm" | "vision";
export type ModelPrecision = "int8" | "fp16" | "fp32";
export type DeviceType = "CPU" | "GPU" | "NPU";
export type Config = {
  precision?: ModelPrecision;
  device?: DeviceType;
  /** Cache size for model optimization */
  cache_size?: number;
  /** Ultralytics quantization dataset used to enable INT8 export */
  quantize?: string | null;
};
export type ModelRequest = {
  /** The name/ID of the model (e.g., microsoft/Phi-3.5-mini-instruct) */
  name: string;
  hub: ModelHub;
  type?: ModelType;
  /** Whether to convert the model to OpenVINO IR format (requires OpenVINO plugin) */
  is_ovms?: boolean;
  /** Specific model revision/version to download */
  revision?: string;
  /** Configuration for OpenVINO conversion (required if is_ovms is true) */
  config?: Config;
};
export type ModelDownloadRequest = {
  /** List of models to download and/or convert */
  models: ModelRequest[];
  /** Whether to download models in parallel (currently not implemented) */
  parallel_downloads?: boolean;
};
export type JobStatus = "pending" | "processing" | "completed" | "failed";
export type Job = {
  /** Unique identifier for the job */
  job_id?: string;
  /** Type of operation */
  operation_type?: "download" | "convert";
  /** Name of the model */
  model_name?: string;
  /** Model hub source */
  hub?: string;
  status?: JobStatus;
  /** Output directory for the operation */
  output_dir?: string;
  /** Plugin handling the operation */
  plugin_name?: string;
  /** When the job was created */
  creation_time?: string;
  /** When the job was completed */
  completion_time?: string | null;
  /** Error message if job failed */
  error?: string | null;
};
export type JobListResponse = {
  /** List of jobs */
  jobs?: Job[];
};
export type ModelResultsResponse = {
  results?: {
    job_id?: string;
    model_name?: string;
    hub?: string;
    operation_type?: string;
    status?: string;
    model_path?: string;
    is_ovms?: boolean;
    completion_time?: string;
  }[];
};
export type UploadResponse = {
  status?: string;
  message?: string;
  /** Job ID for the completed upload operation */
  job_id?: string;
  /** Sanitized model name used for storage */
  model_name?: string;
  /** Final extracted model path */
  model_path?: string;
};
export type PluginInfo = {
  /** Plugin name */
  name?: string;
  /** Plugin type (hub or conversion) */
  type?: string;
  /** Plugin description */
  description?: string;
  capabilities?: {
    supports_parallel_downloads?: boolean;
  };
  /** Whether the plugin is available */
  available?: boolean;
  /** Reason if plugin is not available */
  unavailable_reason?: string | null;
};
export type PluginsResponse = {
  available_plugins?: {
    [key: string]: PluginInfo[];
  };
  /** Total number of plugins */
  total_count?: number;
  /** Number of available plugins */
  available_count?: number;
  /** Instructions for enabling/disabling plugins */
  activation_instructions?: string;
};
export const {
  useHealthCheckQuery,
  useLazyHealthCheckQuery,
  useDownloadModelsMutation,
  useGetJobStatusQuery,
  useLazyGetJobStatusQuery,
  useListJobsQuery,
  useLazyListJobsQuery,
  useGetModelJobsQuery,
  useLazyGetModelJobsQuery,
  useGetModelResultsQuery,
  useLazyGetModelResultsQuery,
  useUploadModelMutation,
  useListPluginsQuery,
  useLazyListPluginsQuery,
} = injectedRtkApi;
