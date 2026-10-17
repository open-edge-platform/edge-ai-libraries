// Minimal shape shared by API graph nodes and React Flow editor nodes.
type MetadataPublisherNode = {
  type?: string;
  data?: Record<string, unknown> | null;
};

// Mirrors Graph.has_file_gvametapublish() in the backend: a gvametapublish
// without an explicit method publishes to a file, like the element's default.
export const hasFileMetadataPublisher = (
  nodes: readonly MetadataPublisherNode[],
): boolean =>
  nodes.some(
    (node) =>
      node.type === "gvametapublish" &&
      String(node.data?.["method"] ?? "file") === "file",
  );

export const hasMetadataPublisher = (
  nodes: readonly MetadataPublisherNode[],
): boolean => nodes.some((node) => node.type === "gvametapublish");
