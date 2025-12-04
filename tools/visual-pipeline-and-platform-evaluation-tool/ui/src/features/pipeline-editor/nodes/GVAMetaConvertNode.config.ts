export const GVA_METADATA_CONVERT_FORMATS = ["json", "dump-detection"] as const;

export type GVAMetaConvertFormatType =
  (typeof GVA_METADATA_CONVERT_FORMATS)[number];

export const gvaMetaConvertConfig = {
  editableProperties: [
    {
      key: "name",
      label: "Name",
      type: "text" as const,
      defaultValue: "",
      description: "Element name",
    },
    {
      key: "qos",
      label: "QoS",
      type: "boolean" as const,
      defaultValue: false,
      description: "Handle quality-of-service events",
    },
    {
      key: "timestamp-utc",
      label: "Timestamp UTC",
      type: "boolean" as const,
      defaultValue: false,
      description: "Use UTC timestamps",
    },
    {
      key: "format",
      label: "Format",
      type: "select" as const,
      options: GVA_METADATA_CONVERT_FORMATS,
      defaultValue: "json",
      description: "Output format",
    },
    {
      key: "json-indent",
      label: "JSON Indent",
      type: "number" as const,
      defaultValue: 4,
      description: "JSON indentation level",
    },
    {
      key: "add-empty-results",
      label: "Add Empty Results",
      type: "boolean" as const,
      defaultValue: false,
      description: "Include empty detection results",
    },
    {
      key: "add-tensor-data",
      label: "Add Tensor Data",
      type: "boolean" as const,
      defaultValue: false,
      description: "Include raw tensor data",
    },
  ],
};
