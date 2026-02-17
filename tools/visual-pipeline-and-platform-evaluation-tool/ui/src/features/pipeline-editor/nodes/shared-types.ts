export const INFERENCE_REGION_TYPES = ["roi-list", "full-frame"] as const;

export const DEVICE_TYPES = ["CPU", "GPU", "NPU"] as const;

export type DeviceType = (typeof DEVICE_TYPES)[number];

export type InferenceRegionType = (typeof INFERENCE_REGION_TYPES)[number];
