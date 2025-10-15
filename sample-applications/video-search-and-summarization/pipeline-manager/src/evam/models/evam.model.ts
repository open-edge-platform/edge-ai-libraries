// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
export interface MediaSource {
  element: string;
  type: string;
  properties: {
    location: string;
  };
}

export interface DetectionProps {
  model: string;
  device: string;
}

export interface PublishProps {
  minio_bucket: string;
  video_identifier: string;
  topic: string;
}

export interface Parameters {
  frame: number;
  chunk_duration: number;
  frame_width?: number;
  'detection-properties': DetectionProps;
  publish: PublishProps;
}

export interface ChunkingRequestDTO {
  source: MediaSource;
  parameters: Parameters;
}

export enum EVAMPipelines {
  OBJECT_DETECTION = 'object_detection',
  BASIC_INGESTION = 'video_ingestion',
}

export interface EvamPipelineOption {
  name: string;
  description: string;
  value: EVAMPipelines;
  customOverride?: string;
}

export interface EVAMPipelineRO {
  id: string;
  launch_command: string;
  params: any;
  request: any;
  state: string;
  type: string;
}
