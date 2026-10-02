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

export const proximityTriggerConfig: NodeConfig = {
  editableProperties: [
    {
      key: "class-a",
      label: "Class A",
      type: "text",
      defaultValue: "",
      description: "First object class label to monitor (e.g. 'person')",
    },
    {
      key: "class-b",
      label: "Class B",
      type: "text",
      defaultValue: "",
      description: "Second object class label to monitor (e.g. 'bicycle')",
    },
    {
      key: "distance",
      label: "Distance",
      type: "number",
      defaultValue: 30,
      description:
        "Maximum center-to-center distance in pixels to consider the two objects as being in proximity",
    },
    {
      key: "frames",
      label: "Frames",
      type: "number",
      defaultValue: 10,
      description:
        "Number of consecutive frames the proximity condition must hold before a trigger frame is forwarded",
    },
  ],
};
