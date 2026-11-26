import { useTheme } from "next-themes";
import type { RefObject } from "react";
import { useAppSelector } from "@/store/hooks";
import { selectPipelines } from "@/store/reducers/pipelines";
import {
  Combobox,
  ComboboxChip,
  ComboboxChips,
  ComboboxChipsInput,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxItem,
  ComboboxList,
} from "@/components/ui/combobox.tsx";
import { usePipelineTagColors } from "@/hooks/usePipelineTagColors";

type PipelineTagsComboboxProps = {
  value: string[];
  onChange: (tags: string[]) => void;
  portalContainer?: RefObject<HTMLElement | ShadowRoot | null>;
};

const dedupeTagsIgnoringCase = (tags: string[]): string[] => {
  const seen = new Set<string>();
  return tags.filter((tag) => {
    const key = tag.toLowerCase();
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
};

export const PipelineTagsCombobox = ({
  value,
  onChange,
  portalContainer,
}: PipelineTagsComboboxProps) => {
  const { theme } = useTheme();
  const pipelines = useAppSelector(selectPipelines);
  const { tagColorMap, availableTags } = usePipelineTagColors(pipelines);

  return (
    <Combobox
      value={value}
      onValueChange={(tags: string[]) => onChange(dedupeTagsIgnoringCase(tags))}
      multiple
    >
      <ComboboxChips>
        {value.map((tag) => {
          const color = tagColorMap.get(tag);
          return (
            <ComboboxChip
              key={tag}
              className="rounded border-0"
              style={
                color
                  ? {
                      backgroundColor:
                        theme === "dark"
                          ? `var(--${color})`
                          : `color-mix(in oklch, var(--${color}) 50%, white)`,
                    }
                  : undefined
              }
            >
              {tag}
            </ComboboxChip>
          );
        })}
        <ComboboxChipsInput
          placeholder="Add tags..."
          onKeyDown={(e) => {
            if (e.key === "Enter" && e.currentTarget.value) {
              e.preventDefault();
              const newTag = e.currentTarget.value.trim();
              if (newTag) {
                // Reuse the casing of an existing tag, e.g. "dup" -> "DUP".
                const existingTag = availableTags.find(
                  (tag) => tag.toLowerCase() === newTag.toLowerCase(),
                );
                onChange(
                  dedupeTagsIgnoringCase([...value, existingTag ?? newTag]),
                );
                e.currentTarget.value = "";
              }
            }
          }}
        />
      </ComboboxChips>
      <ComboboxContent portalContainer={portalContainer}>
        <ComboboxList>
          {availableTags.length > 0 ? (
            availableTags.map((tag) => (
              <ComboboxItem key={tag} value={tag}>
                {tag}
              </ComboboxItem>
            ))
          ) : (
            <ComboboxEmpty>No tags available.</ComboboxEmpty>
          )}
        </ComboboxList>
      </ComboboxContent>
    </Combobox>
  );
};
