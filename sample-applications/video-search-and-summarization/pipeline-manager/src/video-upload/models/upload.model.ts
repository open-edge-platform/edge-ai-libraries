// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { AudioModel } from 'src/audio/models/audio.model';
import { EvamPipelineOption, EVAMPipelines } from 'src/evam/models/evam.model';

export interface VideoUploadDTO {
  videoName: string;
  chunkDuration: number;
  samplingFrame: number;
  multiFrameOverride?: number;
  overlapOverride?: number;
  framePromptOverride?: string;
  mapPromptOverride?: string;
  reducePromptOverride?: string;
  singlePromptOverride?: string;
  evamPipelineOverride?: string;
  audioModelOverride?: string;
}

export enum overrideKeys {
  multiFrameOverride = 'multiFrame',
  overlapOverride = 'frameOverlap',
  framePromptOverride = 'framePrompt',
  mapPromptOverride = 'summaryMapPrompt',
  reducePromptOverride = 'summaryReducePrompt',
  singlePromptOverride = 'summarySinglePrompt',
  evamPipelineOverride = 'evamPipeline',
  audioModelOverride = 'audioModel',
}

export interface VideoUploadUserInputs {
  videoName: string;
  chunkDuration: number;
  samplingFrame: number;
}

export interface InferenceConfig {
  temperature: number;
  topP: number;
  presencePenalty: number | null;
  maxCompletionTokens: number;
  frequencyPenalty: number;
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

export interface SystemConfigWithMeta extends SystemConfig {
  meta: {
    evamPipelines: EvamPipelineOption[];
    defaultAudioModel?: string;
    audioModels: AudioModel[];
  };
}

export interface VideoUploadRO {
  message: string;
  stateId: string;
}
