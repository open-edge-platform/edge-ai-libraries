import { format } from "date-fns";

export const formatElapsedTimeWithTenths = (seconds: number): string => {
  const total = Math.max(0, seconds);
  const minutes = Math.floor(total / 60);
  const formattedSeconds = (total % 60).toFixed(1).padStart(4, "0");
  return `${minutes}:${formattedSeconds}`;
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
