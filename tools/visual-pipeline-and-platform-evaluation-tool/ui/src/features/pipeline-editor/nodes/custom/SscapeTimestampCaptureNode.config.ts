// SPDX-License-Identifier: Apache-2.0
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

export const sscapeTimestampCaptureConfig: NodeConfig = {
  editableProperties: [
    {
      key: "ntp-server",
      label: "NTP server",
      type: "text",
      defaultValue: "",
      description:
        "Hostname of an NTP server used to periodically correct the system clock offset. Empty disables NTP correction",
    },
    {
      key: "use-frame-ntp-timestamp",
      label: "Use frame NTP timestamp",
      type: "boolean",
      defaultValue: false,
      description:
        "Use the NTP timestamp attached by rtspsrc (add-reference-timestamp-meta=true); falls back to post-decode system time",
    },
    {
      key: "fps-alpha",
      label: "FPS smoothing factor",
      type: "text",
      defaultValue: "0.75",
      description:
        "Weight of the previous FPS estimate in the running average (0.0 - 1.0)",
    },
    {
      key: "fps-calc-interval",
      label: "FPS calculation interval",
      type: "text",
      defaultValue: "1.0",
      description:
        "Minimum time in seconds between FPS recomputations (0.01 - 60.0)",
    },
  ],
};
