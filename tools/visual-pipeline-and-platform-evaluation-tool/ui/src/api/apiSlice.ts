import { createApi, fetchBaseQuery } from "@reduxjs/toolkit/query/react";
import type { BaseQueryFn } from "@reduxjs/toolkit/query";

export const API_BASE_URL = "/api/v1";

const _serversHost = import.meta.env.VITE_SERVERS_HOST as string | undefined;
export const SERVERS_BASE_URL = _serversHost
  ? `http://${_serversHost}/api/v1`
  : API_BASE_URL;

export const ADMIN_API_KEY: string = (import.meta.env.VITE_ADMIN_API_KEY as string | undefined) ?? "";

/**
 * Dynamic base query that supports per-request server IP override.
 * 
 * The serverIp is passed as `_serverIp` inside the args object because
 * RTK Query's queryFn provides a pre-bound baseQuery that only accepts
 * args (not api or extraOptions). We extract _serverIp from args,
 * use it to determine the base URL, then forward clean args to fetchBaseQuery.
 */
const dynamicBaseQuery: BaseQueryFn<
  string | { url: string; method?: string; body?: unknown; params?: unknown; _serverIp?: string },
  unknown,
  unknown
> = async (args, api, extraOptions) => {
  // Extract serverIp from args if it's an object with _serverIp
  let serverIp: string | undefined;
  let cleanArgs = args;

  if (typeof args !== "string" && args._serverIp) {
    serverIp = args._serverIp;
    const { _serverIp, ...rest } = args;
    cleanArgs = rest;
  }

  // Determine base URL: remote server or localhost
  const baseUrl = serverIp
    ? `http://${serverIp}/api/v1`
    : API_BASE_URL;

  // Create a fetchBaseQuery instance with the determined base URL
  const baseQuery = fetchBaseQuery({
    baseUrl,
    prepareHeaders: (headers) => {
      headers.set("Content-Type", "application/json");
      return headers;
    },
  });

  return baseQuery(cleanArgs, api, extraOptions);
};

export const apiSlice = createApi({
  reducerPath: "api",
  baseQuery: dynamicBaseQuery,
  endpoints: () => ({}),
});
