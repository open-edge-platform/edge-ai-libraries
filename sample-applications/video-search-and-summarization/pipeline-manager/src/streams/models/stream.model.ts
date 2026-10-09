// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { Transform, Type } from 'class-transformer';
import {
  ArrayMaxSize,
  ArrayNotEmpty,
  IsArray,
  IsBoolean,
  IsIn,
  IsInt,
  IsNotEmpty,
  IsNumber,
  IsOptional,
  IsString,
  Matches,
  Max,
  MaxLength,
  Min,
  ValidateNested,
} from 'class-validator';

/**
 * Lifecycle states reported by multimodal-dataprep.
 *
 * Mirrors `LiveStreamStateEnum` in the dataprep schema. All seven values can
 * appear in a response; only `running` and `paused` may be requested.
 */
export enum LiveStreamState {
  PENDING = 'pending',
  STARTING = 'starting',
  RUNNING = 'running',
  PAUSED = 'paused',
  RECONNECTING = 'reconnecting',
  ERROR = 'error',
  STOPPED = 'stopped',
}

/** The only states a caller is allowed to request via PATCH. */
export const CALLER_SETTABLE_STATES = [
  LiveStreamState.RUNNING,
  LiveStreamState.PAUSED,
] as const;

/**
 * Accepts only RTSP URLs.
 *
 * Deliberately permissive beyond the scheme: dataprep's `validate_stream_url`
 * is the authority on host/SSRF rules, and duplicating that logic here would
 * let the two drift apart. This check exists to reject the obvious mistake
 * (an http:// URL, a file path) before a credential leaves the browser.
 */
const RTSP_URL = /^rtsps?:\/\/\S+$/i;

const MAX_TAGS = 32;
const MAX_TAG_LENGTH = 128;

/** Query params arrive as strings; accept the usual truthy spellings. */
const toBoolean = ({ value }: { value: unknown }): unknown => {
  if (typeof value === 'boolean') return value;
  if (value === 'true' || value === '1') return true;
  if (value === 'false' || value === '0') return false;
  return value;
};

export class LiveStreamCreateDto {
  @ApiProperty({
    description:
      'RTSP source URL (rtsp:// or rtsps://). May carry credentials, which ' +
      'are never logged, never persisted by the Pipeline Manager, and never ' +
      'returned in a response.',
    example: 'rtsp://camera-1.local:554/stream1',
  })
  @IsString()
  @IsNotEmpty()
  @MaxLength(2048)
  @Matches(RTSP_URL, {
    message: 'stream_url must start with rtsp:// or rtsps://',
  })
  stream_url: string;

  @ApiPropertyOptional({ description: 'Friendly label for the camera.' })
  @IsOptional()
  @IsString()
  @MaxLength(256)
  stream_name?: string;

  @ApiPropertyOptional({ description: 'Free-text description.' })
  @IsOptional()
  @IsString()
  @MaxLength(1024)
  description?: string;

  @ApiPropertyOptional({
    description:
      'Stable logical identity of the physical source, recorded on every ' +
      'embedding. Defaults to the generated stream_id.',
  })
  @IsOptional()
  @IsString()
  @MaxLength(128)
  @Matches(/^[A-Za-z0-9][A-Za-z0-9._:-]*$/, {
    message:
      'sensor_id must start alphanumeric and contain only letters, digits, . _ : -',
  })
  sensor_id?: string;

  @ApiPropertyOptional({
    description: 'Sample every Nth frame. Lower = denser capture, more load.',
    minimum: 1,
    maximum: 60,
    example: 15,
  })
  @IsOptional()
  @Type(() => Number)
  @IsInt()
  @Min(1)
  @Max(60)
  frame_interval?: number;

  @ApiPropertyOptional({
    description: 'Enable object detection and crop extraction.',
    example: true,
  })
  @IsOptional()
  @IsBoolean()
  enable_object_detection?: boolean;

  @ApiPropertyOptional({
    description: 'Minimum detection score to keep a crop (0.1-1.0).',
    minimum: 0.1,
    maximum: 1.0,
    example: 0.85,
  })
  @IsOptional()
  @Type(() => Number)
  @IsNumber()
  @Min(0.1)
  @Max(1.0)
  detection_confidence?: number;

  @ApiPropertyOptional({
    type: [String],
    description: 'Tags applied to every embedding.',
  })
  @IsOptional()
  @IsArray()
  @ArrayMaxSize(MAX_TAGS)
  @IsString({ each: true })
  @MaxLength(MAX_TAG_LENGTH, { each: true })
  tags?: string[];

  @ApiPropertyOptional({
    description:
      'Start ingesting immediately. False registers the stream paused.',
    default: true,
  })
  @IsOptional()
  @IsBoolean()
  start?: boolean;
}

export class LiveStreamBatchCreateDto {
  @ApiProperty({ type: [LiveStreamCreateDto] })
  @IsArray()
  @ArrayNotEmpty()
  @ArrayMaxSize(64)
  @ValidateNested({ each: true })
  @Type(() => LiveStreamCreateDto)
  items: LiveStreamCreateDto[];
}

/**
 * PATCH body.
 *
 * `stream_url` is deliberately absent: dataprep's `LiveStreamUpdateRequest`
 * has no such field, so a URL change is not expressible. Changing a camera's
 * address means delete + re-create. With `forbidNonWhitelisted` on the
 * controller, sending one is rejected rather than silently dropped.
 */
export class LiveStreamUpdateDto {
  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  @MaxLength(256)
  stream_name?: string;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  @MaxLength(1024)
  description?: string;

  @ApiPropertyOptional({
    description: 'Sample every Nth frame. Lower = denser capture, more load.',
    minimum: 1,
    maximum: 60,
    example: 15,
  })
  @IsOptional()
  @Type(() => Number)
  @IsInt()
  @Min(1)
  @Max(60)
  frame_interval?: number;

  @ApiPropertyOptional({
    description: 'Enable object detection and crop extraction.',
    example: true,
  })
  @IsOptional()
  @IsBoolean()
  enable_object_detection?: boolean;

  @ApiPropertyOptional({
    description: 'Minimum detection score to keep a crop (0.1-1.0).',
    minimum: 0.1,
    maximum: 1.0,
    example: 0.85,
  })
  @IsOptional()
  @Type(() => Number)
  @IsNumber()
  @Min(0.1)
  @Max(1.0)
  detection_confidence?: number;

  @ApiPropertyOptional({
    type: [String],
    description: 'Replaces the existing tag list.',
  })
  @IsOptional()
  @IsArray()
  @ArrayMaxSize(MAX_TAGS)
  @IsString({ each: true })
  @MaxLength(MAX_TAG_LENGTH, { each: true })
  tags?: string[];

  @ApiPropertyOptional({
    enum: CALLER_SETTABLE_STATES,
    example: LiveStreamState.PAUSED,
    description:
      'Change the ingestion state. Only two transitions are allowed here: ' +
      '`running` resumes a paused stream, and `paused` pauses ingestion ' +
      'without deregistering it. The other lifecycle states a stream reports ' +
      'via GET - `pending`, `starting`, `reconnecting`, `error`, `stopped` - ' +
      'are managed by the service and cannot be set through this API.',
  })
  @IsOptional()
  @IsIn(CALLER_SETTABLE_STATES as readonly string[])
  state?: LiveStreamState.RUNNING | LiveStreamState.PAUSED;
}

export class LiveStreamListQueryDto {
  @ApiPropertyOptional({ enum: LiveStreamState })
  @IsOptional()
  @IsIn(Object.values(LiveStreamState))
  state?: LiveStreamState;

  @ApiPropertyOptional({
    type: [String],
    description: 'Only streams carrying all of these tags.',
  })
  @IsOptional()
  @Transform(({ value }) =>
    value === undefined || Array.isArray(value) ? value : [value],
  )
  @IsArray()
  @ArrayMaxSize(MAX_TAGS)
  @IsString({ each: true })
  @MaxLength(MAX_TAG_LENGTH, { each: true })
  tags?: string[];
}

export class LiveStreamPurgeQueryDto {
  @ApiPropertyOptional({
    default: false,
    description: 'Also delete every embedding generated from this stream.',
  })
  @IsOptional()
  @Transform(toBoolean)
  @IsBoolean()
  purge_embeddings?: boolean;

  @ApiPropertyOptional({
    default: false,
    description: "Also delete the stream's recorded segments and frames.",
  })
  @IsOptional()
  @Transform(toBoolean)
  @IsBoolean()
  purge_media?: boolean;
}

export class LiveStreamBatchDeleteDto {
  @ApiProperty({ type: [String] })
  @IsArray()
  @ArrayNotEmpty()
  @ArrayMaxSize(64)
  @IsString({ each: true })
  @MaxLength(256, { each: true })
  stream_ids: string[];
}

// -- Response shapes (documentation only; dataprep is the authority) --------

export interface LiveStreamStats {
  frames_processed: number;
  embeddings_created: number;
  segments_stored: number;
  frames_stored: number;
  reconnect_count: number;
  last_frame_ts?: number | null;
  started_ts?: number | null;
  uptime_seconds?: number | null;
}

export interface LiveStreamInfo {
  stream_id: string;
  /** Always redacted by dataprep — never carries credentials. */
  stream_url: string;
  stream_name: string;
  description?: string | null;
  state: LiveStreamState;
  bucket_name?: string | null;
  video_id?: string | null;
  sensor_id?: string | null;
  frame_interval: number;
  enable_object_detection: boolean;
  detection_confidence: number;
  tags: string[];
  stats: LiveStreamStats;
  last_error?: string | null;
  created_ts?: number | null;
  updated_ts?: number | null;
}

export interface LiveStreamListRO {
  status?: string;
  message?: string;
  count: number;
  streams: LiveStreamInfo[];
}

export interface LiveStreamRO {
  status?: string;
  message?: string;
  stream: LiveStreamInfo;
}

export interface LiveStreamBatchItemResult {
  identifier: string;
  stream_id?: string | null;
  status: string;
  message?: string | null;
}

export interface LiveStreamBatchRO {
  status?: string;
  message?: string;
  accepted: number;
  rejected: number;
  items: LiveStreamBatchItemResult[];
}

export interface LiveStreamDeleteRO {
  status?: string;
  message?: string;
  stream_id?: string;
  embeddings_purged?: number;
  media_purged?: number;
}
