// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { FrameMetadata } from 'src/evam/models/message-broker.model';

export interface FileUploadRO {
  filePath: string;
}

export interface FrameData {
  frame_id: number;
  chunk_id: number;
  chunk_frame_number: number;
  image_url: string;
  frame_metadata: FrameMetadata;
}
