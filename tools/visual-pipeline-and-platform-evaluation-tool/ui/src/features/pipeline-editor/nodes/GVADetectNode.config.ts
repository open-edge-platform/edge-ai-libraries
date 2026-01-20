import {
  DEVICE_TYPES,
  INFERENCE_REGION_TYPES,
} from "@/features/pipeline-editor/nodes/shared-types.ts";

export const gvaDetectConfig = {
  editableProperties: [
    {
      key: "model",
      label: "Model",
      type: "select" as const,
      defaultValue: "",
      description: "Path to inference model network file",
      params: {
        filter: "detection",
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
      key: "batch-size",
      label: "Batch size",
      type: "text" as const,
      defaultValue: "0",
      description: "Number of frames batched together for a single inference",
    },
    {
      key: "nireq",
      label: "Nireq",
      type: "text" as const,
      defaultValue: "0",
      description: "Number of inference requests",
    },
    {
      key: "inference-interval",
      label: "Inference interval",
      type: "text" as const,
      defaultValue: "1",
      description:
        "Interval between inference requests. An interval of N performs inference on every Nth frame",
    },
    {
      key: "inference-region",
      label: "Inference region",
      type: "select" as const,
      options: INFERENCE_REGION_TYPES,
      defaultValue: "",
      description:
        "Identifier responsible for the region on which inference will be performed",
    },
    {
      key: "object-class",
      label: "Object class",
      type: "text" as const,
      defaultValue: "",
      description:
        "Filter for Region of Interest class label on this element input",
    },
  ],
};
