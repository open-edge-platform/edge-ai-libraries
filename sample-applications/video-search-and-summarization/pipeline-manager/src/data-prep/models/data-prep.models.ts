// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
export interface DataPrepMinioDTO {
  bucket_name: string;
  video_id: string;
  video_name?: string;
  tags?: string[];
}

export interface DataPrepBatchProcessDTO {
  items: DataPrepMinioDTO[];
}

export interface DataPrepBatchSubmitRO {
  status?: string;
  message?: string;
  job_id: string;
  accepted: number;
}

export interface DataPrepBatchItemResultRO {
  identifier: string;
  bucket_name?: string;
  video_id?: string;
  status: string;
  message?: string;
  embeddings_count?: number;
}

export interface DataPrepBatchJobStatusRO {
  job_id: string;
  state: string;
  source?: string;
  total: number;
  completed: number;
  failed: number;
  items: DataPrepBatchItemResultRO[];
  created_ts?: number;
  updated_ts?: number;
}

export interface DataPrepSummaryDTO {
  bucket_name: string;
  video_id: string;
  video_summary: string;
  video_start_time: number;
  video_end_time: number;
  tags: string[];
}

export interface DataPrepMinioRO {
  status: string;
  message: string;
}
