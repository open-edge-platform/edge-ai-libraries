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

export const dataSrcConfig: NodeConfig = {
  editableProperties: [
    {
      key: "location",
      label: "Location",
      type: "text",
      defaultValue: "",
      description: "Path to the input data file",
    },
    {
      key: "topic",
      label: "Topic",
      type: "text",
      defaultValue: "",
      description: "Topic name used by downstream components to route the data",
    },
  ],
};
