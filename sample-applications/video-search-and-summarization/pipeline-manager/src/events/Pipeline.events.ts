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
