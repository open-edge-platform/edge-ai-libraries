import type { Node } from "@/api/api.generated";

// Element properties round-trip through the API as strings, so "false" is falsy.
export const isTruthyPropertyValue = (value: unknown): boolean =>
  value === true || String(value ?? "").toLowerCase() === "true";

// Mirrors Graph.has_file_gvametapublish() in the backend: a gvametapublish
// without an explicit method publishes to a file, like the element's default.
export const hasFileMetadataPublisher = (nodes: readonly Node[]): boolean =>
  nodes.some(
    (node) =>
      node.type === "gvametapublish" &&
      String(node.data?.["method"] ?? "file") === "file",
  );

export const hasMetadataPublisher = (nodes: readonly Node[]): boolean =>
  nodes.some((node) => node.type === "gvametapublish");
