import { Input } from "@/components/ui/input";
import {
  DEEP_SORT_PARAMS,
  DEEPSORT_CFG_KEY,
  composeDeepSortCfg,
  isDeepSortTrackingType,
  parseDeepSortCfg,
} from "./GVATrackNode.config.ts";

const FIELD_INPUT_CLASS = "h-8 w-full bg-background text-xs md:text-xs";

type GVATrackDeepSortFieldsProps = {
  nodeId: string;
  data: Record<string, unknown>;
  onDataChange: (updated: Record<string, unknown>) => void;
};

const GVATrackDeepSortFields = ({
  nodeId,
  data,
  onDataChange,
}: GVATrackDeepSortFieldsProps) => {
  if (!isDeepSortTrackingType(data["tracking-type"])) {
    return null;
  }

  const values = parseDeepSortCfg(data[DEEPSORT_CFG_KEY]);

  const handleParamChange = (paramKey: string, rawValue: string) => {
    const next = { ...values };
    const trimmed = rawValue.trim();
    if (trimmed === "") {
      delete next[paramKey];
    } else {
      next[paramKey] = trimmed;
    }

    const composed = composeDeepSortCfg(next);
    const updated = { ...data };
    if (composed) {
      updated[DEEPSORT_CFG_KEY] = composed;
    } else {
      delete updated[DEEPSORT_CFG_KEY];
    }
    onDataChange(updated);
  };

  return (
    <div className="space-y-3 mt-4">
      <h4 className="text-xs font-medium text-muted-foreground border-b border-border pb-1">
        Deep SORT Parameters:
      </h4>
      {DEEP_SORT_PARAMS.map((param) => {
        const currentValue = values[param.key] ?? "";
        return (
          <div
            key={`${nodeId}:deepsort:${param.key}`}
            className="border-l-2 border-brand-accent/20 pl-3"
          >
            <label className="text-xs font-medium text-muted-foreground block mb-1">
              {param.label}:
            </label>
            <div className="text-xs text-muted-foreground mb-1 italic">
              {param.description}
            </div>
            <Input
              type={param.type}
              value={currentValue}
              step={param.step}
              min={param.min}
              max={param.max}
              onChange={(e) => handleParamChange(param.key, e.target.value)}
              className={FIELD_INPUT_CLASS}
              placeholder={param.defaultValue || `Enter ${param.label}`}
            />
          </div>
        );
      })}
    </div>
  );
};

export default GVATrackDeepSortFields;
