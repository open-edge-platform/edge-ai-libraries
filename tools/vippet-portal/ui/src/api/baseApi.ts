import { createApi, fetchBaseQuery } from "@reduxjs/toolkit/query/react";

const paramsSerializer = (params: Record<string, unknown>) => {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null) continue;
    for (const item of Array.isArray(value) ? value : [value]) {
      search.append(key, String(item));
    }
  }
  return search.toString();
};

export const baseApi = createApi({
  reducerPath: "portalApi",
  baseQuery: fetchBaseQuery({ paramsSerializer }),
  endpoints: () => ({}),
});
