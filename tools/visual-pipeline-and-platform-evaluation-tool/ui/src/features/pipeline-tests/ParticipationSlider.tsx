import { useState } from "react";
import { Slider } from "@/components/ui/slider.tsx";
import { cn } from "@/lib/utils.ts";

interface ParticipationSliderProps {
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  disabled?: boolean;
  valueInputClassName?: string;
}

export const ParticipationSlider = ({
  value,
  onChange,
  min = 0,
  max = 100,
  disabled = false,
  valueInputClassName,
}: ParticipationSliderProps) => {
  const [draft, setDraft] = useState<string | null>(null);
  return (
    <div
      className={cn(
        "flex items-center gap-3",
        disabled && "opacity-60 cursor-not-allowed",
      )}
    >
      <span className="text-sm text-muted-foreground min-w-[1rem] text-center font-semibold">
        {min}
      </span>
      <Slider
        value={[value]}
        onValueChange={(val) => {
          if (!disabled) {
            setDraft(null);
            onChange(val[0]);
          }
        }}
        min={min}
        max={max}
        step={1}
        className="flex-1"
        disabled={disabled}
      />
      <span className="text-sm text-muted-foreground min-w-[1.5rem] text-center font-semibold">
        {max}
      </span>
      <input
        type="number"
        value={draft ?? value}
        onChange={(e) => {
          if (disabled) return;
          setDraft(e.target.value);
          const newValue = e.target.valueAsNumber;
          if (
            Number.isInteger(newValue) &&
            newValue >= min &&
            newValue <= max
          ) {
            onChange(newValue);
          }
        }}
        onBlur={() => setDraft(null)}
        min={min}
        max={max}
        className={cn(
          "w-[4rem] px-3 py-1.5 text-sm font-bold border border-border bg-background text-foreground dark:border-border/70 dark:bg-muted/60 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring/50",
          valueInputClassName,
        )}
        style={{ textAlign: "center" }}
        disabled={disabled}
      />
      <span className="text-sm text-muted-foreground font-semibold">%</span>
    </div>
  );
};
