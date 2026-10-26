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

export const multiFileSinkConfig: NodeConfig = {
  editableProperties: [
    {
      key: "location",
      label: "Location",
      type: "text",
      defaultValue: "",
      description:
        "Output file path pattern. Use a printf-style integer specifier (e.g. '%05d') for sequential numbering",
    },
  ],
};
