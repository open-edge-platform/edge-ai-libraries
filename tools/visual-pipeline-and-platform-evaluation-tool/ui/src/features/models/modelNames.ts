import type { Node } from "@/api/api.generated.ts";

const MODEL_DETAILS_SUFFIX_PATTERN =
  // Model nodes may carry trailing details like "(FP16)" or
  // [model-proc: ...]" which the models API does not expect.
  /(?:\s*(?:\([^)]*\)|\[model-proc:[^[\]\n]*]?))+\s*$/i;

export const normalizeModelDisplayName = (value: string): string =>
  value.replace(MODEL_DETAILS_SUFFIX_PATTERN, "").trim();

export const extractModelNamesFromNodes = (nodes: Node[] = []): string[] => {
  const uniqueModels = new Set<string>();

  nodes.forEach((node) => {
    if (!node?.data || typeof node.data !== "object") {
      return;
    }

    const rawModel = (node.data as Record<string, unknown>).model;
    if (typeof rawModel !== "string") {
      return;
    }

    const normalizedModel = normalizeModelDisplayName(rawModel);
    if (normalizedModel) {
      uniqueModels.add(normalizedModel);
    }
  });

  return [...uniqueModels];
};
