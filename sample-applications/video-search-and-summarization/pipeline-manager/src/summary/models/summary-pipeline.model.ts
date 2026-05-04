// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { ApiProperty } from '@nestjs/swagger';
import { EVAMPipelines } from 'src/evam/models/evam.model';
import { Video } from 'src/video-upload/models/video.model';

export interface SummaryPipelineSampling {
  videoStart?: number;
  videoEnd?: number;
  chunkDuration: number;
  samplingFrame: number;
  frameOverlap: number;
  multiFrame: number;
}
export class SummaryPipelineSamplingSwagger implements SummaryPipelineSampling {
  @ApiProperty({
    required: true,
    description: 'Duration for a chunk in seconds',
  })
  chunkDuration: number;

  @ApiProperty({
    required: true,
    description: 'Number of frames to sample per chunk',
  })
  samplingFrame: number;

  @ApiProperty({
    required: true,
    description: 'Frame overlap count',
  })
  frameOverlap: number;

  @ApiProperty({
    required: true,
    description: 'Multi frame count (batch size)',
  })
  multiFrame: number;
}

export interface SummaryPipelinePrompts {
  framePrompt?: string;
  summaryMapPrompt?: string;
  summaryReducePrompt?: string;
  summarySinglePrompt?: string;
  audioSummaryMapPrompt?: string;
  audioSummaryReducePrompt?: string;
  audioSummarySinglePrompt?: string;
}
export class SummaryPipelinePromptsSwagger implements SummaryPipelinePrompts {
  @ApiProperty({
    required: false,
    description: 'Prompt for frame processing',
  })
  framePrompt?: string;
  @ApiProperty({
    required: false,
    description: 'Prompt for summary map processing',
  })
  summaryMapPrompt?: string;
  @ApiProperty({
    required: false,
    description: 'Prompt for summary reduce processing',
  })
  summaryReducePrompt?: string;
  @ApiProperty({
    required: false,
    description: 'Prompt for single summary processing',
  })
  summarySinglePrompt?: string;

  @ApiProperty({
    required: false,
    description: 'Prompt for full audio transcript summarization (map stage)',
  })
  audioSummaryMapPrompt?: string;

  @ApiProperty({
    required: false,
    description: 'Prompt for full audio transcript summarization (reduce stage)',
  })
  audioSummaryReducePrompt?: string;

  @ApiProperty({
    required: false,
    description: 'Prompt for full audio transcript summarization (single reduction stage)',
  })
  audioSummarySinglePrompt?: string;
}

export interface SummaryPipelineAudio {
  audioModel: string;
  useFullTranscriptSummary?: boolean;
}

export class SummaryPipelineAudioSwagger implements SummaryPipelineAudio {
  @ApiProperty({
    required: true,
    description: 'Audio model configuration',
  })
  audioModel: string;

  @ApiProperty({
    required: false,
    description: 'Enable full transcript summarization for audio-dominant videos',
  })
  useFullTranscriptSummary?: boolean;
}

export interface SummaryPipelineEvam {
  evamPipeline: EVAMPipelines;
}

export class SummaryPipelineEvamSwagger implements SummaryPipelineEvam {
  @ApiProperty({
    type: String,
    enum: EVAMPipelines,
    enumName: 'EVAM Pipeline',
  })
  evamPipeline: EVAMPipelines;
}

export interface SummaryPipelineDTO {
  videoId: string;
  video?: Video;
  title: string;
  sampling: SummaryPipelineSampling;
  evam: SummaryPipelineEvam;
  prompts?: SummaryPipelinePrompts;
  audio?: SummaryPipelineAudio;
}

export class SummaryPipelineDTOSwagger implements SummaryPipelineDTO {
  @ApiProperty({ required: true, description: 'ID of the video' })
  videoId: string;

  @ApiProperty({ required: true, description: 'Title for the summary' })
  title: string;

  @ApiProperty({
    required: true,
    description: 'Sampling configuration for the summary',
    type: SummaryPipelineSamplingSwagger,
  })
  sampling: SummaryPipelineSampling;

  @ApiProperty({
    required: true,
    description: 'EVAM pipeline configuration',
    type: SummaryPipelineEvamSwagger,
  })
  evam: SummaryPipelineEvam;

  @ApiProperty({
    required: false,
    description: 'Prompts override',
    type: SummaryPipelinePromptsSwagger,
  })
  prompts?: SummaryPipelinePrompts | undefined;

  @ApiProperty({
    required: false,
    description: 'Audio model configuration',
    type: SummaryPipelineAudioSwagger,
  })
  audio?: SummaryPipelineAudio | undefined;
}

export interface SummaryPipelinRO {
  summaryPipelineId: string;
}

export class SummaryPipelineROSwagger implements SummaryPipelinRO {
  @ApiProperty({ description: 'ID of the created summary pipeline state' })
  summaryPipelineId: string;
}
