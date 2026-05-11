import { DEVICE_TYPES } from "@/features/pipeline-editor/nodes/shared-types.ts";

export const gvaGenAIConfig = {
  editableProperties: [
    {
      key: "model",
      label: "Model",
      type: "select" as const,
      defaultValue: "",
      description: "OpenVINO GenAI model",
      params: {
        filter: "genai",
      },
    },
    {
      key: "device",
      label: "Device",
      type: "select" as const,
      options: DEVICE_TYPES,
      description: "Target device for inference",
    },
    {
      key: "frame-rate",
      label: "Frame rate",
      type: "text" as const,
      defaultValue: "1",
      description: "Frame sampling rate (fps)",
    },
    {
      key: "chunk-size",
      label: "Chunk size",
      type: "text" as const,
      defaultValue: "4",
      description: "Number of frames in one inference chunk",
    },
    {
      key: "prompt",
      label: "Prompt",
      type: "text" as const,
      defaultValue: "Summarize this video in one sentence.",
      description: "Text prompt sent to the vision-language model",
    },
    {
      key: "generation-config",
      label: "Generation config",
      type: "text" as const,
      defaultValue: "max_new_tokens=64",
      description: "OpenVINO GenAI generation parameters (e.g. max_new_tokens=64)",
    },
    {
      key: "metrics",
      label: "Metrics",
      type: "select" as const,
      options: ["false", "true"],
      defaultValue: "false",
      description: "Include performance metrics in JSON output",
    },
  ],
};
