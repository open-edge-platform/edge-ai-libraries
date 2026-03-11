import { useMemo } from "react";
import { type Pipeline } from "@/api/api.generated";

const TAG_COLORS = [
  "electric-aqua",
  "electric-cobalt",
  "electric-coral",
  "electric-daisy",
  "electric-geode",
  "electric-moss",
  "electric-rust",
] as const;

export type TagColor = (typeof TAG_COLORS)[number];

/**
 * Hook to compute tag colors and available tags from pipelines.
 * Returns a map of tag names to their assigned colors and an array of available tags.
 */
export const usePipelineTagColors = (pipelines: Pipeline[] | undefined) => {
  const tagColorMap = useMemo(() => {
    if (!pipelines) return new Map<string, TagColor>();

    const uniqueTags = Array.from(
      new Set(pipelines.flatMap((p) => p.tags ?? [])),
    ).sort();

    return new Map<string, TagColor>(
      uniqueTags.map((tag, index) => [
        tag,
        TAG_COLORS[index % TAG_COLORS.length],
      ]),
    );
  }, [pipelines]);

  const availableTags = useMemo(
    () => Array.from(tagColorMap.keys()),
    [tagColorMap],
  );

  return { tagColorMap, availableTags };
};
