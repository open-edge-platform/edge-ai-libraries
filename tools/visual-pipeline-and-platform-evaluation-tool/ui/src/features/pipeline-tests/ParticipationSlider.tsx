import { Slider } from "@/components/ui/slider.tsx";

interface ParticipationSliderProps {
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  disabled?: boolean;
}

export const ParticipationSlider = ({
  value,
  onChange,
  min = 0,
  max = 100,
  disabled = false,
}: ParticipationSliderProps) => {
  return (
    <div
      className={`flex items-center gap-3 ${disabled ? "opacity-60 cursor-not-allowed" : ""}`}
    >
      <span className="text-sm text-neutral-500 min-w-[1rem] text-center font-semibold">
        {min}
      </span>
      <Slider
        value={[value]}
        onValueChange={(val) => {
          if (!disabled) {
            onChange(val[0]);
          }
        }}
        min={min}
        max={max}
        step={1}
        className="flex-1"
        disabled={disabled}
      />
      <span className="text-sm text-neutral-500 min-w-[1.5rem] text-center font-semibold">
        {max}
      </span>
      <input
        type="number"
        value={value}
        onChange={(e) => {
          if (disabled) return;
          const newValue = parseInt(e.target.value, 10);
          if (!isNaN(newValue) && newValue >= min && newValue <= max) {
            onChange(newValue);
          }
        }}
        min={min}
        max={max}
        className="w-[4rem] px-3 py-1.5 text-sm font-bold border border-border bg-background text-foreground dark:border-border/70 dark:bg-muted/60 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring/50"
        style={{ textAlign: "center" }}
        disabled={disabled}
      />
      <span className="text-sm text-neutral-500 font-semibold">%</span>
    </div>
  );
};
