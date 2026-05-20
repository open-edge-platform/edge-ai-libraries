type SelectOptionConfig = string | readonly [string, string];

type NodePropertyConfig = {
  key: string;
  label: string;
  type: "text" | "number" | "boolean" | "select" | "textarea";
  defaultValue?: unknown;
  options?: SelectOptionConfig[] | readonly SelectOptionConfig[];
  description?: string;
  required?: boolean;
  params?: { [key: string]: string };
};

type NodeConfig = {
  editableProperties: NodePropertyConfig[];
};

export const sourceNodeConfig: NodeConfig = {
  editableProperties: [
    {
      key: "kind",
      label: "Source Type",
      type: "select",
      options: ["video", ["image_set", "Image Set"], "camera"],
      defaultValue: "video",
      description: "Select the input source type",
    },
    {
      key: "source",
      label: "Source",
      type: "select",
      description: "Select the input source",
    },
  ],
};
