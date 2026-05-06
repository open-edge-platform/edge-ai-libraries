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
      queryFn: async ({ performanceTestSpec, serverIp }, api, extraOptions, baseQuery) => {
        const result = await baseQuery(
          {
            url: `/tests/performance`,
            method: "POST",
            body: performanceTestSpec,
          },
          api,
          { ...extraOptions, serverIp },
        );
        return result.error ? { error: result.error } : { data: result.data };
      },
      invalidatesTags: ["tests"],
    }),

    // Performance Job Status - Remote
    getRemotePerformanceJobStatus: build.query<
      GetPerformanceJobStatusApiResponse,
      GetPerformanceJobStatusApiArg & { serverIp?: string }
    >({
      queryFn: async ({ jobId, serverIp }, api, extraOptions, baseQuery) => {
        const result = await baseQuery(
          {
            url: `/jobs/tests/performance/${jobId}/status`,
          },
          api,
          { ...extraOptions, serverIp },
        );
        return result.error ? { error: result.error } : { data: result.data };
      },
      providesTags: ["jobs"],
    }),

    // Stop Performance Test - Remote
    stopRemotePerformanceTestJob: build.mutation<
      StopPerformanceTestJobApiResponse,
      StopPerformanceTestJobApiArg & { serverIp?: string }
    >({
      queryFn: async ({ jobId, serverIp }, api, extraOptions, baseQuery) => {
        const result = await baseQuery(
          {
            url: `/jobs/tests/performance/${jobId}`,
            method: "DELETE",
          },
          api,
          { ...extraOptions, serverIp },
        );
        return result.error ? { error: result.error } : { data: result.data };
      },
      invalidatesTags: ["jobs"],
    }),

    // Density Test - Remote
    runRemoteDensityTest: build.mutation<
      RunDensityTestApiResponse,
      RunDensityTestApiArg & { serverIp?: string }
    >({
      queryFn: async ({ densityTestSpec, serverIp }, api, extraOptions, baseQuery) => {
        const result = await baseQuery(
          {
            url: `/tests/density`,
            method: "POST",
            body: densityTestSpec,
          },
          api,
          { ...extraOptions, serverIp },
        );
        return result.error ? { error: result.error } : { data: result.data };
      },
      invalidatesTags: ["tests"],
    }),

    // Density Job Status - Remote
    getRemoteDensityJobStatus: build.query<
      GetDensityJobStatusApiResponse,
      GetDensityJobStatusApiArg & { serverIp?: string }
    >({
      queryFn: async ({ jobId, serverIp }, api, extraOptions, baseQuery) => {
        const result = await baseQuery(
          {
            url: `/jobs/tests/density/${jobId}/status`,
          },
          api,
          { ...extraOptions, serverIp },
        );
        return result.error ? { error: result.error } : { data: result.data };
      },
      providesTags: ["jobs"],
    }),

    // Stop Density Test - Remote
    stopRemoteDensityTestJob: build.mutation<
      StopDensityTestJobApiResponse,
      StopDensityTestJobApiArg & { serverIp?: string }
    >({
      queryFn: async ({ jobId, serverIp }, api, extraOptions, baseQuery) => {
        const result = await baseQuery(
          {
            url: `/jobs/tests/density/${jobId}`,
            method: "DELETE",
          },
          api,
          { ...extraOptions, serverIp },
        );
        return result.error ? { error: result.error } : { data: result.data };
      },
      invalidatesTags: ["jobs"],
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
} = remoteApiSlice;

