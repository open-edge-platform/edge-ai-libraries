#include "opencl_extrema.hpp"

#ifdef SIFT_VALIDATE_SYCL
#include "syclSift.h"
#endif

#include <opencv2/core.hpp>
#include <opencv2/core/ocl.hpp>
#include <opencv2/features2d.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>

#include <algorithm>
#include <charconv>
#include <chrono>
#include <cmath>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <vector>

namespace {

struct FeatureSet {
  std::vector<cv::Point2f> positions;
  cv::Mat descriptors;
};

#ifdef SIFT_VALIDATE_SYCL
struct SyclStorage {
  SiftData data{};
  float *temporary = nullptr;
  ~SyclStorage() {
    if (temporary) FreeSiftTempMemory(temporary);
    FreeSiftData(data);
  }
};

FeatureSet extract_sycl(const cv::Mat &gray) {
  cv::Mat pixels;
  gray.convertTo(pixels, CV_32F);
  SyclImage image;
  image.Allocate(gray.cols, gray.rows, iAlignUp(gray.cols, 128), false,
                 nullptr, pixels.ptr<float>());
  image.Download();
  SyclStorage storage;
  InitSiftData(storage.data, 32768, true, true);
  storage.temporary = AllocSiftTempMemory(gray.cols, gray.rows, 4, false);
  if (!storage.temporary) throw std::runtime_error("SYCL scratch allocation failed");
  ExtractSift(storage.data, image, 4, 1.0, 3.0f, 0.0f, false, storage.temporary);
  GetSyclQueue().wait_and_throw();
  if (storage.data.numPts < 0 || storage.data.numPts >= storage.data.maxPts)
    throw std::runtime_error("SYCL feature output reached capacity or is invalid");
  FeatureSet result;
  result.descriptors.create(storage.data.numPts, 128, CV_32F);
  for (int index = 0; index < storage.data.numPts; ++index) {
    const auto &point = storage.data.h_data[index];
    if (!std::isfinite(point.xpos) || !std::isfinite(point.ypos))
      throw std::runtime_error("SYCL keypoint is not finite");
    result.positions.emplace_back(point.xpos, point.ypos);
    double norm_squared = 0.0;
    for (float value : point.data) {
      if (!std::isfinite(value)) throw std::runtime_error("SYCL descriptor is not finite");
      norm_squared += static_cast<double>(value) * value;
    }
    if (norm_squared <= 0.0) throw std::runtime_error("SYCL descriptor is zero");
    std::copy(std::begin(point.data), std::end(point.data),
              result.descriptors.ptr<float>(index));
  }
  return result;
}
#endif

FeatureSet extract_opencl(sift_extractor::detail::OpenCLDoGExtrema &extractor,
                          const cv::Mat &gray) {
  std::vector<float> pixels(static_cast<size_t>(gray.rows) * gray.cols);
  for (int row = 0; row < gray.rows; ++row) {
    for (int column = 0; column < gray.cols; ++column)
      pixels[static_cast<size_t>(row) * gray.cols + column] =
          static_cast<float>(gray.at<unsigned char>(row, column));
  }
  const auto features = extractor.extract_image(pixels, gray.cols, gray.rows,
                                                 4, 3, 1.6f, 1.0f, 12.1f);
  FeatureSet result;
  result.descriptors.create(static_cast<int>(features.size()), 128, CV_32F);
  for (size_t index = 0; index < features.size(); ++index) {
    result.positions.emplace_back(features[index].point.keypoint.image_x,
                                   features[index].point.keypoint.image_y);
    std::copy(features[index].descriptor.begin(), features[index].descriptor.end(),
               result.descriptors.ptr<float>(static_cast<int>(index)));
  }
  return result;
}

FeatureSet extract_opencv(const cv::Mat &gray) {
  const auto sift = cv::SIFT::create();
  std::vector<cv::KeyPoint> keypoints;
  FeatureSet result;
  sift->detectAndCompute(gray, cv::noArray(), keypoints, result.descriptors);
  for (const auto &point : keypoints) result.positions.push_back(point.pt);
  return result;
}

void report(cv::FileStorage &output, const char *name, const FeatureSet &first,
            const FeatureSet &second, const cv::Mat &affine) {
  int accepted = 0;
  int inliers = 0;
  double squared_error_sum = 0.0;
  if (!first.descriptors.empty() && second.descriptors.rows >= 2) {
    std::vector<std::vector<cv::DMatch>> neighbors;
    cv::BFMatcher(cv::NORM_L2).knnMatch(first.descriptors, second.descriptors,
                                       neighbors, 2);
    for (const auto &pair : neighbors) {
      if (pair.size() < 2 || pair[0].distance >= 0.8f * pair[1].distance) continue;
      ++accepted;
      const auto &source = first.positions[static_cast<size_t>(pair[0].queryIdx)];
      const auto &target = second.positions[static_cast<size_t>(pair[0].trainIdx)];
      const double projected_x = affine.at<double>(0, 0) * source.x +
                                  affine.at<double>(0, 1) * source.y + affine.at<double>(0, 2);
      const double projected_y = affine.at<double>(1, 0) * source.x +
                                  affine.at<double>(1, 1) * source.y + affine.at<double>(1, 2);
      const double error_x = target.x - projected_x;
      const double error_y = target.y - projected_y;
      const double squared_error = error_x * error_x + error_y * error_y;
      if (squared_error <= 9.0) {
        ++inliers;
        squared_error_sum += squared_error;
      }
    }
  }
  output << name << "{" << "first_features" << static_cast<int>(first.positions.size())
         << "second_features" << static_cast<int>(second.positions.size())
         << "ratio_matches" << accepted << "ground_truth_inliers_3px" << inliers
         << "inlier_fraction" << (accepted ? static_cast<double>(inliers) / accepted : 0.0)
         << "inlier_rmse_px" << (inliers ? std::sqrt(squared_error_sum / inliers) : -1.0)
         << "}";
}

#ifdef SIFT_VALIDATE_SYCL
double report_latency(cv::FileStorage &output, const char *name,
                      std::vector<double> samples) {
  output << name << "{" << "samples_ms" << samples;
  std::sort(samples.begin(), samples.end());
  const size_t middle = samples.size() / 2;
  const double median = samples.size() % 2 ? samples[middle] :
      (samples[middle - 1] + samples[middle]) * 0.5;
  output << "median_ms" << median << "min_ms" << samples.front()
         << "max_ms" << samples.back() << "}";
  return median;
}
#endif

} // namespace

int main(int argc, char **argv) {
  if (argc < 2 || argc > 4) {
    std::cerr << "Usage: validate_sift_pair <image> [output.json [timing-iterations]]\n";
    return 2;
  }
  try {
    int timing_iterations = 0;
    if (argc == 4) {
#ifndef SIFT_VALIDATE_SYCL
      throw std::runtime_error("Timing comparison requires both OpenCL and SYCL");
#else
      const auto parsed = std::from_chars(argv[3], argv[3] + std::strlen(argv[3]),
                                           timing_iterations);
      if (parsed.ec != std::errc{} || *parsed.ptr != '\0' ||
          timing_iterations < 1 || timing_iterations > 100)
        throw std::runtime_error("Timing iterations must be an integer from 1 to 100");
#endif
    }
    cv::ocl::setUseOpenCL(false);
    cv::Mat first = cv::imread(argv[1], cv::IMREAD_GRAYSCALE);
    if (first.empty()) throw std::runtime_error("Cannot read input image");
    if (first.cols > 640 || first.rows > 480) {
      const double factor = std::min(640.0 / first.cols, 480.0 / first.rows);
      cv::resize(first, first, cv::Size(), factor, factor, cv::INTER_AREA);
    }
    const cv::Mat affine = cv::getRotationMatrix2D(
        cv::Point2f((first.cols - 1) * 0.5f, (first.rows - 1) * 0.5f), 30.0, 0.85);
    cv::Mat second;
    cv::warpAffine(first, second, affine, first.size(), cv::INTER_LINEAR,
                     cv::BORDER_CONSTANT);
#ifdef SIFT_VALIDATE_SYCL
    InitSycl(0);
    const auto sycl_device = GetSyclQueue().get_device();
    if (!sycl_device.is_gpu() ||
        sycl_device.get_info<sycl::info::device::vendor_id>() != 0x8086)
      throw std::runtime_error("Comparison requires an Intel GPU, not CPU fallback");
    const auto first_sycl = extract_sycl(first);
    const auto second_sycl = extract_sycl(second);
#endif
    sift_extractor::detail::OpenCLDoGExtrema extractor;
    const auto first_opencl = extract_opencl(extractor, first);
    const auto second_opencl = extract_opencl(extractor, second);
    const auto first_opencv = extract_opencv(first);
    const auto second_opencv = extract_opencv(second);
#ifdef SIFT_VALIDATE_SYCL
    std::vector<double> opencl_samples;
    std::vector<double> sycl_samples;
    std::vector<double> cpu_samples;
    if (timing_iterations) {
      const auto measure = [&](int backend) {
        const auto start = std::chrono::steady_clock::now();
        const auto features = backend == 0 ? extract_opencl(extractor, first) :
            backend == 1 ? extract_sycl(first) : extract_opencv(first);
        const auto end = std::chrono::steady_clock::now();
        const auto expected = backend == 0 ? first_opencl.positions.size() :
            backend == 1 ? first_sycl.positions.size() : first_opencv.positions.size();
        if (features.positions.size() != expected)
          throw std::runtime_error("Feature count changed during timing repetitions");
        return std::chrono::duration<double, std::milli>(end - start).count();
      };
      for (int iteration = -3; iteration < timing_iterations; ++iteration) {
        double samples[3]{};
        for (int offset = 0; offset < 3; ++offset) {
          const int backend = (iteration + 3 + offset) % 3;
          samples[backend] = measure(backend);
        }
        if (iteration >= 0) {
          opencl_samples.push_back(samples[0]);
          sycl_samples.push_back(samples[1]);
          cpu_samples.push_back(samples[2]);
        }
      }
    }
#endif
    cv::FileStorage output(argc >= 3 ? argv[2] : ".json", cv::FileStorage::WRITE |
      (argc == 2 ? cv::FileStorage::MEMORY : 0) | cv::FileStorage::FORMAT_JSON);
    if (!output.isOpened()) throw std::runtime_error("Cannot open JSON report");
    output << "diagnostic_only" << 1 << "cuda_reference_available" << 0
           << "performance_measured" << (timing_iterations ? 1 : 0)
           << "release_performance_gate" << 0 << "parameters_equivalent" << 0
           << "input" << argv[1] << "width" << first.cols << "height" << first.rows
          << "rotation_degrees" << 30.0 << "scale_factor" << 0.85
          << "prototype_octaves" << 4 << "prototype_intervals" << 3
          << "prototype_base_sigma" << 1.6 << "prototype_contrast" << 1.0
          << "prototype_hessian_ratio_limit" << 12.1
          << "reference" << "OpenCV CPU SIFT defaults"
          << "reference_opencv_version" << CV_VERSION
          << "cpu_threads" << cv::getNumThreads()
          << "cpu_optimized_code_enabled" << static_cast<int>(cv::useOptimized())
          << "ratio_threshold" << 0.8 << "inlier_threshold_px" << 3.0;
    report(output, "opencl_prototype", first_opencl, second_opencl, affine);
  #ifdef SIFT_VALIDATE_SYCL
    output << "sycl_device" << sycl_device.get_info<sycl::info::device::name>()
         << "sycl_driver" << sycl_device.get_info<sycl::info::device::driver_version>()
           << "sycl_compute_units" << static_cast<int>(sycl_device.get_info<sycl::info::device::max_compute_units>())
           << "sycl_max_clock_mhz" << static_cast<int>(sycl_device.get_info<sycl::info::device::max_clock_frequency>())
         << "sycl_octaves" << 4 << "sycl_init_blur" << 1.0
         << "sycl_contrast" << 3.0 << "sycl_scale_up" << 0
         << "sycl_capacity" << 32768;
    report(output, "sycl_reference", first_sycl, second_sycl, affine);
    if (timing_iterations) {
      output << "timing" << "{" << "iterations" << timing_iterations
              << "warmups_per_backend" << 3 << "rotating_backend_order" << 1
             << "scope" << "single_image_conversion_allocation_per_call_setup_transfers_extract_host_descriptors_and_logging"
                  << "excludes" << "image_io_transform_matching_and_initial_gpu_detector_construction"
             << "tops_normalization" << "not_applied_precision_and_bandwidth_unverified";
                const double opencl_ms = report_latency(output, "opencl", opencl_samples);
                const double sycl_ms = report_latency(output, "sycl", sycl_samples);
                const double cpu_ms = report_latency(output, "opencv_cpu", cpu_samples);
                output << "cpu_over_opencl_latency_ratio" << cpu_ms / opencl_ms
                  << "cpu_over_sycl_latency_ratio" << cpu_ms / sycl_ms
                  << "speedup_quality_qualified" << 0;
      output << "}";
    }
  #endif
    report(output, "opencv_cpu_default", first_opencv, second_opencv, affine);
    if (argc == 2) std::cout << output.releaseAndGetString() << '\n';
  } catch (const std::exception &error) {
    std::cerr << "Validation failed: " << error.what() << '\n';
    return 1;
  }
  return 0;
}