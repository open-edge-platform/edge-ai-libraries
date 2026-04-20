import { API_BASE_URL } from "./apiSlice";

/**
 * API endpoint URLs for manual requests (e.g., XMLHttpRequest for upload progress)
 */
export const ENDPOINTS = {
  UPLOAD_VIDEO: `${API_BASE_URL}/videos/upload`,
} as const;
