export const GVA_TRACKING_TYPES = [
  "zero-term",
  "short-term-imageless",
  "zero-term-imageless",
  "deep-sort",
] as const;

export const DEEP_SORT_TRACKING_TYPE = "deep-sort";
export const DEEPSORT_CFG_KEY = "deepsort-trck-cfg";

export type DeepSortParam = {
  key: string;
  label: string;
  type: "number" | "text";
  defaultValue: string;
  description: string;
  step?: number;
  min?: number;
  max?: number;
};

// Deep SORT tracker parameters exposed to the UI. These are packed into the
// single `deepsort-trck-cfg="k=v,k=v,..."` gvatrack property at emit time.
// See https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/dlstreamer/dev_guide/object_tracking.html
export const DEEP_SORT_PARAMS: readonly DeepSortParam[] = [
  {
    key: "max_iou_distance",
    label: "Max IoU distance",
    type: "number",
    defaultValue: "0.7",
    step: 0.05,
    min: 0,
    max: 1,
    description: "Max IoU for matching (lower = stricter)",
  },
  {
    key: "max_age",
    label: "Max age",
    type: "number",
    defaultValue: "30",
    step: 1,
    min: 1,
    description: "Frames a track survives without detection",
  },
  {
    key: "n_init",
    label: "N init",
    type: "number",
    defaultValue: "3",
    step: 1,
    min: 1,
    description: "Detections needed to confirm a track",
  },
  {
    key: "max_cosine_distance",
    label: "Max cosine distance",
    type: "number",
    defaultValue: "0.2",
    step: 0.05,
    min: 0,
    max: 1,
    description: "Max appearance distance (lower = stricter)",
  },
  {
    key: "nn_budget",
    label: "NN budget",
    type: "number",
    defaultValue: "100",
    step: 1,
    min: 0,
    description: "Features stored per track (0 = unlimited)",
  },
  {
    key: "object_class",
    label: "Object class",
    type: "text",
    defaultValue: "",
    description: "Only track this class",
  },
  {
    key: "reid_max_age",
    label: "Re-ID max age",
    type: "number",
    defaultValue: "0",
    step: 1,
    min: 0,
    description: "Frames to keep tracks for re-ID (0 = off)",
  },
] as const;

export const gvaTrackConfig = {
  editableProperties: [
    {
      key: "tracking-type",
      label: "Tracking type",
      type: "select" as const,
      options: GVA_TRACKING_TYPES,
      defaultValue: GVA_TRACKING_TYPES[0],
      description:
        "Tracking algorithm used to identify the same object in multiple frames",
    },
  ],
};

export const isDeepSortTrackingType = (value: unknown): boolean =>
  String(value ?? "")
    .trim()
    .toLowerCase() === DEEP_SORT_TRACKING_TYPE;

// Parse a stored `deepsort-trck-cfg` value (e.g. `"max_age=60,object_class=person"`)
// into `{ paramKey: value }`. Surrounding quotes are stripped; unknown keys are
// preserved so they round-trip through the UI.
export const parseDeepSortCfg = (raw: unknown): Record<string, string> => {
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
export const composeDeepSortCfg = (values: Record<string, string>): string => {
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
