export const gvaMotionDetectConfig = {
  editableProperties: [
    {
      key: "name",
      label: "Name",
      type: "text" as const,
      defaultValue: "",
      description: "Instance name of the element",
    },
    {
      key: "block-size",
      label: "Block size",
      type: "text" as const,
      defaultValue: "32",
      description: "Block size in pixels for motion grid analysis",
    },
    {
      key: "motion-threshold",
      label: "Motion threshold",
      type: "text" as const,
      defaultValue: "5.0",
      description:
        "Percentage of blocks that must change to consider a frame as having motion",
    },
    {
      key: "min-persistence",
      label: "Min persistence",
      type: "text" as const,
      defaultValue: "5",
      description:
        "Minimum number of consecutive frames an object must be tracked before it is reported",
    },
    {
      key: "max-miss",
      label: "Max miss",
      type: "text" as const,
      defaultValue: "5",
      description:
        "Maximum number of consecutive frames an object can be missing before tracking is lost",
    },
    {
      key: "iou-threshold",
      label: "IoU threshold",
      type: "text" as const,
      defaultValue: "0.3",
      description:
        "Intersection over Union threshold for matching detected regions across frames",
    },
    {
      key: "smooth-alpha",
      label: "Smooth alpha",
      type: "text" as const,
      defaultValue: "0.5",
      description:
        "Exponential moving average smoothing factor for bounding box coordinates",
    },
    {
      key: "confirm-frames",
      label: "Confirm frames",
      type: "text" as const,
      defaultValue: "3",
      description:
        "Number of frames required to confirm a new detection before it becomes a tracked object",
    },
    {
      key: "pixel-diff-threshold",
      label: "Pixel diff threshold",
      type: "text" as const,
      defaultValue: "25",
      description:
        "Minimum pixel intensity difference to consider a pixel as changed",
    },
    {
      key: "min-rel-area",
      label: "Min relative area",
      type: "text" as const,
      defaultValue: "0.005",
      description:
        "Minimum relative area (fraction of frame) for a detected motion region to be reported",
    },
  ],
};
