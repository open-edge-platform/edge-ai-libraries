// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { apiSlice } from "@/api/apiSlice";

export type OvmsPocRunRequest = {
  input_video: string;
  max_parallel_requests?: number;
  max_inference_width?: number;
  max_inference_height?: number;
  request_timeout_s?: number;
};

export type OvmsPocStatus = {
  job_id: string;
  state:
  | "STARTING"
  | "RUNNING"
  | "COMPLETED"
  | "CANCELLED"
  | "FAILED"
  | "UNKNOWN";
  frames_processed?: number;
  failed_frames?: number;
  fps?: number;
  duration_s?: number;
  end_to_end_fps?: number;
  ovms_fps?: number;
  mean_ovms_inference_ms?: number;
  p95_ovms_inference_ms?: number;
  output_video?: string;
  metadata_path?: string;
  message?: string;
};

export type OvmsPocMetadataRecord = {
  frame_id: number;
  timestamp_ms: number;
  ovms_inference_ms?: number;
  response_timestamp?: number;
  output_shape?: number[];
  error?: string;
};

const ovmsPocApi = apiSlice.injectEndpoints({
  endpoints: (build) => ({
    runOvmsPoc: build.mutation<{ job_id: string }, OvmsPocRunRequest>({
      query: (body) => ({ url: "/ovms-poc/run", method: "POST", body }),
    }),
    getOvmsPocJob: build.query<OvmsPocStatus, string>({
      query: (jobId) => ({ url: `/ovms-poc/jobs/${jobId}` }),
    }),
    stopOvmsPocJob: build.mutation<{ message: string }, string>({
      query: (jobId) => ({
        url: `/ovms-poc/jobs/${jobId}/stop`,
        method: "POST",
      }),
    }),
    getOvmsPocMetadata: build.query<OvmsPocMetadataRecord[], string>({
      query: (jobId) => ({
        url: `/ovms-poc/jobs/${jobId}/metadata`,
        params: { limit: 200 },
      }),
    }),
  }),
});

export const {
  useRunOvmsPocMutation,
  useGetOvmsPocJobQuery,
  useStopOvmsPocJobMutation,
  useGetOvmsPocMetadataQuery,
} = ovmsPocApi;
