// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
export interface VideoDatastoreInfo {
  bucket: string;
  objectName: string;
  fileName: string;
}

export interface Video {
  dbId?: number;
  videoId: string;
  name: string;
  url: string;
  tags: string[];
  createdAt: string;
  updatedAt: string;
  summaries?: string[];
  textEmbeddings?: boolean;
  videoEmbeddings?: boolean;
  dataStore?: VideoDatastoreInfo;
}

export interface VideoDTO {
  name?: string;
  tags?: string;
  tagsArray?: string[];
}

export interface VideoRO {
  videoId: string;
}
