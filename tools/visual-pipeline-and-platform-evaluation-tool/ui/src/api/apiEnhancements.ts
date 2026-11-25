// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { api } from "@/api/api.generated.ts";
import type {
  ExportBenchmarkSuiteRunCsvApiArg,
  ExportVariantAsAppApiArg,
} from "@/api/api.generated.ts";

export type ExportBenchmarkSuiteRunCsvDownload = {
  blob: Blob;
  contentDisposition: string | null;
  contentType: string | null;
};

export type ExportVariantAsAppDownload = {
  blob: Blob;
  contentDisposition: string | null;
};

export const apiWithEnhancements = api.injectEndpoints({
  endpoints: (build) => ({
    exportBenchmarkSuiteRunCsv: build.query<
      ExportBenchmarkSuiteRunCsvDownload,
      ExportBenchmarkSuiteRunCsvApiArg
    >({
      query: (queryArg) => ({
        url: `/benchmarks/${queryArg.suiteSlug}/run/${queryArg.runId}/csv`,
        headers: {
          Accept: "text/csv",
        },
        responseHandler: async (response) => ({
          blob: await response.blob(),
          contentDisposition: response.headers.get("content-disposition"),
          contentType: response.headers.get("content-type"),
        }),
      }),
      providesTags: ["benchmarks"],
    }),
    exportVariantAsApp: build.mutation<
      ExportVariantAsAppDownload,
      ExportVariantAsAppApiArg
    >({
      query: (queryArg) => ({
        url: `/pipelines/${queryArg.pipelineId}/variants/${queryArg.variantId}/export-app`,
        method: "POST",
        headers: {
          Accept: "application/zip",
        },
        // Errors come back as JSON MessageResponse, so only a success is read as a file.
        responseHandler: async (response) =>
          response.ok
            ? {
                blob: await response.blob(),
                contentDisposition: response.headers.get("content-disposition"),
              }
            : response.json(),
      }),
    }),
  }),
  overrideExisting: true,
});

export const {
  useLazyExportBenchmarkSuiteRunCsvQuery,
  useExportVariantAsAppMutation,
} = apiWithEnhancements;
