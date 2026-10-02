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

export const teeConfig: NodeConfig = {
  editableProperties: [
    {
      key: "name",
      label: "Name",
      type: "text",
      defaultValue: "",
      description: "Instance name used to reference tee branches",
    },
  ],
};
