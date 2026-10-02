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

export const tsamIngestionConfig: NodeConfig = {
  editableProperties: [
    {
      key: "host",
      label: "Host",
      type: "text",
      defaultValue: "",
      description: "Time Series Analytics ingestion service hostname",
    },
    {
      key: "port",
      label: "Port",
      type: "text",
      defaultValue: "5000",
      description: "Time Series Analytics ingestion service port",
    },
  ],
};
