// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { ApiProperty } from '@nestjs/swagger';
import { VideoDTO } from './video.model';
import { UploadedFile } from '@nestjs/common';

export class VideoDTOSwagger implements VideoDTO {
  @ApiProperty({
    description: 'Video file to upload',
    type: 'string',
    format: 'binary',
  })
  video: any;

  @ApiProperty({ description: 'Name of the video file', required: false })
  name: string;

  @ApiProperty({
    description: 'Tags seperated by commas',
    required: false,
  })
  tags?: string;
}
