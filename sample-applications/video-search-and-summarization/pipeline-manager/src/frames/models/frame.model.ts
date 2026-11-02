// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { Type } from 'class-transformer';
import {
  IsIn,
  IsInt,
  IsNotEmpty,
  IsNumber,
  IsOptional,
  IsString,
  Matches,
  Max,
  Min,
} from 'class-validator';

/** A pixel bounding box 'x1,y1,x2,y2' (integers). */
const CROP_BBOX = /^\d+,\d+,\d+,\d+$/;

/**
 * Query for `GET /manager/frames`, proxied to dataprep `GET /media/frame`.
 *
 * Addresses one frame purely by location + time (+ optional crop box). A
 * typical caller is a downstream agent that took these values straight from a
 * search result's `best_frame_info`.
 */
export class FrameQueryDto {
  @ApiProperty({
    description: 'Uploaded video_id or live stream_id.',
    example: 'cam-lobby-01',
  })
  @IsString()
  @IsNotEmpty()
  video_id!: string;

  @ApiProperty({
    description:
      'Seconds from the start of the addressed media. For an upload this is the ' +
      'position in the file; for a live stream it is the offset within the ' +
      'segment named by media_path. Pass best_frame_info.timestamp here.',
    example: 4.5,
  })
  @Type(() => Number)
  @IsNumber()
  @Min(0)
  timestamp!: number;

  @ApiPropertyOptional({
    description: 'Bucket/top-level directory holding the media. Defaults to the configured bucket.',
  })
  @IsOptional()
  @IsString()
  bucket_name?: string;

  @ApiPropertyOptional({
    description:
      "Relative object path inside the video_id directory, e.g. 'segments/1790655530.mp4'. " +
      'Required for live-stream frames (stored under <stream_id>/segments/).',
  })
  @IsOptional()
  @IsString()
  media_path?: string;

  @ApiPropertyOptional({
    description: "'full' returns the whole frame; 'crop' returns the crop_bbox region.",
    enum: ['full', 'crop'],
    default: 'full',
  })
  @IsOptional()
  @IsIn(['full', 'crop'])
  variant?: 'full' | 'crop';

  @ApiPropertyOptional({
    description:
      "Pixel box 'x1,y1,x2,y2' for variant=crop. Supply best_frame_info.crop_bbox. Ignored when variant=full.",
    example: '120,80,360,420',
  })
  @IsOptional()
  @IsString()
  @Matches(CROP_BBOX, {
    message: 'crop_bbox must be four integers in the form x1,y1,x2,y2',
  })
  crop_bbox?: string;

  @ApiPropertyOptional({
    description: "'image' returns raw image/jpeg (default); 'json' returns base64 + metadata.",
    enum: ['image', 'json'],
    default: 'image',
  })
  @IsOptional()
  @IsIn(['image', 'json'])
  format?: 'image' | 'json';

  @ApiPropertyOptional({
    description: 'Output JPEG quality (1-100).',
    minimum: 1,
    maximum: 100,
    default: 90,
  })
  @IsOptional()
  @Type(() => Number)
  @IsInt()
  @Min(1)
  @Max(100)
  quality?: number;
}

/** Metadata describing the frame returned by the JSON variant. */
export interface FrameMetadataRO {
  video_id: string;
  bucket_name: string;
  media_path?: string | null;
  requested_timestamp: number;
  actual_timestamp?: number | null;
  variant: string;
  width: number;
  height: number;
  cropped: boolean;
}

/** JSON (`format=json`) response: base64 JPEG + metadata. */
export interface FrameJsonRO {
  mime: string;
  image_base64: string;
  frame: FrameMetadataRO;
}
