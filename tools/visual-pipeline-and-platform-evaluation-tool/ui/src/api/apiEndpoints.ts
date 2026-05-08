import { API_BASE_URL } from "./apiSlice";
import { MODEL_DOWNLOAD_API_BASE_URL } from "./apiModelDownloadSlice";

/**
 * API endpoint URLs for manual requests (e.g., XMLHttpRequest for upload progress)
 */
export const ENDPOINTS = {
  UPLOAD_VIDEO: `${API_BASE_URL}/videos/upload`,
  UPLOAD_IMAGE_ARCHIVE: `${API_BASE_URL}/images/upload`,
  UPLOAD_MODEL: `${MODEL_DOWNLOAD_API_BASE_URL}/models/upload`,
} as const;
