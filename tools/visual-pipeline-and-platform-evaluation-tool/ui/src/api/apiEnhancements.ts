import { api } from "@/api/api.generated.ts";
import type { ExportBenchmarkSuiteRunCsvApiArg } from "@/api/api.generated.ts";

export type ExportBenchmarkSuiteRunCsvDownload = {
  blob: Blob;
  contentDisposition: string | null;
  contentType: string | null;
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
  }),
  overrideExisting: true,
});

export const { useLazyExportBenchmarkSuiteRunCsvQuery } = apiWithEnhancements;
