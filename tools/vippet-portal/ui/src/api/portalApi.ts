import { createApi, fetchBaseQuery } from "@reduxjs/toolkit/query/react";

export const API_BASE_URL = "/api/v1";

export type TestKind = "performance" | "density";

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

export type BenchmarkRun = {
  ref: string;
  id: number;
  instance_id: number;
  instance_name: string;
  instance_url: string;
  cpu: string | null;
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
};

export type TestJob = {
  ref: string;
  id: string;
  kind: TestKind;
  instance_id: number;
  instance_name: string;
  instance_url: string;
  cpu: string | null;
  state: string;
  start_time: number | null;
  elapsed_time: number | null;
  total_fps: number | null;
  per_stream_fps: number | null;
  total_streams: number | null;
  details: string[];
  workload: string | null;
  pipelines: string[];
};

export type BenchmarkSuite = {
  slug: string;
  name: string;
  description: string | null;
  workload_count: number;
  instance_ids: number[];
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

export type ComparisonColumn = {
  ref: string;
  label: string;
  instance_id: number;
  instance_name: string;
  cpu: string | null;
  status: string | null;
  start_time: number | null;
  summary: Record<string, number | null>;
};

export type ComparisonRow = {
  key: string;
  label: string;
  group: string | null;
  cells: Record<string, Record<string, unknown>>;
};

export type Comparison = {
  columns: ComparisonColumn[];
  rows: ComparisonRow[];
  metrics: string[];
  errors: Record<string, string>;
};

export type BenchmarkRunDetails = BenchmarkRun & {
  suite_description: string | null;
  workload_runs: Array<{
    id: number;
    pipeline_id: string | null;
    status: string;
    score_total: number | null;
    score_performance: number | null;
    score_efficiency: number | null;
    execution_time: number | null;
    test_case_runs: Array<Record<string, number | string | null>>;
  }>;
};

/** FastAPI expects `refs` repeated once per value, not comma-joined. */
const refsQuery = (refs: string[]) =>
  refs.map((ref) => `refs=${encodeURIComponent(ref)}`).join("&");

export const portalApi = createApi({
  reducerPath: "portalApi",
  baseQuery: fetchBaseQuery({ baseUrl: API_BASE_URL }),
  tagTypes: ["instances", "benchmarks", "experiments", "tests"],
  endpoints: (build) => ({
    getInstances: build.query<InstanceHealth[], void>({
      query: () => "/instances",
      providesTags: ["instances"],
    }),
    addInstance: build.mutation<
      InstanceHealth,
      { url: string; name?: string; notes?: string }
    >({
      query: (body) => ({ url: "/instances", method: "POST", body }),
      invalidatesTags: ["instances", "benchmarks", "tests"],
    }),
    updateInstance: build.mutation<
      InstanceHealth,
      {
        id: number;
        url?: string;
        name?: string;
        notes?: string;
        enabled?: boolean;
      }
    >({
      query: ({ id, ...body }) => ({
        url: `/instances/${id}`,
        method: "PATCH",
        body,
      }),
      invalidatesTags: ["instances", "benchmarks", "tests"],
    }),
    deleteInstance: build.mutation<void, number>({
      query: (id) => ({ url: `/instances/${id}`, method: "DELETE" }),
      invalidatesTags: ["instances", "benchmarks", "experiments", "tests"],
    }),

    getBenchmarkRuns: build.query<BenchmarkRun[], void>({
      query: () => "/benchmarks/runs",
      providesTags: ["benchmarks"],
    }),
    getBenchmarkRunDetails: build.query<BenchmarkRunDetails, string>({
      query: (ref) => `/benchmarks/runs/${encodeURIComponent(ref)}`,
      providesTags: ["benchmarks"],
    }),
    compareBenchmarkRuns: build.query<Comparison, string[]>({
      query: (refs) => `/benchmarks/compare?${refsQuery(refs)}`,
      providesTags: ["benchmarks"],
    }),

    getBenchmarkSuites: build.query<BenchmarkSuite[], void>({
      query: () => "/benchmarks/suites",
      providesTags: ["benchmarks"],
    }),
    getExperiments: build.query<Experiment[], void>({
      query: () => "/experiments",
      providesTags: ["experiments"],
    }),
    startExperiment: build.mutation<
      Experiment,
      { suite_slug: string; instance_ids: number[] }
    >({
      query: (body) => ({ url: "/experiments", method: "POST", body }),
      invalidatesTags: ["experiments", "benchmarks"],
    }),
    deleteExperiment: build.mutation<void, number>({
      query: (id) => ({ url: `/experiments/${id}`, method: "DELETE" }),
      invalidatesTags: ["experiments"],
    }),

    getPipelineCatalog: build.query<Pipeline[], void>({
      query: () => "/experiments/pipelines",
      providesTags: ["instances"],
    }),
    getTestExperiments: build.query<TestExperiment[], TestKind>({
      query: (kind) => `/experiments/tests/${kind}`,
      providesTags: ["experiments"],
    }),
    startTestExperiment: build.mutation<
      TestExperiment,
      {
        kind: TestKind;
        pipeline_id: string;
        variant_id: string;
        instance_ids: number[];
        streams?: number;
        max_runtime?: number;
        fps_floor?: number;
      }
    >({
      query: ({ kind, ...body }) => ({
        url: `/experiments/tests/${kind}`,
        method: "POST",
        body,
      }),
      invalidatesTags: ["experiments", "tests"],
    }),
    deleteTestExperiment: build.mutation<void, number>({
      query: (id) => ({ url: `/experiments/tests/${id}`, method: "DELETE" }),
      invalidatesTags: ["experiments"],
    }),

    getTestJobs: build.query<TestJob[], TestKind>({
      query: (kind) => `/tests/${kind}`,
      providesTags: ["tests"],
    }),
    compareTestJobs: build.query<
      Comparison,
      { kind: TestKind; refs: string[] }
    >({
      query: ({ kind, refs }) => `/tests/${kind}/compare?${refsQuery(refs)}`,
      providesTags: ["tests"],
    }),
  }),
});

export const {
  useGetInstancesQuery,
  useAddInstanceMutation,
  useUpdateInstanceMutation,
  useDeleteInstanceMutation,
  useGetBenchmarkRunsQuery,
  useGetBenchmarkRunDetailsQuery,
  useCompareBenchmarkRunsQuery,
  useGetBenchmarkSuitesQuery,
  useGetExperimentsQuery,
  useStartExperimentMutation,
  useDeleteExperimentMutation,
  useGetPipelineCatalogQuery,
  useGetTestExperimentsQuery,
  useStartTestExperimentMutation,
  useDeleteTestExperimentMutation,
  useGetTestJobsQuery,
  useCompareTestJobsQuery,
} = portalApi;
