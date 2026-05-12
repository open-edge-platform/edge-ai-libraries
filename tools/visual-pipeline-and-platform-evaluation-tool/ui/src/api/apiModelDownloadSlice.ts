import { createApi, fetchBaseQuery } from "@reduxjs/toolkit/query/react";

export const MODEL_DOWNLOAD_API_BASE_URL = "/model-download/api/v1";

export const apiModelDownloadSlice = createApi({
  reducerPath: "apiModelDownload",
  baseQuery: fetchBaseQuery({
    baseUrl: MODEL_DOWNLOAD_API_BASE_URL,
    prepareHeaders: (headers) => {
      headers.set("Content-Type", "application/json");
      return headers;
    },
  }),
  endpoints: () => ({}),
});
