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

export const mp4MuxConfig: NodeConfig = {
  editableProperties: [
    {
      key: "fragment-duration",
      label: "Fragment duration",
      type: "number",
      defaultValue: 0,
      description:
        "Fragment length in milliseconds when writing a fragmented MP4 (0 disables fragmentation)",
    },
  ],
};
