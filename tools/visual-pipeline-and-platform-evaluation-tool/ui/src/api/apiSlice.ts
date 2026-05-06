import { createApi, fetchBaseQuery } from "@reduxjs/toolkit/query/react";
import type { BaseQueryFn } from "@reduxjs/toolkit/query";

export const API_BASE_URL = "/api/v1";
export const VIPPET_API_PORT = 7860;

/**
 * Dynamic base query that supports per-request server IP override
 * 
 * Usage:
 * - Default: Uses `/api/v1` (localhost)
 * - Remote: Pass `serverIp` in extraOptions: `{ serverIp: "192.168.1.100" }`
 *   Results in: `http://192.168.1.100:7860/api/v1`
 */
const dynamicBaseQuery: BaseQueryFn<
  string | { url: string; method?: string; body?: unknown; params?: unknown },
  unknown,
  unknown,
  { serverIp?: string }
> = async (args, api, extraOptions) => {
  const serverIp = extraOptions?.serverIp;
  
  // Determine base URL: remote server or localhost
  const baseUrl = serverIp
    ? `http://${serverIp}:${VIPPET_API_PORT}/api/v1`
    : API_BASE_URL;

  // Create a fetchBaseQuery instance with the determined base URL
  const baseQuery = fetchBaseQuery({
    baseUrl,
    prepareHeaders: (headers) => {
      headers.set("Content-Type", "application/json");
      return headers;
    },
  });

  return baseQuery(args, api, extraOptions);
};

export const apiSlice = createApi({
  reducerPath: "api",
  baseQuery: dynamicBaseQuery,
  endpoints: () => ({}),
});
