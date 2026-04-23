// SPDX-License-Identifier: Apache-2.0
export type PipelineNodeRoleClasses = {
  color: string;
  border: string;
  surface: string;
  icon: string;
  title: string;
  handle: string;
};

const NODE_CLASSES = {
  border: "border-l-node-border",
  surface: "bg-node-surface",
  icon: "text-node-icon",
  title: "text-node-title",
  handle: "bg-node-handle!",
} as const;

export const PIPELINE_NODE_ROLE_CLASSES = {
  source: { color: "node-sky", ...NODE_CLASSES },
  buffer: { color: "node-chart-blue", ...NODE_CLASSES },
  parse: { color: "node-amethyst", ...NODE_CLASSES },
  decode: { color: "node-sky", ...NODE_CLASSES },
  demux: { color: "node-indigo", ...NODE_CLASSES },
  encode: { color: "node-cobalt", ...NODE_CLASSES },
  transform: { color: "node-periwinkle", ...NODE_CLASSES },
  media: { color: "node-steel", ...NODE_CLASSES },
  mux: { color: "node-geode", ...NODE_CLASSES },
  sink: { color: "node-neutral", ...NODE_CLASSES },
  counter: { color: "node-orchid", ...NODE_CLASSES },
  watermark: { color: "node-amethyst", ...NODE_CLASSES },
  metadata: { color: "node-cerulean", ...NODE_CLASSES },
  metadataPublish: { color: "node-indigo", ...NODE_CLASSES },
  aiDetect: { color: "node-cobalt", ...NODE_CLASSES },
  aiClassify: { color: "node-geode", ...NODE_CLASSES },
  aiTrack: { color: "node-lavender", ...NODE_CLASSES },
} as const satisfies Record<string, PipelineNodeRoleClasses>;
