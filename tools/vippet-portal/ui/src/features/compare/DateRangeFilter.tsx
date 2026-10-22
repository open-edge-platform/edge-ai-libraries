import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  EMPTY_DATE_RANGE,
  isDateRangeActive,
  type DateRange,
} from "@/lib/dateRange";
import { X } from "lucide-react";

type DateRangeFilterProps = {
  value: DateRange;
  onChange: (range: DateRange) => void;
  /** Keeps the input ids unique when several filter bars share a page. */
  idPrefix: string;
};

export const DateRangeFilter = ({
  value,
  onChange,
  idPrefix,
}: DateRangeFilterProps) => (
  <div className="flex items-end gap-2">
    <div className="grid gap-1.5">
      <Label htmlFor={`${idPrefix}-from`} className="text-xs font-normal">
        From
      </Label>
      <Input
        id={`${idPrefix}-from`}
        type="date"
        className="w-[10rem]"
        value={value.from}
        max={value.to || undefined}
        onChange={(event) => onChange({ ...value, from: event.target.value })}
      />
    </div>
    <div className="grid gap-1.5">
      <Label htmlFor={`${idPrefix}-to`} className="text-xs font-normal">
        To
      </Label>
      <Input
        id={`${idPrefix}-to`}
        type="date"
        className="w-[10rem]"
        value={value.to}
        min={value.from || undefined}
        onChange={(event) => onChange({ ...value, to: event.target.value })}
      />
    </div>
    {isDateRangeActive(value) ? (
      <Button
        variant="ghost"
        size="icon"
        aria-label="Clear date range"
        onClick={() => onChange(EMPTY_DATE_RANGE)}
      >
        <X className="h-4 w-4" />
      </Button>
    ) : null}
  </div>
);
