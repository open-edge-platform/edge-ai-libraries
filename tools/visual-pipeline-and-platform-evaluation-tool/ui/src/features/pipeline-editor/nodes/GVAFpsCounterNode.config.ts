type NodePropertyConfig = {
  key: string;
  label: string;
  type: "text" | "number" | "boolean" | "select" | "textarea";
  defaultValue?: unknown;
  description?: string;
  required?: boolean;
};

type NodeConfig = {
  editableProperties: NodePropertyConfig[];
};

export const gvaFpsCounterConfig: NodeConfig = {
  editableProperties: [
    {
      key: "starting-frame",
      label: "Starting frame",
      type: "number",
      defaultValue: 0,
      description:
        "Skip this many frames before starting to measure FPS so warm-up time is excluded",
    },
  ],
};
