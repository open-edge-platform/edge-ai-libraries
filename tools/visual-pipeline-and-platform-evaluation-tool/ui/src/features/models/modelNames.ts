import type { Node } from "@/api/api.generated.ts";

const PAREN_DETAILS_SUFFIX_PATTERN = /\s*\([^()\n]*\)\s*$/;
const MODEL_PROC_SUFFIX_PATTERN = /\s*\[model-proc:[^\]\n]*\]\s*$/i;

export const normalizeModelDisplayName = (value: string): string => {
  let normalized = value;

  // Remove any number of trailing details like "(FP16)" and
  // "[model-proc: ...]" without relying on a backtracking-heavy pattern.
  while (true) {
    const next = normalized
      .replace(PAREN_DETAILS_SUFFIX_PATTERN, "")
      .replace(MODEL_PROC_SUFFIX_PATTERN, "");

    if (next === normalized) {
      break;
    }

    normalized = next;
  }

  return normalized.trim();
};

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
