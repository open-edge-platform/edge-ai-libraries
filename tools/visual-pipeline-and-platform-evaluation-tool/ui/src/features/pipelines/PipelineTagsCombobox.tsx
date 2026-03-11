import { useTheme } from "next-themes";
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
};

export const PipelineTagsCombobox = ({
  value,
  onChange,
}: PipelineTagsComboboxProps) => {
  const { theme } = useTheme();
  const pipelines = useAppSelector(selectPipelines);
  const { tagColorMap, availableTags } = usePipelineTagColors(pipelines);

  return (
    <Combobox value={value} onValueChange={onChange} multiple>
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
              if (newTag && !value.includes(newTag)) {
                onChange([...value, newTag]);
                e.currentTarget.value = "";
              }
            }
          }}
        />
      </ComboboxChips>
      <ComboboxContent>
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
