// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include "sift_extractor/extractor.hpp"
#include "sift_extractor/features.hpp"

#include <opencv2/core.hpp>

#include <vector>

namespace sift_extractor::opencv {

// Thin OpenCV type adapters around the OpenCV-free core Extractor.
// This is not OpenCV features2d SIFT and not Phase D upstream work.
// KeyPoint::size uses diameter = 2 * SiftFeature::scale (presentation mapping).

cv::KeyPoint to_keypoint(const SiftFeature &feature);

void to_opencv(const std::vector<SiftFeature> &features,
               std::vector<cv::KeyPoint> &keypoints, cv::Mat &descriptors);

// Accepts single-channel CV_8U or CV_32F grayscale; returns contiguous CV_32F.
cv::Mat to_float_gray(const cv::Mat &image);

// Image shape must match extractor width/height.
std::vector<SiftFeature> extract(Extractor &extractor, const cv::Mat &image);

void detect_and_compute(Extractor &extractor, const cv::Mat &image,
                        std::vector<cv::KeyPoint> &keypoints, cv::Mat &descriptors);

} // namespace sift_extractor::opencv
