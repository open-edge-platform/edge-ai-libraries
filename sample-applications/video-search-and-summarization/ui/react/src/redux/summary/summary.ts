// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
export enum StateActionStatus {
  NA = 'na',
  READY = 'ready',
  IN_PROGRESS = 'inProgress',
  COMPLETE = 'complete',
}

export enum StateStatus {
  IDLE,
  LOADING,
}

export interface ObjectBoundingBox {
  x_max: number;
  x_min: number;
  y_max: number;
  y_min: number;
}

export interface DetectionConfig {
  bounding_box: ObjectBoundingBox;
  confidence: number;
  label: string;
  label_id: number;
}

export interface DetectedObject {
  detection: DetectionConfig;
  h: number;
  region_id: number;
  roi_type: string;
  w: number;
  x: number;
  y: number;
}

export interface FrameMetadata {
  objects?: DetectedObject[];
  resolution?: { height: number; width: number };
  system_timestamp?: string;
  timestamp?: number;
  time: string;
  image_format: string;
}

export type CountStatus = Record<StateActionStatus, number>;

export interface UIChunk {
  chunkId: string;
  duration: { from: number; to: number };
}

export interface UIChunkForState extends UIChunk {
  stateId: string;
}

export interface UIFrame {
  chunkId: string;
  frameId: string;
  url?: string;
  metadata?: FrameMetadata;
  videoTimeStamp?: number;
}

export interface UIFrameForState extends UIFrame {
  stateId: string;
}

export interface SummaryUserInputs {
  videoName: string;
  chunkDuration: number;
  samplingFrame: number;
  samplingInterval: number;
}

export interface ModelInfo {
  model: string;
  device: string;
}

export interface InferenceConfig {
  objectDetection?: ModelInfo;
  imageInference?: ModelInfo;
  textInference?: ModelInfo;
}

export interface ICDTO extends InferenceConfig {
  stateId: string;
}

export interface UIInferenceConfig extends ModelInfo {
  key: string;
}

export interface UIFrameSummary {
  summary: string;
  frames: string[];
  frameKey: string;
  startFrame: string;
  endFrame: string;
  status: StateActionStatus;
  embeddingsCreated?: boolean;
  stateId: string;
}

export interface SummaryPipelineSampling {
  videoStart?: number;
  videoEnd?: number;
  chunkDuration: number;
  samplingFrame: number;
  frameOverlap: number;
  multiFrame: number;
}

export interface SystemConfig {
  multiFrame: number;
  frameOverlap: number;

  llm?: InferenceConfig;
  vlm?: InferenceConfig;

  evamPipeline: EVAMPipelines;

  audioModel?: string;

  framePrompt: string;
  summaryMapPrompt: string;
  summaryReducePrompt: string;
  summarySinglePrompt: string;
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

export interface AudioModel {
  model_id: string;
  display_name: string;
  description: string;
}

export interface SystemConfigWithMeta extends SystemConfig {
  meta: {
    evamPipelines: EvamPipelineOption[];
    defaultAudioModel?: string;
    audioModels: AudioModel[];
  };
}

export interface UIStateStatus {
  videoSummaryStatus: StateActionStatus;
  frameSummaryStatus: CountStatus;
  chunkingStatus: StateActionStatus;
}

export interface UIStatusForState extends UIStateStatus {
  stateId: string;
}

export interface UISummaryState {
  stateId: string;
  userInputs: SummaryPipelineSampling;
  inferenceConfig?: InferenceConfig;
  videoId: string;
  summary: string;
  title: string;
  systemConfig: SystemConfig;
  chunksCount: number;
  framesCount: number;
  frameSummaries: number;
  videoSummaryStatus: StateActionStatus;
  frameSummaryStatus: CountStatus;
  chunkingStatus: StateActionStatus;
}

export interface UIState extends UIStateStatus {
  stateId: string;
  chunks: UIChunk[];
  frames: UIFrame[];
  title: string;
  systemConfig: SystemConfig;
  userInputs: SummaryPipelineSampling;
  summary: string;
  frameSummaries: UIFrameSummary[];
  videoId: string;
  inferenceConfig?: InferenceConfig;
}

export interface SummaryUserInputs {
  chunkDuration: number;
  samplingFrame: number;
  samplingInterval: number;
}

export interface SummaryState {
  summaries: Record<string, UISummaryState>;
  selectedSummary: string | null;
  status: StateStatus;
}

export interface VideoChunkState {
  chunks: Record<string, UIChunkForState>;
  selectedSummary: string | null;
}

export interface VideoFrameState {
  frames: Record<string, UIFrameForState>;
  frameSummaries: Record<string, UIFrameSummary>;
  selectedSummary: string | null;
}

export interface SummaryStatusWithFrames {
  summary: string;
  status: StateActionStatus;
  frames: string[];
}
export interface ChunkSummaryStatusFromFrames {
  summaryUsingFrames: number;
  summaryStatus: StateActionStatus;
  summaries: SummaryStatusWithFrames[];
  hasEmbeddings: boolean;
}

export interface SummaryStreamChunk {
  stateId: string;
  streamChunk: string;
}

export interface VideoUploadRO {
  message: string;
  stateId: string;
}

export interface FrameDataDTO {
  stateId: string;
  chunkId: string;
  frameId: string;
  uiFrame: UIFrame;
}

export interface ChunkStatusDTO {
  stateId: string;
  chunkId: string;
  status: { summaryStatus: StateActionStatus; captionStatus: CountStatus };
}

export interface ChunkSummaryDTO {
  stateId: string;
  chunkId: string;
  uiChunk: UIChunk;
}
