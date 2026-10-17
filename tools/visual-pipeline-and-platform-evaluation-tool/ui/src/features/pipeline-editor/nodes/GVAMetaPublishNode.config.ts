export const GVA_METADATA_PUBLISH_METHODS = ["file", "mqtt"] as const;

export type GVAMetaPublishMethodType =
  (typeof GVA_METADATA_PUBLISH_METHODS)[number];

export const GVA_METADATA_PUBLISH_FILE_FORMATS = ["json", "json-lines"] as const;

export const gvaMetaPublishConfig = {
  editableProperties: [
    {
      key: "method",
      label: "Method",
      type: "select" as const,
      options: GVA_METADATA_PUBLISH_METHODS,
      defaultValue: "file",
      description: "Where inference metadata is published",
    },
    {
      key: "file-format",
      label: "File Format",
      type: "select" as const,
      options: GVA_METADATA_PUBLISH_FILE_FORMATS,
      defaultValue: "json-lines",
      description: "Structure of JSON objects in the file",
      visibleWhen: { key: "method", equals: ["file"] },
    },
    {
      key: "file-path",
      label: "File Path",
      type: "text" as const,
      defaultValue: "/dev/null",
      description: "Absolute path to the output file",
      visibleWhen: { key: "method", equals: ["file"] },
    },
    {
      key: "address",
      label: "Broker Address",
      type: "text" as const,
      // Matches the broker service in compose.mqtt.yml (make run MQTT=1).
      defaultValue: "mqtt-broker:1883",
      description:
        "Broker host and port as seen from the vippet container. 'localhost' is the container itself; use 'host.docker.internal:1883' for a broker on the host",
      required: true,
      visibleWhen: { key: "method", equals: ["mqtt"] },
    },
    {
      key: "topic",
      label: "Topic",
      type: "text" as const,
      defaultValue: "vippet/metadata",
      description: "Topic the metadata is published on",
      required: true,
      visibleWhen: { key: "method", equals: ["mqtt"] },
    },
    {
      key: "mqtt-client-id",
      label: "Client ID",
      type: "text" as const,
      defaultValue: "",
      description: "Unique MQTT client id. Generated when left empty",
      visibleWhen: { key: "method", equals: ["mqtt"] },
    },
    {
      key: "max-connect-attempts",
      label: "Max Connect Attempts",
      type: "number" as const,
      defaultValue: "1",
      description: "Failed connection attempts before the pipeline fails (1-10)",
      visibleWhen: { key: "method", equals: ["mqtt"] },
    },
    {
      key: "max-reconnect-interval",
      label: "Max Reconnect Interval",
      type: "number" as const,
      defaultValue: "30",
      description: "Upper bound in seconds between reconnect attempts (1-300)",
      visibleWhen: { key: "method", equals: ["mqtt"] },
    },
    {
      key: "mqtt-config",
      label: "Config File",
      type: "text" as const,
      defaultValue: "",
      description:
        "Path to a JSON file with credentials and TLS settings. Overrides the fields above",
      visibleWhen: { key: "method", equals: ["mqtt"] },
    },
  ],
};
