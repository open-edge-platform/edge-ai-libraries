import type { Model, Node } from "@/api/api.generated.ts";

// Variant labels are "<model> (<precision>)" plus an optional "[model-proc: ...]";
// only that trailing group is stripped, model names may contain parentheses.
const MODEL_DETAILS_SUFFIX_PATTERN = /\s*\([^()]*\)(?:\s*\[[^\]]*\])?\s*$/;

export const isGatedModel = (model: Pick<Model, "gated">): boolean =>
  Boolean(model.gated) && model.gated !== "false";

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
