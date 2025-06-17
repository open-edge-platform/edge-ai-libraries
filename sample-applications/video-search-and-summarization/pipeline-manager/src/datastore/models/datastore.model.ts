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

// const frameData = {
//   frame_id: 3,
//   chunk_id: 1,
//   chunk_frame_number: 3,
//   image_uri: '/videosummtest-1/video_id_1/frame/chunk_1_frame_3.jpeg',
//   frame_metadata: {
//     objects: [
//       {
//         detection: {
//           bounding_box: {
//             x_max: 0.8349332218607248,
//             x_min: 0.7635653371150095,
//             y_max: 0.6859462363413904,
//             y_min: 0.46424957013502066,
//           },
//           confidence: 0.8981269001960754,
//           label: 'person',
//           label_id: 0,
//         },
//         h: 96,
//         region_id: 403,
//         roi_type: 'person',
//         w: 55,
//         x: 586,
//         y: 201,
//       },
//     ],
//     resolution: { height: 432, width: 768 },
//     system_timestamp: '2025-02-24T06:36:50.549:+0000',
//     timestamp: 4000000000,
//     time: '2025_02_07-14_30_19.123',
//     img_format: 'BGR',
//   },
// };
