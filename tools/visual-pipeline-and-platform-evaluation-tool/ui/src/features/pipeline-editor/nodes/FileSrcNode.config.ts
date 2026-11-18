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

export const fileSrcConfig: NodeConfig = {
  editableProperties: [
    {
      key: "location",
      label: "Location",
      type: "text",
      defaultValue: "",
      description: "Path to the input file",
    },
  ],
};
