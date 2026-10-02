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

export const queueConfig: NodeConfig = {
  editableProperties: [
    {
      key: "name",
      label: "Name",
      type: "text",
      defaultValue: "",
      description: "Instance name of the element",
    },
    {
      key: "leaky",
      label: "Leaky",
      type: "select",
      options: ["no", "upstream", "downstream"],
      defaultValue: "no",
      description:
        "Where to drop buffers when the queue is full ('upstream' drops old, 'downstream' drops new)",
    },
    {
      key: "max-size-buffers",
      label: "Max size buffers",
      type: "number",
      defaultValue: 200,
      description: "Maximum number of buffers to hold in the queue",
    },
    {
      key: "flush-on-eos",
      label: "Flush on EOS",
      type: "boolean",
      defaultValue: false,
      description:
        "Discard any remaining data in the queue when end-of-stream is received",
    },
  ],
};
