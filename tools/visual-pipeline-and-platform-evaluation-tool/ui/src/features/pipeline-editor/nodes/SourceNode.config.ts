// SPDX-License-Identifier: Apache-2.0

type NodePropertyConfig = {
  key: string;
  label: string;
  type: "text" | "number" | "boolean" | "select" | "textarea";
  defaultValue?: unknown;
  options?: string[] | readonly string[];
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
      options: ["file", "camera"],
      defaultValue: "file",
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
