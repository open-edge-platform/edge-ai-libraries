import { Input } from "@/components/ui/input";
import {
  DEEP_SORT_PARAMS,
  DEEP_SORT_TRACKING_TYPE,
  DEEPSORT_CFG_KEY,
} from "./GVATrackNode.config.ts";

const FIELD_INPUT_CLASS = "h-8 w-full bg-background text-xs md:text-xs";

const isDeepSortTrackingType = (value: unknown): boolean =>
  String(value ?? "")
    .trim()
    .toLowerCase() === DEEP_SORT_TRACKING_TYPE;

// Parse a stored `deepsort-trck-cfg` value (e.g. `"max_age=60,object_class=person"`)
// into `{ paramKey: value }`. Surrounding quotes are stripped; unknown keys are
// preserved so they round-trip through the UI.
const parseDeepSortCfg = (raw: unknown): Record<string, string> => {
  const text = String(raw ?? "")
    .trim()
    .replace(/^["'](.*)["']$/, "$1");
  if (!text) return {};

  const result: Record<string, string> = {};
  for (const segment of text.split(",")) {
    const eqIndex = segment.indexOf("=");
    if (eqIndex <= 0) continue;
    const key = segment.slice(0, eqIndex).trim();
    const value = segment.slice(eqIndex + 1).trim();
    if (key) result[key] = value;
  }
  return result;
};

// Compose a `deepsort-trck-cfg` value from the UI param map. Declared params
// come first in the canonical order, then any unknown keys preserved from
// parse. Empty values are dropped (fall back to DLStreamer's defaults);
// returns `""` when nothing is set, so the caller can drop the property.
const composeDeepSortCfg = (values: Record<string, string>): string => {
  const knownKeys = new Set(DEEP_SORT_PARAMS.map((p) => p.key));
  const orderedKeys = [
    ...DEEP_SORT_PARAMS.map((p) => p.key),
    ...Object.keys(values).filter((k) => !knownKeys.has(k)),
  ];
  const pairs = orderedKeys
    .map((k) => [k, values[k]?.trim() ?? ""] as const)
    .filter(([, v]) => v !== "")
    .map(([k, v]) => `${k}=${v}`);
  return pairs.length ? `"${pairs.join(",")}"` : "";
};

type GVATrackNodeDeepSortParamsProps = {
  nodeId: string;
  data: Record<string, unknown>;
  onDataChange: (updated: Record<string, unknown>) => void;
};

const GVATrackNodeDeepSortParams = ({
  nodeId,
  data,
  onDataChange,
}: GVATrackNodeDeepSortParamsProps) => {
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

export default GVATrackNodeDeepSortParams;
