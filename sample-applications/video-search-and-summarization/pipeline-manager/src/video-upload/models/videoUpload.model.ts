// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { ApiProperty } from '@nestjs/swagger';
import { VideoUploadDTO } from './upload.model';
import { EVAMPipelines } from 'src/evam/models/evam.model';

export class VideoUploadDTOModel implements VideoUploadDTO {
  @ApiProperty({ description: 'Custom name for video' })
  videoName: string;

  @ApiProperty({ description: 'Duration of each chunk in seconds' })
  chunkDuration: number;

  @ApiProperty({ description: 'Number of frames to sample per chunk' })
  samplingFrame: number;

  @ApiProperty({
    description: 'Number of frames to process in parallel',
    required: false,
  })
  multiFrameOverride?: number;

  @ApiProperty({
    description: 'Number of frames to overlap between chunks',
    required: false,
  })
  overlapOverride?: number;

  @ApiProperty({ description: 'Prompt for each frame', required: false })
  framePromptOverride?: string;

  @ApiProperty({ description: 'Prompt for the map phase', required: false })
  mapPromptOverride?: string;

  @ApiProperty({ description: 'Prompt for the reduce phase', required: false })
  reducePromptOverride?: string;

  @ApiProperty({ description: 'Prompt for the single phase', required: false })
  singlePromptOverride?: string;

  @ApiProperty({
    description: 'EVAM pipeline to use',
    required: false,
    enum: EVAMPipelines,
  })
  evamPipelineOverride?: EVAMPipelines;

  @ApiProperty({ description: 'Audio model to use', required: false })
  audioModelOverride?: string;
}
