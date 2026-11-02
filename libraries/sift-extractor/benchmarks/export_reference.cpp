// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <opencv2/core.hpp>
#include <opencv2/imgcodecs.hpp>
#include <algorithm>
#include <iostream>
#include <stdexcept>

#ifdef SIFT_VALIDATE_CUDA
#include <cuda_runtime.h>
#include "cudaSift.h"
#else
#define main sift_complete_reference_application_main
#include SIFT_COMPLETE_REFERENCE_SOURCE
#undef main
#endif

int main(int argc, char **argv) {
  if (argc != 3) {
    std::cerr << "Usage: export_reference IMAGE OUTPUT.json\n";
    return 2;
  }
  try {
    cv::setNumThreads(1);
    const cv::Mat gray = cv::imread(argv[1], cv::IMREAD_GRAYSCALE);
    if (gray.empty() || gray.cols > 3840 || gray.rows > 2160)
      throw std::runtime_error("Invalid reference image dimensions");
    cv::Mat positions, descriptors;
    int capacity = 0;
    std::string backend;
#ifdef SIFT_VALIDATE_CUDA
    InitCuda(0);
    cv::Mat pixels;
    gray.convertTo(pixels, CV_32F);
    CudaImage image;
    image.Allocate(gray.cols, gray.rows, (gray.cols + 127) / 128 * 128,
                   false, nullptr, pixels.ptr<float>());
    image.Download();
    struct Storage {
      SiftData data{};
      ~Storage() { FreeSiftData(data); }
    } storage;
    capacity = 32768;
    InitSiftData(storage.data, capacity, true, true);
    ExtractSift(storage.data, image, 4, 1.0, 3.0f, 0.0f, false);
    if (cudaDeviceSynchronize() != cudaSuccess || storage.data.numPts < 0 ||
        storage.data.numPts > capacity)
      throw std::runtime_error("CUDA reference extraction failed");
    positions.create(storage.data.numPts, 2, CV_32F);
    descriptors.create(storage.data.numPts, 128, CV_32F);
    for (int index = 0; index < storage.data.numPts; ++index) {
      const auto &point = storage.data.h_data[index];
      positions.at<float>(index, 0) = point.xpos;
      positions.at<float>(index, 1) = point.ypos;
      std::copy(std::begin(point.data), std::end(point.data), descriptors.ptr<float>(index));
    }
    backend = "CudaSift";
#else
    CompleteSIFT_GPU extractor;
    std::vector<cv::KeyPoint> points;
    if (!extractor.initialize() || !extractor.detectAndCompute(gray, points, descriptors))
      throw std::runtime_error("Complete GPU reference extraction failed");
    positions.create(static_cast<int>(points.size()), 2, CV_32F);
    for (size_t index = 0; index < points.size(); ++index) {
      positions.at<float>(static_cast<int>(index), 0) = points[index].pt.x;
      positions.at<float>(static_cast<int>(index), 1) = points[index].pt.y;
    }
    capacity = 10000;
    backend = "complete-gpu-sift";
#endif
    if (positions.empty()) {
      positions = cv::Mat(0, 2, CV_32F);
      descriptors = cv::Mat(0, 128, CV_32F);
    }
    cv::FileStorage output(argv[2], cv::FileStorage::WRITE | cv::FileStorage::FORMAT_JSON);
    if (!output.isOpened()) throw std::runtime_error("Cannot write reference features");
    output << "backend" << backend << "image" << argv[1]
           << "width" << gray.cols << "height" << gray.rows
           << "capacity" << capacity << "capacity_reached" << static_cast<int>(positions.rows >= capacity)
           << "parameters_equivalent" << 0 << "positions" << positions << "descriptors" << descriptors;
#ifdef SIFT_VALIDATE_CUDA
    cudaDeviceProp properties{};
    int driver_version = 0;
    if (cudaGetDeviceProperties(&properties, 0) != cudaSuccess ||
        cudaDriverGetVersion(&driver_version) != cudaSuccess)
      throw std::runtime_error("Cannot query CUDA reference device metadata");
    output << "device" << properties.name << "cuda_driver_api_version" << driver_version
           << "cuda_compile_version" << CUDART_VERSION << "octaves" << 4
           << "initial_blur" << 1.0 << "contrast" << 3.0 << "scale_up" << 0;
#endif
  } catch (const std::exception &error) {
    std::cerr << "Reference export failed: " << error.what() << '\n';
    return 1;
  }
  return 0;
}