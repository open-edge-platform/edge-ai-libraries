import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { metricLabel } from "@/lib/format";

export const MetricSelect = ({
  metrics,
  value,
  onChange,
}: {
  metrics: string[];
  value: string;
  onChange: (metric: string) => void;
}) => (
  <Select value={value} onValueChange={onChange}>
    <SelectTrigger className="w-[15rem]">
      <SelectValue placeholder="Metric" />
    </SelectTrigger>
    <SelectContent>
      {metrics.map(metric => (
        <SelectItem key={metric} value={metric}>
          {metricLabel(metric)}
        </SelectItem>
      ))}
    </SelectContent>
  </Select>
);
