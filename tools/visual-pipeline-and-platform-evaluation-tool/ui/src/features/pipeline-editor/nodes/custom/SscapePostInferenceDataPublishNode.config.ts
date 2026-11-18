// SPDX-License-Identifier: Apache-2.0
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

export const SSCAPE_METADATA_POLICIES = [
  "detectionPolicy",
  "detection3DPolicy",
  "reidPolicy",
  "classificationPolicy",
  "ocrPolicy",
] as const;

export const sscapePostInferenceDataPublishConfig: NodeConfig = {
  editableProperties: [
    {
      key: "cameraid",
      label: "Camera ID",
      type: "text",
      defaultValue: "",
      description: "Camera identifier used in MQTT topics and the payload 'id'",
    },
    {
      key: "metadatagenpolicy",
      label: "Metadata policy",
      type: "select",
      options: SSCAPE_METADATA_POLICIES,
      defaultValue: "detectionPolicy",
      description: "Policy used to build the SceneScape metadata payload",
    },
    {
      key: "detection-labels",
      label: "Detection labels",
      type: "text",
      defaultValue: "",
      description:
        "Comma-separated allow-list of detection categories to publish. Empty publishes all",
    },
    {
      key: "mqtt-host",
      label: "MQTT host",
      type: "text",
      defaultValue: "",
      description:
        "MQTT broker hostname. Empty falls back to MQTT_HOST env var or 'broker.scenescape.intel.com'",
    },
    {
      key: "mqtt-port",
      label: "MQTT port",
      type: "text",
      defaultValue: "1883",
      description: "MQTT broker port (1 - 65535)",
    },
    {
      key: "publish-image",
      label: "Publish image",
      type: "boolean",
      defaultValue: false,
      description:
        "Publish an annotated JPEG frame on scenescape/image/camera/<cameraid> each frame",
    },
    {
      key: "annotate-track-ids",
      label: "Annotate track IDs",
      type: "boolean",
      defaultValue: false,
      description: "Add Analytics GID labels to published images",
    },
    {
      key: "track-topic",
      label: "Track topic",
      type: "text",
      defaultValue: "scenescape/regulated/scene/+",
      description: "Analytics regulated scene topic filter",
    },
    {
      key: "track-wait-ms",
      label: "Track wait (ms)",
      type: "text",
      defaultValue: "300",
      description:
        "Maximum wait for a track snapshot in milliseconds (0 - 2000)",
    },
    {
      key: "track-max-age-ms",
      label: "Track max age (ms)",
      type: "text",
      defaultValue: "1000",
      description: "Maximum timestamp difference in milliseconds (0 - 5000)",
    },
  ],
};
