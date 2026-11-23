// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
export enum PipelineEvents {
  UPLOAD_TO_DATASTORE = 'pipeline.upload',
  UPLOAD_TO_DATASTORE_COMPLETE = 'pipeline.upload.complete',
  SUMMARY_PIPELINE_START = 'pipeline.summary.start',

  CHECK_QUEUE_STATUS = 'pipeline.check.queue.status',

  AUDIO_TRIGGERED = 'pipeline.audio.triggered',
  AUDIO_COMPLETE = 'pipeline.audio.complete',
  AUDIO_ERROR = 'pipeline.audio.error',
  AUDIO_SUMMARY_TRIGGER = 'pipeline.audio.summary.trigger',
  AUDIO_SUMMARY_COMPLETE = 'pipeline.audio.summary.complete',

  CHUNKING_TRIGGERED = 'pipeline.chunking.triggered',
  CHUNKING_STATUS = 'pipeline.chunking.status',
  CHUNKING_COMPLETE = 'pipeline.chunking.complete',

  CHUNK_RECEIVED = 'pipeline.chunk.received',
  CHUNK_CAPTION_COMPLETE = 'pipeline.chunk.caption',
  CHUNK_SEARCH_EMBEDDINGS = 'pipeline.chunk.search.embeddings',

  FRAME_CAPTION_PROCESSING = 'pipeline.chunk.frame.captionProgress',
  FRAME_CAPTION_COMPLETE = 'pipeline.chunk.frame.caption',

  SUMMARY_TRIGGER = 'pipeline.summary.trigger',
  SUMMARY_PROCESSING = 'pipeline.summary.processing',
  SUMMARY_STREAM = 'pipeline.summary.stream',
  SUMMARY_COMPLETE = 'pipeline.summary.complete',
}

export enum SearchEvents {
  EMBEDDINGS_UPDATE = 'search.embeddings.update',
  RUN_QUERY = 'search.run.query',
}

export enum StreamEvents {
  /** Payload: `string[]`, the union of tags on all registered live streams. */
  TAGS_SEEN = 'streams.tags.seen',
}

export enum VideoEvents {
  /** Payload: `VideoEmbeddingsStatusEvent`. */
  EMBEDDINGS_STATUS = 'video.embeddings.status',
}

/**
 * Which index a stored video has been embedded into:
 * - `searchEmbeddings`: frame/object embeddings from dataprep `/media/process`
 *   (`POST /videos/search-embeddings[-batch]`).
 * - `textEmbeddings`: chunk-caption embeddings from dataprep `/summary`,
 *   written by the summary pipeline when search is enabled.
 */
export type VideoEmbeddingKind = 'searchEmbeddings' | 'textEmbeddings';

export interface VideoEmbeddingsStatusEvent {
  videoId: string;
  kind: VideoEmbeddingKind;
  created: boolean;
}

export enum PipelineErrors {}

export interface PipelineDTOBase {
  stateId: string;
}

export interface PipelineUploadToDS extends PipelineDTOBase {
  fileInfo: Express.Multer.File;
}

export interface FrameCaptionEventDTO extends PipelineDTOBase {
  frameIds: string[];
  caption: string;
}

export interface ChunkSummaryTrigger extends PipelineDTOBase {
  chunkId: string;
}

export interface ChunkSummaryComplete extends PipelineDTOBase {
  chunkId: string;
  summary: string;
}

export interface SummaryStreamChunk extends PipelineDTOBase {
  streamChunk: string;
}

export interface SummaryCompleteRO extends PipelineDTOBase {
  summary: string;
}
