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

export const tsamUdfConfig: NodeConfig = {
  editableProperties: [
    {
      key: "udf-name",
      label: "UDF name",
      type: "text",
      defaultValue: "",
      description: "User-defined function (UDF) identifier to run",
    },
    {
      key: "udf-model",
      label: "UDF model",
      type: "text",
      defaultValue: "",
      description: "Pickled model file used by the UDF for inference",
    },
    {
      key: "device",
      label: "Device",
      type: "text",
      defaultValue: "cpu",
      description: "Target device for UDF execution",
    },
  ],
};
