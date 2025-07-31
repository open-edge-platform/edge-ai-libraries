// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
export interface ChunkFrame {
  frameId: string;
  imageUri: string;
  imageBase64?: string;
  metadata?: FrameMetadata;
}

export interface ChunkQueue {
  evamIdentifier: string;
  chunkId: number;
  frames: ChunkFrame[];
}

export interface ChunkQueueItem {
  chunkId: string;
  stateId: string;
}

export interface SummaryQueueItem {
  stateId: string;
}

export interface FrameQueueItem {
  queueKey: string;
  stateId: string;
  frames: string[];
}

export interface ObjectBoundingBox {
  x_max: number;
  x_min: number;
  y_max: number;
  y_min: number;
}

export interface DetectionConfig {
  bounding_box: ObjectBoundingBox;
  confidence: number;
  label: string;
  label_id: number;
}

export interface DetectedObject {
  detection: DetectionConfig;
  h: number;
  region_id: number;
  roi_type: string;
  w: number;
  x: number;
  y: number;
}

export interface FrameMetadata {
  objects?: DetectedObject[];
  resolution?: { height: number; width: number };
  system_timestamp?: string;
  timestamp?: number;
  frame_timestamp: number;
  image_format: string;
}

//  metadata: {
//     objects: [
//       {
//         detection: {
//           bounding_box: {
//             x_max: 0.9815004495009845,
//             x_min: 0.8798492562748379,
//             y_max: 0.249878624824861,
//             y_min: 0.1456219218018937
//           },
//           confidence: 0.9029167890548706,
//           label: 'bicycle',
//           label_id: 1
//         },
//         h: 45,
//         region_id: 2490,
//         roi_type: 'bicycle',
//         w: 78,
//         x: 676,
//         y: 63
//       },
//       {
//         detection: {
//           bounding_box: {
//             x_max: 0.9658714438359652,
//             x_min: 0.9142879622323505,
//             y_max: 0.22762382369672984,
//             y_min: 0.06790907484157493
//           },
//           confidence: 0.8019858002662659,
//           label: 'person',
//           label_id: 0
//         },
//         h: 69,
//         region_id: 2491,
//         roi_type: 'person',
//         w: 40,
//         x: 702,
//         y: 29
//       }
//     ],
//     resolution: { height: 432, width: 768 },
//     system_timestamp: '2025-02-17T11:11:34.600:+0000',
//     timestamp: 28500000000,
//     time: '2025_02_07-14_30_43.623456',
//     img_format: 'BGR'
//   }
