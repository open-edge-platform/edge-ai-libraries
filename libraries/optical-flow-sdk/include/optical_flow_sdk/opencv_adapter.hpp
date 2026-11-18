// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include "optical_flow_sdk/optical_flow.hpp"
#include "optical_flow_sdk/types.hpp"
#include "optical_flow_sdk/version.hpp"

#if OPTICALFLOW_HAS_OPENCV_ADAPTER

#include <opencv2/core.hpp>

namespace optical_flow_sdk::opencv {

// Thin OpenCV type adapters around the OpenCV-free core. This is not
// OpenCV's video tracking module; it only bridges Mat <-> SDK types.

ImageView as_image_view(const cv::Mat &gray8);
cv::Mat to_mat(const FlowField &flow);   // CV_32FC2
cv::Mat to_mat(const CostMap &cost);     // CV_8UC1
FlowField to_flow_field(const cv::Mat &flow32fc2);

void calc(OpticalFlow &of, const cv::Mat &prev_gray8, const cv::Mat &next_gray8, cv::Mat &flow32fc2);
void calc(OpticalFlow &of, const cv::Mat &prev_gray8, const cv::Mat &next_gray8, cv::Mat &flow32fc2,
          cv::Mat &cost8u);

} // namespace optical_flow_sdk::opencv

#endif // OPTICALFLOW_HAS_OPENCV_ADAPTER
