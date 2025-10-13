// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { ApiProperty } from '@nestjs/swagger';

export enum AudioDevice {
  CPU = 'cpu',
  GPU = 'gpu',
  AUTO = 'auto',
}

export interface srtText {
  id: string;
  startTime: string;
  endTime: string;
  startSeconds: number;
  endSeconds: number;
  text: string;
}

export interface AudioModel {
  model_id: string;
  display_name: string;
  description: string;
}
export class AudioModelSwagger implements AudioModel {
  @ApiProperty({ description: 'Unique identifier for the audio model' })
  model_id: string;

  @ApiProperty({ description: 'Display name of the audio model' })
  display_name: string;

  @ApiProperty({ description: 'Description of the audio model' })
  description: string;
}
export interface AudioModelRO {
  default_model: string;
  models: AudioModel[];
}

export class AudioModelROSwagger implements AudioModelRO {
  @ApiProperty({ description: 'Default audio model ID' })
  default_model: string;

  @ApiProperty({
    type: [AudioModelSwagger],
    description: 'List of available audio models',
  })
  models: AudioModel[];
}

export interface AudioTranscriptDTO {
  file?: null;
  device: AudioDevice;
  model_name: string;
  include_timestamps: boolean;
  minio_bucket: string;
  video_id: string;
  video_name: string;
}

export interface AudioTranscriptsParsed {
  transcriptPath: string;
  transcripts: srtText[];
}

export interface AudioTranscriptionRO {
  job_id: string;
  message: string;
  status: string;
  transcript_path: string;
  video_duration: number;
  video_name: string;
}
