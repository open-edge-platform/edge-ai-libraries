/**
 * Remote API extensions for multi-server support
 * 
 * This module provides enhanced versions of the auto-generated API hooks
 * that support dynamic server IP targeting for remote test execution.
 */

import { apiSlice } from "./apiSlice";
import type {
  RunPerformanceTestApiArg,
  RunPerformanceTestApiResponse,
  RunDensityTestApiArg,
  RunDensityTestApiResponse,
  GetPerformanceJobStatusApiArg,
  GetPerformanceJobStatusApiResponse,
  GetDensityJobStatusApiArg,
  GetDensityJobStatusApiResponse,
  StopPerformanceTestJobApiArg,
  StopPerformanceTestJobApiResponse,
  StopDensityTestJobApiArg,
  StopDensityTestJobApiResponse,
  ValidatePipelineApiArg,
  ValidatePipelineApiResponse,
  CreatePipelineApiArg,
  CreatePipelineApiResponse,
} from "./api.generated";

/**
 * Remote-enabled API endpoints
 * Enhances auto-generated endpoints to support serverIp parameter for remote execution
 */
export const remoteApiSlice = apiSlice.injectEndpoints({
  endpoints: (build) => ({
    // Performance Test - Remote
    runRemotePerformanceTest: build.mutation<
      RunPerformanceTestApiResponse,
      RunPerformanceTestApiArg & { serverIp?: string }
    >({
      queryFn: async ({ performanceTestSpec, serverIp }, _api, _extraOptions, baseQuery) => {
        const result = await baseQuery({
          url: `/tests/performance`,
          method: "POST",
          body: performanceTestSpec,
          _serverIp: serverIp,
        });
        return result.error ? { error: result.error } : { data: result.data };
      },
      invalidatesTags: ["tests"],
    }),

    // Performance Job Status - Remote
    getRemotePerformanceJobStatus: build.query<
      GetPerformanceJobStatusApiResponse,
      GetPerformanceJobStatusApiArg & { serverIp?: string }
    >({
      queryFn: async ({ jobId, serverIp }, _api, _extraOptions, baseQuery) => {
        const result = await baseQuery({
          url: `/jobs/tests/performance/${jobId}/status`,
          _serverIp: serverIp,
        });
        return result.error ? { error: result.error } : { data: result.data };
      },
      providesTags: ["jobs"],
    }),

    // Stop Performance Test - Remote
    stopRemotePerformanceTestJob: build.mutation<
      StopPerformanceTestJobApiResponse,
      StopPerformanceTestJobApiArg & { serverIp?: string }
    >({
      queryFn: async ({ jobId, serverIp }, _api, _extraOptions, baseQuery) => {
        const result = await baseQuery({
          url: `/jobs/tests/performance/${jobId}`,
          method: "DELETE",
          _serverIp: serverIp,
        });
        return result.error ? { error: result.error } : { data: result.data };
      },
      invalidatesTags: ["jobs"],
    }),

    // Density Test - Remote
    runRemoteDensityTest: build.mutation<
      RunDensityTestApiResponse,
      RunDensityTestApiArg & { serverIp?: string }
    >({
      queryFn: async ({ densityTestSpec, serverIp }, _api, _extraOptions, baseQuery) => {
        const result = await baseQuery({
          url: `/tests/density`,
          method: "POST",
          body: densityTestSpec,
          _serverIp: serverIp,
        });
        return result.error ? { error: result.error } : { data: result.data };
      },
      invalidatesTags: ["tests"],
    }),

    // Density Job Status - Remote
    getRemoteDensityJobStatus: build.query<
      GetDensityJobStatusApiResponse,
      GetDensityJobStatusApiArg & { serverIp?: string }
    >({
      queryFn: async ({ jobId, serverIp }, _api, _extraOptions, baseQuery) => {
        const result = await baseQuery({
          url: `/jobs/tests/density/${jobId}/status`,
          _serverIp: serverIp,
        });
        return result.error ? { error: result.error } : { data: result.data };
      },
      providesTags: ["jobs"],
    }),

    // Stop Density Test - Remote
    stopRemoteDensityTestJob: build.mutation<
      StopDensityTestJobApiResponse,
      StopDensityTestJobApiArg & { serverIp?: string }
    >({
      queryFn: async ({ jobId, serverIp }, _api, _extraOptions, baseQuery) => {
        const result = await baseQuery({
          url: `/jobs/tests/density/${jobId}`,
          method: "DELETE",
          _serverIp: serverIp,
        });
        return result.error ? { error: result.error } : { data: result.data };
      },
      invalidatesTags: ["jobs"],
    }),

    // Validate Pipeline - Remote
    validateRemotePipeline: build.mutation<
      ValidatePipelineApiResponse,
      ValidatePipelineApiArg & { serverIp?: string }
    >({
      queryFn: async ({ pipelineValidationInput, serverIp }, _api, _extraOptions, baseQuery) => {
        const result = await baseQuery({
          url: `/pipelines/validate`,
          method: "POST",
          body: pipelineValidationInput,
          _serverIp: serverIp,
        });
        return result.error ? { error: result.error } : { data: result.data };
      },
    }),

    // Create Pipeline - Remote
    createRemotePipeline: build.mutation<
      CreatePipelineApiResponse,
      CreatePipelineApiArg & { serverIp?: string }
    >({
      queryFn: async ({ pipelineDefinition, serverIp }, _api, _extraOptions, baseQuery) => {
        const result = await baseQuery({
          url: `/pipelines`,
          method: "POST",
          body: pipelineDefinition,
          _serverIp: serverIp,
        });
        return result.error ? { error: result.error } : { data: result.data };
      },
    }),
  }),
  overrideExisting: true,
});

export const {
  useRunRemotePerformanceTestMutation,
  useGetRemotePerformanceJobStatusQuery,
  useStopRemotePerformanceTestJobMutation,
  useRunRemoteDensityTestMutation,
  useGetRemoteDensityJobStatusQuery,
  useStopRemoteDensityTestJobMutation,
  useValidateRemotePipelineMutation,
  useCreateRemotePipelineMutation,
} = remoteApiSlice;

