type NodePropertyConfig = {
  key: string;
  label: string;
  type: "text" | "number" | "boolean" | "select" | "textarea";
  defaultValue?: unknown;
  options?: string[] | readonly string[];
  description?: string;
  required?: boolean;
};

type NodeConfig = {
  editableProperties: NodePropertyConfig[];
};

export const tsamOutputConfig: NodeConfig = {
  editableProperties: [
    {
      key: "method",
      label: "Method",
      type: "select",
      options: ["rest", "mqtt", "kafka"],
      defaultValue: "rest",
      description: "Transport used to publish the output",
    },
    {
      key: "endpoint",
      label: "Endpoint",
      type: "text",
      defaultValue: "",
      description: "Destination endpoint (REST path, broker URL, etc.)",
    },
    {
      key: "topic",
      label: "Topic",
      type: "text",
      defaultValue: "",
      description: "Topic/channel name to publish the output under",
    },
  ],
};
