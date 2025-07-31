// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { AudioDevice, srtText } from 'src/audio/models/audio.model';
import { FrameMetadata } from 'src/evam/models/message-broker.model';
import { SummaryPipelineSampling } from 'src/summary/models/summary-pipeline.model';
import { SystemConfig } from 'src/video-upload/models/upload.model';
import { Video } from 'src/video-upload/models/video.model';

export enum StateStatus {
  UPLOADING,
  PROCESSING,
}

export enum StateActionStatus {
  NA = 'na',
  READY = 'ready',
  IN_PROGRESS = 'inProgress',
  COMPLETE = 'complete',
}

export interface StateChunkFrame {
  frameId: string;
  chunkId: string;
  createdAt: string;
  frameUri: string;
  metadata?: FrameMetadata;
}

export interface StateChunk {
  chunkId: string;
}

export interface FileInfo {
  destination: string;
  path: string;
  filename: string;
  mimetype: string;
  originalname: string;
  fieldname: string;
  extension?: string;
  minioObject?: string;
}

export interface ModelInfo {
  model: string;
  device: string;
  pipeline?: string;
}

export interface InferenceConfig {
  objectDetection?: ModelInfo;
  imageInference?: ModelInfo;
  textInference?: ModelInfo;
}

export interface FrameSummary {
  summary: string;
  frames: string[];
  frameKey: string;
  startFrame: string;
  endFrame: string;
  status: StateActionStatus;
  embeddingsCreated?: boolean;
}

export interface StateAudio {
  device: AudioDevice;
  model: string;
  status: StateActionStatus;
  transcriptPath?: string;
  transcript: srtText[];
}

export interface State {
  dbId?: number;
  stateId: string;
  createdAt: string;
  updatedAt: string;
  title: string;
  userInputs: SummaryPipelineSampling;
  chunks: Record<string, StateChunk>;
  frames: Record<string, StateChunkFrame>;
  frameSummaries: Record<string, FrameSummary>;
  systemConfig: SystemConfig;
  evamProcessId?: string;
  summary?: string;
  inferenceConfig?: InferenceConfig;
  audio?: StateAudio;
  video: Video;
  status: {
    dataStoreUpload: StateActionStatus;
    summarizing: StateActionStatus;
    chunking: StateActionStatus;
  };
}

export interface FrameSyncDTO {
  frameId: string;
  chunkId: string;
  stateId: string;
  captioningStatus: StateActionStatus;
}

export interface ChunkStatusSyncDTO {
  chunkId: string;
  stateId: string;
  summaryStatus: StateActionStatus;
  captionStatus: StateActionStatus;
}

export interface ChunkSummarySyncDTO {
  chunkId: string;
  stateId: string;
  summary: string;
}

export interface SummaryChunkDTO {
  stateId: string;
  summaryChunk: string;
}

export interface SummarySyncDTO {
  stateId: string;
  summary: string;
}
