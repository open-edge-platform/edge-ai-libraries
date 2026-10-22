import { format } from "date-fns";
import type { PipelineEvent } from "@/api/api.generated";

export const formatPosition = (event: PipelineEvent): string => {
  if (event.pts_seconds != null) {
    const total = Math.max(0, event.pts_seconds);
    const minutes = Math.floor(total / 60);
    const seconds = (total % 60).toFixed(1).padStart(4, "0");
    return `${minutes}:${seconds}`;
  }
  return new Date(event.timestamp_ms).toLocaleTimeString();
};

export const formatElapsedTimeMillis = (milliseconds: number) => {
  const seconds = milliseconds / 1000;
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}m ${secs}s`;
};

export const formatElapsedTimeSeconds = (seconds: number) => {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}m ${secs}s`;
};

export const formatTimestamp = (timestamp: number) =>
  format(new Date(timestamp), "MMM d, yyyy HH:mm:ss");
