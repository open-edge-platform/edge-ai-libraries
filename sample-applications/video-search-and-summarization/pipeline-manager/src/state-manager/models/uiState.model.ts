// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { FrameMetadata } from 'src/evam/models/message-broker.model';
import {
  FrameSummary,
  InferenceConfig,
  StateActionStatus,
} from './state.model';
import { SystemConfig } from 'src/video-upload/models/upload.model';
import { SummaryPipelineSampling } from 'src/summary/models/summary-pipeline.model';

export type CountStatus = Record<StateActionStatus, number>;

export interface UIChunk {
  chunkId: string;
  duration: { from: number; to: number };
}

export interface UIFrameSummary extends FrameSummary {
  stateId: string;
}

export interface UIFrame {
  chunkId: string;
  frameId: string;
  url?: string;
  metadata?: FrameMetadata;
  videoTimeStamp?: number;
}

export interface SummaryUserInputs {
  videoName: string;
  chunkDuration: number;
  samplingFrame: number;
}

export interface UIStateStatus {
  videoSummaryStatus: StateActionStatus;
  frameSummaryStatus: CountStatus;
  chunkingStatus: StateActionStatus;
  audioStatus?: StateActionStatus;
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
