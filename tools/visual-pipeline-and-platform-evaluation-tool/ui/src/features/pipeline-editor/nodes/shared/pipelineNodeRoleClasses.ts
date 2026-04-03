// SPDX-License-Identifier: Apache-2.0
export type PipelineNodeRoleClasses = {
  border: string;
  surface: string;
  icon: string;
  title: string;
  handle: string;
};

export const PIPELINE_NODE_ROLE_CLASSES = {
  source: {
    border: "border-l-node-role-source-border",
    surface: "bg-node-role-source-surface",
    icon: "text-node-role-source-icon",
    title: "text-node-role-source-title",
    handle: "bg-node-role-source-handle!",
  },
  buffer: {
    border: "border-l-node-role-buffer-border",
    surface: "bg-node-role-buffer-surface",
    icon: "text-node-role-buffer-icon",
    title: "text-node-role-buffer-title",
    handle: "bg-node-role-buffer-handle!",
  },
  parse: {
    border: "border-l-node-role-parse-border",
    surface: "bg-node-role-parse-surface",
    icon: "text-node-role-parse-icon",
    title: "text-node-role-parse-title",
    handle: "bg-node-role-parse-handle!",
  },
  decode: {
    border: "border-l-node-role-decode-border",
    surface: "bg-node-role-decode-surface",
    icon: "text-node-role-decode-icon",
    title: "text-node-role-decode-title",
    handle: "bg-node-role-decode-handle!",
  },
  demux: {
    border: "border-l-node-role-demux-border",
    surface: "bg-node-role-demux-surface",
    icon: "text-node-role-demux-icon",
    title: "text-node-role-demux-title",
    handle: "bg-node-role-demux-handle!",
  },
  encode: {
    border: "border-l-node-role-encode-border",
    surface: "bg-node-role-encode-surface",
    icon: "text-node-role-encode-icon",
    title: "text-node-role-encode-title",
    handle: "bg-node-role-encode-handle!",
  },
  transform: {
    border: "border-l-node-role-transform-border",
    surface: "bg-node-role-transform-surface",
    icon: "text-node-role-transform-icon",
    title: "text-node-role-transform-title",
    handle: "bg-node-role-transform-handle!",
  },
  media: {
    border: "border-l-node-role-media-border",
    surface: "bg-node-role-media-surface",
    icon: "text-node-role-media-icon",
    title: "text-node-role-media-title",
    handle: "bg-node-role-media-handle!",
  },
  mux: {
    border: "border-l-node-role-mux-border",
    surface: "bg-node-role-mux-surface",
    icon: "text-node-role-mux-icon",
    title: "text-node-role-mux-title",
    handle: "bg-node-role-mux-handle!",
  },
  sink: {
    border: "border-l-node-role-sink-border",
    surface: "bg-node-role-sink-surface",
    icon: "text-node-role-sink-icon",
    title: "text-node-role-sink-title",
    handle: "bg-node-role-sink-handle!",
  },
  counter: {
    border: "border-l-node-role-counter-border",
    surface: "bg-node-role-counter-surface",
    icon: "text-node-role-counter-icon",
    title: "text-node-role-counter-title",
    handle: "bg-node-role-counter-handle!",
  },
  watermark: {
    border: "border-l-node-role-watermark-border",
    surface: "bg-node-role-watermark-surface",
    icon: "text-node-role-watermark-icon",
    title: "text-node-role-watermark-title",
    handle: "bg-node-role-watermark-handle!",
  },
  metadata: {
    border: "border-l-node-role-metadata-border",
    surface: "bg-node-role-metadata-surface",
    icon: "text-node-role-metadata-icon",
    title: "text-node-role-metadata-title",
    handle: "bg-node-role-metadata-handle!",
  },
  metadataPublish: {
    border: "border-l-node-role-metadata-publish-border",
    surface: "bg-node-role-metadata-publish-surface",
    icon: "text-node-role-metadata-publish-icon",
    title: "text-node-role-metadata-publish-title",
    handle: "bg-node-role-metadata-publish-handle!",
  },
  aiDetect: {
    border: "border-l-node-role-ai-detect-border",
    surface: "bg-node-role-ai-detect-surface",
    icon: "text-node-role-ai-detect-icon",
    title: "text-node-role-ai-detect-title",
    handle: "bg-node-role-ai-detect-handle!",
  },
  aiClassify: {
    border: "border-l-node-role-ai-classify-border",
    surface: "bg-node-role-ai-classify-surface",
    icon: "text-node-role-ai-classify-icon",
    title: "text-node-role-ai-classify-title",
    handle: "bg-node-role-ai-classify-handle!",
  },
  aiTrack: {
    border: "border-l-node-role-ai-track-border",
    surface: "bg-node-role-ai-track-surface",
    icon: "text-node-role-ai-track-icon",
    title: "text-node-role-ai-track-title",
    handle: "bg-node-role-ai-track-handle!",
  },
} as const satisfies Record<string, PipelineNodeRoleClasses>;
