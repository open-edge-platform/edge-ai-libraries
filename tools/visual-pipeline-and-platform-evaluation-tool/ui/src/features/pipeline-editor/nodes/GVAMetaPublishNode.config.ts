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

export const gvaMetaPublishConfig: NodeConfig = {
  editableProperties: [
    {
      key: "method",
      label: "Method",
      type: "select",
      options: ["file", "mqtt", "kafka"],
      defaultValue: "file",
      description: "Target backend to publish inference metadata to",
    },
    {
      key: "file-format",
      label: "File format",
      type: "select",
      options: ["json", "json-lines"],
      defaultValue: "json",
      description: "Output file format when method is 'file'",
    },
    {
      key: "file-path",
      label: "File path",
      type: "text",
      defaultValue: "",
      description: "Output file path when method is 'file'",
    },
  ],
};
