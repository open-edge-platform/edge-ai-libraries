import { baseApi as api } from "./baseApi";
export const addTagTypes = [
  "instances",
  "benchmarks",
  "experiments",
  "tests",
  "health",
] as const;
const injectedRtkApi = api
  .enhanceEndpoints({
    addTagTypes,
  })
  .injectEndpoints({
    endpoints: build => ({
      getInstances: build.query<GetInstancesApiResponse, GetInstancesApiArg>({
        query: () => ({ url: `/api/v1/instances` }),
        providesTags: ["instances"],
      }),
      addInstance: build.mutation<AddInstanceApiResponse, AddInstanceApiArg>({
        query: queryArg => ({
          url: `/api/v1/instances`,
          method: "POST",
          body: queryArg,
        }),
        invalidatesTags: ["instances"],
      }),
      updateInstance: build.mutation<
        UpdateInstanceApiResponse,
        UpdateInstanceApiArg
      >({
        query: queryArg => ({
          url: `/api/v1/instances/${encodeURIComponent(String(queryArg.instanceId))}`,
          method: "PATCH",
          body: queryArg.instanceUpdate,
        }),
        invalidatesTags: ["instances"],
      }),
      deleteInstance: build.mutation<
        DeleteInstanceApiResponse,
        DeleteInstanceApiArg
      >({
        query: queryArg => ({
          url: `/api/v1/instances/${encodeURIComponent(String(queryArg))}`,
          method: "DELETE",
        }),
        invalidatesTags: ["instances"],
      }),
      getBenchmarkRuns: build.query<
        GetBenchmarkRunsApiResponse,
        GetBenchmarkRunsApiArg
      >({
        query: () => ({ url: `/api/v1/benchmarks/runs` }),
        providesTags: ["benchmarks"],
      }),
      getBenchmarkSuites: build.query<
        GetBenchmarkSuitesApiResponse,
        GetBenchmarkSuitesApiArg
      >({
        query: () => ({ url: `/api/v1/benchmarks/suites` }),
        providesTags: ["benchmarks"],
      }),
      compareBenchmarkRuns: build.query<
        CompareBenchmarkRunsApiResponse,
        CompareBenchmarkRunsApiArg
      >({
        query: queryArg => ({
          url: `/api/v1/benchmarks/compare`,
          params: {
            refs: queryArg,
          },
        }),
        providesTags: ["benchmarks"],
      }),
      getBenchmarkRunDetails: build.query<
        GetBenchmarkRunDetailsApiResponse,
        GetBenchmarkRunDetailsApiArg
      >({
        query: queryArg => ({
          url: `/api/v1/benchmarks/runs/${encodeURIComponent(String(queryArg))}`,
        }),
        providesTags: ["benchmarks"],
      }),
      getExperiments: build.query<
        GetExperimentsApiResponse,
        GetExperimentsApiArg
      >({
        query: () => ({ url: `/api/v1/experiments` }),
        providesTags: ["experiments"],
      }),
      startExperiment: build.mutation<
        StartExperimentApiResponse,
        StartExperimentApiArg
      >({
        query: queryArg => ({
          url: `/api/v1/experiments`,
          method: "POST",
          body: queryArg,
        }),
        invalidatesTags: ["experiments"],
      }),
      getPipelineCatalog: build.query<
        GetPipelineCatalogApiResponse,
        GetPipelineCatalogApiArg
      >({
        query: () => ({ url: `/api/v1/experiments/pipelines` }),
        providesTags: ["experiments"],
      }),
      getTestExperiments: build.query<
        GetTestExperimentsApiResponse,
        GetTestExperimentsApiArg
      >({
        query: queryArg => ({
          url: `/api/v1/experiments/tests/${encodeURIComponent(String(queryArg))}`,
        }),
        providesTags: ["experiments"],
      }),
      startTestExperiment: build.mutation<
        StartTestExperimentApiResponse,
        StartTestExperimentApiArg
      >({
        query: queryArg => ({
          url: `/api/v1/experiments/tests/${encodeURIComponent(String(queryArg.kind))}`,
          method: "POST",
          body: queryArg.testExperimentCreate,
        }),
        invalidatesTags: ["experiments"],
      }),
      deleteTestExperiment: build.mutation<
        DeleteTestExperimentApiResponse,
        DeleteTestExperimentApiArg
      >({
        query: queryArg => ({
          url: `/api/v1/experiments/tests/${encodeURIComponent(String(queryArg))}`,
          method: "DELETE",
        }),
        invalidatesTags: ["experiments"],
      }),
      deleteExperiment: build.mutation<
        DeleteExperimentApiResponse,
        DeleteExperimentApiArg
      >({
        query: queryArg => ({
          url: `/api/v1/experiments/${encodeURIComponent(String(queryArg))}`,
          method: "DELETE",
        }),
        invalidatesTags: ["experiments"],
      }),
      getTestJobs: build.query<GetTestJobsApiResponse, GetTestJobsApiArg>({
        query: queryArg => ({
          url: `/api/v1/tests/${encodeURIComponent(String(queryArg))}`,
        }),
        providesTags: ["tests"],
      }),
      compareTestJobs: build.query<
        CompareTestJobsApiResponse,
        CompareTestJobsApiArg
      >({
        query: queryArg => ({
          url: `/api/v1/tests/${encodeURIComponent(String(queryArg.kind))}/compare`,
          params: {
            refs: queryArg.refs,
          },
        }),
        providesTags: ["tests"],
      }),
      getHealth: build.query<GetHealthApiResponse, GetHealthApiArg>({
        query: () => ({ url: `/api/v1/health` }),
        providesTags: ["health"],
      }),
    }),
    overrideExisting: false,
  });
export { injectedRtkApi as generatedApi };
export type GetInstancesApiResponse =
  /** status 200 Successful Response */ InstanceHealth[];
export type GetInstancesApiArg = void;
export type AddInstanceApiResponse =
  /** status 201 Successful Response */ Instance;
export type AddInstanceApiArg = InstanceCreate;
export type UpdateInstanceApiResponse =
  /** status 200 Successful Response */ Instance;
export type UpdateInstanceApiArg = {
  instanceId: number;
  instanceUpdate: InstanceUpdate;
};
export type DeleteInstanceApiResponse = unknown;
export type DeleteInstanceApiArg = number;
export type GetBenchmarkRunsApiResponse =
  /** status 200 Successful Response */ BenchmarkRun[];
export type GetBenchmarkRunsApiArg = void;
export type GetBenchmarkSuitesApiResponse =
  /** status 200 Successful Response */ BenchmarkSuite[];
export type GetBenchmarkSuitesApiArg = void;
export type CompareBenchmarkRunsApiResponse =
  /** status 200 Successful Response */ Comparison;
export type CompareBenchmarkRunsApiArg =
  /** Run refs: <instance>:<slug>:<id> */ string[] | undefined;
export type GetBenchmarkRunDetailsApiResponse =
  /** status 200 Successful Response */ {
    [key: string]: any;
  };
export type GetBenchmarkRunDetailsApiArg = string;
export type GetExperimentsApiResponse =
  /** status 200 Successful Response */ Experiment[];
export type GetExperimentsApiArg = void;
export type StartExperimentApiResponse =
  /** status 201 Successful Response */ Experiment;
export type StartExperimentApiArg = ExperimentCreate;
export type GetPipelineCatalogApiResponse =
  /** status 200 Successful Response */ Pipeline[];
export type GetPipelineCatalogApiArg = void;
export type GetTestExperimentsApiResponse =
  /** status 200 Successful Response */ TestExperiment[];
export type GetTestExperimentsApiArg = TestKind;
export type StartTestExperimentApiResponse =
  /** status 201 Successful Response */ TestExperiment;
export type StartTestExperimentApiArg = {
  kind: TestKind;
  testExperimentCreate: TestExperimentCreate;
};
export type DeleteTestExperimentApiResponse = unknown;
export type DeleteTestExperimentApiArg = number;
export type DeleteExperimentApiResponse = unknown;
export type DeleteExperimentApiArg = number;
export type GetTestJobsApiResponse =
  /** status 200 Successful Response */ TestJob[];
export type GetTestJobsApiArg = TestKind;
export type CompareTestJobsApiResponse =
  /** status 200 Successful Response */ Comparison;
export type CompareTestJobsApiArg = {
  kind: TestKind;
  /** Job refs: <instance>:<job_id> */
  refs?: string[];
};
export type GetHealthApiResponse = /** status 200 Successful Response */ {
  [key: string]: boolean;
};
export type GetHealthApiArg = void;
export type InstanceHealth = {
  id: number;
  name: string;
  url: string;
  enabled: boolean;
  notes: string | null;
  cpu: string | null;
  gpu: string | null;
  npu: string | null;
  version: string | null;
  reachable: boolean;
  ready: boolean;
  status: string | null;
  error: string | null;
  benchmark_run_count: number;
  performance_job_count: number;
  density_job_count: number;
  best_score: number | null;
  last_run_time: number | null;
};
export type Instance = {
  id: number;
  name: string;
  url: string;
  enabled: boolean;
  notes: string | null;
  cpu: string | null;
  gpu: string | null;
  npu: string | null;
  version: string | null;
};
export type ValidationError = {
  loc: (string | number)[];
  msg: string;
  type: string;
};
export type HttpValidationError = {
  detail?: ValidationError[];
};
export type InstanceCreate = {
  url: string;
  name?: string | null;
  notes?: string | null;
};
export type InstanceUpdate = {
  url?: string | null;
  name?: string | null;
  notes?: string | null;
  enabled?: boolean | null;
};
export type BenchmarkRun = {
  instance_id: number;
  instance_name: string;
  instance_url: string;
  cpu: string | null;
  id: number;
  suite_slug: string;
  suite_name: string | null;
  status: string;
  score_total: number | null;
  score_performance: number | null;
  score_efficiency: number | null;
  start_time: number;
  execution_time: number | null;
  total_test_cases: number | null;
  passed_test_cases: number | null;
  ref: string;
};
export type BenchmarkSuite = {
  slug: string;
  name: string;
  description: string | null;
  workload_count: number;
  instance_ids: number[];
};
export type ComparisonColumn = {
  ref: string;
  label: string;
  instance_id: number;
  instance_name: string;
  cpu: string | null;
  status: string | null;
  start_time: number | null;
  summary: {
    [key: string]: number | null;
  };
};
export type ComparisonRow = {
  key: string;
  label: string;
  group: string | null;
  cells: {
    [key: string]: {
      [key: string]: any;
    };
  };
};
export type Comparison = {
  columns: ComparisonColumn[];
  rows: ComparisonRow[];
  metrics: string[];
  errors: {
    [key: string]: string;
  };
};
export type ExperimentRun = {
  instance_id: number;
  instance_name: string;
  cpu: string | null;
  job_id: string | null;
  state: string;
  error: string | null;
  start_time: number | null;
  elapsed_time: number | null;
  total_test_cases: number | null;
  completed_test_cases: number | null;
  score_total: number | null;
  score_performance: number | null;
  score_efficiency: number | null;
  ref: string | null;
};
export type Experiment = {
  id: number;
  suite_slug: string;
  suite_name: string | null;
  created_at: string;
  state: string;
  runs: ExperimentRun[];
};
export type ExperimentCreate = {
  suite_slug: string;
  instance_ids: number[];
};
export type PipelineVariant = {
  id: string;
  name: string;
};
export type Pipeline = {
  id: string;
  name: string;
  variants: PipelineVariant[];
  instance_ids: number[];
};
export type TestKind = "performance" | "density";
export type TestExperimentRun = {
  instance_id: number;
  instance_name: string;
  cpu: string | null;
  job_id: string | null;
  state: string;
  error: string | null;
  start_time: number | null;
  elapsed_time: number | null;
  total_fps: number | null;
  per_stream_fps: number | null;
  total_streams: number | null;
  ref: string | null;
};
export type TestExperiment = {
  id: number;
  kind: TestKind;
  pipeline_id: string;
  variant_id: string;
  label: string;
  streams: number | null;
  max_runtime: number | null;
  fps_floor: number | null;
  created_at: string;
  state: string;
  runs: TestExperimentRun[];
};
export type TestExperimentCreate = {
  pipeline_id: string;
  variant_id: string;
  instance_ids: number[];
  streams?: number;
  max_runtime?: number;
  fps_floor?: number;
};
export type TestJob = {
  instance_id: number;
  instance_name: string;
  instance_url: string;
  cpu: string | null;
  id: string;
  kind: TestKind;
  state: string;
  start_time: number | null;
  elapsed_time: number | null;
  total_fps: number | null;
  per_stream_fps: number | null;
  total_streams: number | null;
  details: string[];
  workload: string | null;
  pipelines: string[];
  ref: string;
};
export const {
  useGetInstancesQuery,
  useAddInstanceMutation,
  useUpdateInstanceMutation,
  useDeleteInstanceMutation,
  useGetBenchmarkRunsQuery,
  useGetBenchmarkSuitesQuery,
  useCompareBenchmarkRunsQuery,
  useGetBenchmarkRunDetailsQuery,
  useGetExperimentsQuery,
  useStartExperimentMutation,
  useGetPipelineCatalogQuery,
  useGetTestExperimentsQuery,
  useStartTestExperimentMutation,
  useDeleteTestExperimentMutation,
  useDeleteExperimentMutation,
  useGetTestJobsQuery,
  useCompareTestJobsQuery,
  useGetHealthQuery,
} = injectedRtkApi;
