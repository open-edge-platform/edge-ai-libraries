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

export const splitMuxSinkConfig: NodeConfig = {
  editableProperties: [
    {
      key: "location",
      label: "Location",
      type: "text",
      defaultValue: "",
      description: "Output file path pattern used for each split segment",
    },
  ],
};
