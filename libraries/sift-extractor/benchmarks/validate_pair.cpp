// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#include "opencl_extrema.hpp"

#ifdef SIFT_VALIDATE_SYCL
#include "syclSift.h"
#include "sift_extractor/sycl_extractor.hpp"
#endif

#include <opencv2/core.hpp>
#include <opencv2/core/ocl.hpp>
#include <opencv2/features2d.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>

#include <algorithm>
#include <array>
#include <charconv>
#include <chrono>
#include <cmath>
#include <cstring>
#include <filesystem>
#include <iostream>
#include <limits>
#include <numeric>
#include <set>
#include <stdexcept>
#include <vector>

namespace {

struct Configuration {
  int width = 0;
  int height = 0;
  int nfeatures = 0;
  int octave_layers = 3;
  double contrast = 0.04;
  double edge = 10.0;
  double sigma = 1.6;
  int cpu_threads = 1;
  int octaves = 4;
  double opencl_contrast = 1.0;
  double sycl_contrast = 3.0;
  double sycl_init_blur = 1.0;
  double rotation = 30.0;
  double scale = 0.85;
  double gain = 1.0;
  double bias = 0.0;
  double blur_sigma = 0.0;
};

Configuration load_configuration(const char *path) {
  Configuration config;
  if (!path) return config;
  cv::FileStorage input(path, cv::FileStorage::READ | cv::FileStorage::FORMAT_JSON);
  if (!input.isOpened() || !input.root().isMap())
    throw std::runtime_error("Configuration must be a readable JSON object");
  const std::vector<std::string> keys = {"width", "height", "nfeatures",
      "nOctaveLayers", "contrastThreshold", "edgeThreshold", "sigma", "cpuThreads",
      "octaves", "openclContrast", "syclContrast", "syclInitBlur",
      "rotationDegrees", "scaleFactor", "gain", "bias", "blurSigma"};
  for (const auto &node : input.root()) {
    if (std::find(keys.begin(), keys.end(), node.name()) == keys.end())
      throw std::runtime_error("Unknown configuration key: " + node.name());
  }
  const auto number = [&](const char *name, double fallback, double low,
                          double high, bool integral = false) {
    const auto node = input[name];
    if (node.empty()) return fallback;
    if (!node.isInt() && !node.isReal())
      throw std::runtime_error(std::string("Configuration value must be numeric: ") + name);
    const double value = static_cast<double>(node);
    if (!std::isfinite(value) || value < low || value > high ||
        (integral && std::trunc(value) != value))
      throw std::runtime_error(std::string("Configuration value out of range: ") + name);
    return value;
  };
  config.width = static_cast<int>(number("width", 0, 32, 3840, true));
  config.height = static_cast<int>(number("height", 0, 32, 2160, true));
  if ((config.width == 0) != (config.height == 0))
    throw std::runtime_error("Set both width and height, or neither");
  config.nfeatures = static_cast<int>(number("nfeatures", 0, 0, 16000, true));
  config.octave_layers = static_cast<int>(number("nOctaveLayers", 3, 1, 6, true));
  config.contrast = number("contrastThreshold", 0.04, 0.00001, 0.2);
  config.edge = number("edgeThreshold", 10, 1, 30);
  config.sigma = number("sigma", 1.6, 0.5, 3.0);
  config.cpu_threads = static_cast<int>(number("cpuThreads", 1, 1, 128, true));
  config.octaves = static_cast<int>(number("octaves", 4, 1, 6, true));
  config.opencl_contrast = number("openclContrast", 1.0, 0.01, 20.0);
  config.sycl_contrast = number("syclContrast", 3.0, 0.01, 20.0);
  config.sycl_init_blur = number("syclInitBlur", 1.0, 0.2, 3.0);
  config.rotation = number("rotationDegrees", 30.0, -180.0, 180.0);
  config.scale = number("scaleFactor", 0.85, 0.25, 2.0);
  config.gain = number("gain", 1.0, 0.25, 2.0);
  config.bias = number("bias", 0.0, -64.0, 64.0);
  config.blur_sigma = number("blurSigma", 0.0, 0.0, 4.0);
  return config;
}

struct FeatureSet {
  std::vector<cv::Point2f> positions;
  std::vector<float> responses;
  std::vector<double> stage_ms;
  cv::Mat descriptors;
};

FeatureSet limit_features(FeatureSet features, int limit) {
  if (!limit || features.positions.size() <= static_cast<size_t>(limit)) return features;
  std::vector<size_t> order(features.positions.size());
  std::iota(order.begin(), order.end(), 0);
  std::stable_sort(order.begin(), order.end(), [&](size_t first, size_t second) {
    return features.responses[first] > features.responses[second];
  });
  FeatureSet selected;
  selected.descriptors.create(limit, 128, CV_32F);
  for (int index = 0; index < limit; ++index) {
    const size_t source = order[static_cast<size_t>(index)];
    selected.positions.push_back(features.positions[source]);
    selected.responses.push_back(features.responses[source]);
    features.descriptors.row(static_cast<int>(source)).copyTo(selected.descriptors.row(index));
  }
  return selected;
}

#ifdef SIFT_VALIDATE_SYCL
struct SyclStorage {
  SiftData data{};
  float *temporary = nullptr;
  int width = 0;
  int height = 0;
  int octaves = 0;
  SyclStorage() = default;
  SyclStorage(const SyclStorage &) = delete;
  SyclStorage &operator=(const SyclStorage &) = delete;
  void prepare(int image_width, int image_height, int octave_count) {
    if (temporary) {
      if (width != image_width || height != image_height || octaves != octave_count)
        throw std::runtime_error("SYCL workspace shape or octave count changed");
      return;
    }
    width = image_width;
    height = image_height;
    octaves = octave_count;
    InitSiftData(data, 32768, true, true);
    if (!data.h_data || !data.d_data)
      throw std::runtime_error("SYCL feature allocation failed");
    temporary = AllocSiftTempMemory(width, height, octaves, false);
    if (!temporary) throw std::runtime_error("SYCL scratch allocation failed");
  }
  void release() {
    if (temporary) FreeSiftTempMemory(temporary);
    temporary = nullptr;
    FreeSiftData(data);
  }
  ~SyclStorage() { release(); }
};

FeatureSet extract_sycl(const cv::Mat &gray, const Configuration &config,
                        SyclStorage *workspace = nullptr) {
  const auto started = std::chrono::steady_clock::now();
  auto previous = started;
  std::vector<double> stages;
  const auto mark = [&] {
    const auto now = std::chrono::steady_clock::now();
    stages.push_back(std::chrono::duration<double, std::milli>(now - previous).count());
    previous = now;
  };
  cv::Mat pixels;
  gray.convertTo(pixels, CV_32F);
  mark();
  FeatureSet result;
  {
  SyclImage image;
  image.Allocate(gray.cols, gray.rows, iAlignUp(gray.cols, 128), false,
                 nullptr, pixels.ptr<float>());
  image.Download();
  mark();
  SyclStorage per_call_storage;
  SyclStorage &storage = workspace ? *workspace : per_call_storage;
  storage.prepare(gray.cols, gray.rows, config.octaves);
  mark();
  ExtractSift(storage.data, image, config.octaves, config.sycl_init_blur,
              static_cast<float>(config.sycl_contrast), 0.0f, false, storage.temporary);
  GetSyclQueue().wait_and_throw();
  mark();
  if (storage.data.numPts < 0 || storage.data.numPts >= storage.data.maxPts)
    throw std::runtime_error("SYCL feature output reached capacity or is invalid");
  result.descriptors.create(storage.data.numPts, 128, CV_32F);
  for (int index = 0; index < storage.data.numPts; ++index) {
    const auto &point = storage.data.h_data[index];
    if (!std::isfinite(point.xpos) || !std::isfinite(point.ypos))
      throw std::runtime_error("SYCL keypoint is not finite");
    result.positions.emplace_back(point.xpos, point.ypos);
    result.responses.push_back(std::abs(point.sharpness));
    double norm_squared = 0.0;
    for (float value : point.data) {
      if (!std::isfinite(value)) throw std::runtime_error("SYCL descriptor is not finite");
      norm_squared += static_cast<double>(value) * value;
    }
    if (norm_squared <= 0.0) throw std::runtime_error("SYCL descriptor is zero");
    std::copy(std::begin(point.data), std::end(point.data),
              result.descriptors.ptr<float>(index));
  }
  result = limit_features(std::move(result), config.nfeatures);
  mark();
  }
  mark();
  result.stage_ms = std::move(stages);
  return result;
}

FeatureSet extract_context(const cv::Mat &gray, const Configuration &config,
    sift_extractor::SyclExtractor &context) {
  const auto start = std::chrono::steady_clock::now();
  cv::Mat pixels;
  gray.convertTo(pixels, CV_32F);
  const auto converted = std::chrono::steady_clock::now();
  const auto features = context.extract(pixels.ptr<float>(), pixels.total());
  const auto extracted = std::chrono::steady_clock::now();
  FeatureSet result;
  result.descriptors.create(static_cast<int>(features.size()), 128, CV_32F);
  for (std::size_t index = 0; index < features.size(); ++index) {
    const auto &point = features[index];
    result.positions.emplace_back(point.x, point.y);
    result.responses.push_back(std::abs(point.response));
    std::copy(point.descriptor.begin(), point.descriptor.end(),
              result.descriptors.ptr<float>(static_cast<int>(index)));
  }
  result = limit_features(std::move(result), config.nfeatures);
  const auto selected = std::chrono::steady_clock::now();
  result.stage_ms = {
      std::chrono::duration<double, std::milli>(converted - start).count(),
      std::chrono::duration<double, std::milli>(extracted - converted).count(),
      std::chrono::duration<double, std::milli>(selected - extracted).count()};
  return result;
}
#endif

FeatureSet extract_opencl(sift_extractor::detail::OpenCLDoGExtrema &extractor,
                          const cv::Mat &gray, const Configuration &config) {
  std::vector<float> pixels(static_cast<size_t>(gray.rows) * gray.cols);
  for (int row = 0; row < gray.rows; ++row) {
    for (int column = 0; column < gray.cols; ++column)
      pixels[static_cast<size_t>(row) * gray.cols + column] =
          static_cast<float>(gray.at<unsigned char>(row, column));
  }
  const auto features = extractor.extract_image(pixels, gray.cols, gray.rows,
                                  config.octaves, config.octave_layers, static_cast<float>(config.sigma),
                                  static_cast<float>(config.opencl_contrast),
                                  static_cast<float>((config.edge + 1) * (config.edge + 1) / config.edge),
                                  config.nfeatures);
  FeatureSet result;
  result.descriptors.create(static_cast<int>(features.size()), 128, CV_32F);
  for (size_t index = 0; index < features.size(); ++index) {
    result.positions.emplace_back(features[index].point.keypoint.image_x,
                                   features[index].point.keypoint.image_y);
    result.responses.push_back(std::abs(features[index].point.keypoint.local.response));
    std::copy(features[index].descriptor.begin(), features[index].descriptor.end(),
               result.descriptors.ptr<float>(static_cast<int>(index)));
  }
  return limit_features(std::move(result), config.nfeatures);
}

FeatureSet extract_opencv(const cv::Mat &gray, const Configuration &config) {
  const auto sift = cv::SIFT::create(config.nfeatures, config.octave_layers,
                                   config.contrast, config.edge, config.sigma);
  std::vector<cv::KeyPoint> keypoints;
  FeatureSet result;
  sift->detectAndCompute(gray, cv::noArray(), keypoints, result.descriptors);
  for (const auto &point : keypoints) result.positions.push_back(point.pt);
  return result;
}

void report(cv::FileStorage &output, const char *name, const FeatureSet &first,
            const FeatureSet &second, const cv::Mat &transform) {
  int accepted = 0;
  int inliers = 0;
  int unprojectable = 0;
  double squared_error_sum = 0.0;
  double error_x_sum = 0.0;
  double error_y_sum = 0.0;
  std::set<std::array<float, 2>> inlier_first_positions, inlier_second_positions;
  const auto support = [](const FeatureSet &features) {
    std::set<std::array<float, 2>> positions;
    std::set<std::array<float, 130>> records;
    for (size_t index = 0; index < features.positions.size(); ++index) {
      const auto &point = features.positions[index];
      positions.insert({point.x, point.y});
      std::array<float, 130> record{point.x, point.y};
      std::copy_n(features.descriptors.ptr<float>(static_cast<int>(index)),
                  128, record.begin() + 2);
      records.insert(record);
    }
    return std::pair{static_cast<int>(positions.size()),
                     static_cast<int>(features.positions.size() - records.size())};
  };
  const auto first_support = support(first);
  const auto second_support = support(second);
  if (!first.descriptors.empty() && second.descriptors.rows >= 2) {
    std::vector<std::vector<cv::DMatch>> neighbors;
    cv::BFMatcher(cv::NORM_L2).knnMatch(first.descriptors, second.descriptors,
                                       neighbors, 2);
    for (const auto &pair : neighbors) {
      if (pair.size() < 2 || pair[0].distance >= 0.8f * pair[1].distance) continue;
      ++accepted;
      const auto &source = first.positions[static_cast<size_t>(pair[0].queryIdx)];
      const auto &target = second.positions[static_cast<size_t>(pair[0].trainIdx)];
      const double projected_x = transform.at<double>(0, 0) * source.x +
                            transform.at<double>(0, 1) * source.y + transform.at<double>(0, 2);
      const double projected_y = transform.at<double>(1, 0) * source.x +
                            transform.at<double>(1, 1) * source.y + transform.at<double>(1, 2);
      double error_x = target.x - projected_x;
      double error_y = target.y - projected_y;
      if (transform.rows == 3) {
        const double horizontal = transform.at<double>(2, 0) * source.x;
        const double vertical = transform.at<double>(2, 1) * source.y;
        const double constant = transform.at<double>(2, 2);
        const double divisor = horizontal + vertical + constant;
        const double tolerance = 8.0 * std::numeric_limits<double>::epsilon() *
            (std::abs(horizontal) + std::abs(vertical) + std::abs(constant));
        if (std::abs(divisor) <= tolerance) {
          ++unprojectable;
          continue;
        }
        const double normalized_x = projected_x / divisor;
        const double normalized_y = projected_y / divisor;
        if (!std::isfinite(normalized_x) || !std::isfinite(normalized_y)) {
          ++unprojectable;
          continue;
        }
        error_x = target.x - normalized_x;
        error_y = target.y - normalized_y;
      }
      const double squared_error = error_x * error_x + error_y * error_y;
      if (squared_error <= 9.0) {
        ++inliers;
        inlier_first_positions.insert({source.x, source.y});
        inlier_second_positions.insert({target.x, target.y});
        squared_error_sum += squared_error;
        error_x_sum += error_x;
        error_y_sum += error_y;
      }
    }
  }
  output << name << "{" << "first_features" << static_cast<int>(first.positions.size())
         << "second_features" << static_cast<int>(second.positions.size())
      << "first_distinct_positions" << first_support.first
      << "second_distinct_positions" << second_support.first
      << "first_duplicate_records" << first_support.second
      << "second_duplicate_records" << second_support.second
      << "inlier_distinct_first_positions" << static_cast<int>(inlier_first_positions.size())
      << "inlier_distinct_second_positions" << static_cast<int>(inlier_second_positions.size())
         << "ratio_matches" << accepted << "ground_truth_inliers_3px" << inliers
         << "unprojectable_ratio_matches" << unprojectable
         << "inlier_fraction" << (accepted ? static_cast<double>(inliers) / accepted : 0.0)
         << "inlier_rmse_px" << (inliers ? std::sqrt(squared_error_sum / inliers) : -1.0)
         << "inlier_mean_dx_px" << (inliers ? error_x_sum / inliers : 0.0)
         << "inlier_mean_dy_px" << (inliers ? error_y_sum / inliers : 0.0)
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

FeatureSet read_external(const char *path, int width, int height) {
  if (std::filesystem::file_size(path) > 256 * 1024 * 1024)
    throw std::runtime_error("External feature file exceeds 256 MiB");
  cv::FileStorage input(path, cv::FileStorage::READ);
  if (!input.isOpened() || static_cast<int>(input["width"]) != width ||
      static_cast<int>(input["height"]) != height)
    throw std::runtime_error("External feature image dimensions do not match pair");
  const auto point_node = input["positions"];
  const auto descriptor_node = input["descriptors"];
  const int count = static_cast<int>(point_node["rows"]);
  if (count < 0 || count > 32768 || static_cast<int>(point_node["cols"]) != 2 ||
      static_cast<int>(descriptor_node["rows"]) != count ||
      static_cast<int>(descriptor_node["cols"]) != 128)
    throw std::runtime_error("Invalid external feature matrix dimensions");
  cv::Mat positions;
  FeatureSet result;
  point_node >> positions;
  descriptor_node >> result.descriptors;
  if (count == 0) return result;
  if (positions.type() != CV_32F || result.descriptors.type() != CV_32F ||
      !cv::checkRange(positions) || !cv::checkRange(result.descriptors))
    throw std::runtime_error("External features must contain finite float32 values");
  for (int index = 0; index < count; ++index) {
    const float horizontal = positions.at<float>(index, 0);
    const float vertical = positions.at<float>(index, 1);
    if (horizontal < 0 || horizontal >= width || vertical < 0 || vertical >= height ||
        cv::norm(result.descriptors.row(index), cv::NORM_L2) <= 0.0)
      throw std::runtime_error("External feature is out of bounds or has a zero descriptor");
    result.positions.emplace_back(horizontal, vertical);
  }
  return result;
}

int export_features(char **argv) {
  const std::string backend = argv[5];
  if (backend != "opencl" && backend != "opencv" && backend != "sycl")
    throw std::runtime_error("Feature export backend must be opencl, opencv or sycl");
#ifndef SIFT_VALIDATE_SYCL
  if (backend == "sycl") throw std::runtime_error("SYCL export is not enabled");
#endif
  const auto config = load_configuration(argv[4]);
  if (config.width || config.height)
    throw std::runtime_error("Feature export does not resize; preprocess images and geometry explicitly");
  cv::setNumThreads(config.cpu_threads);
  cv::ocl::setUseOpenCL(false);
  const cv::Mat image = cv::imread(argv[2], cv::IMREAD_GRAYSCALE);
  if (image.empty() || image.cols > 3840 || image.rows > 2160)
    throw std::runtime_error("Export image must be readable and at most 3840x2160");
  FeatureSet features;
  if (backend == "opencl") {
    sift_extractor::detail::OpenCLDoGExtrema extractor;
    features = extract_opencl(extractor, image, config);
  } else if (backend == "opencv") {
    features = extract_opencv(image, config);
  }
#ifdef SIFT_VALIDATE_SYCL
  else {
    sift_extractor::SyclExtractorOptions options;
    options.octaves = config.octaves;
    options.initial_blur = config.sycl_init_blur;
    options.contrast_threshold = static_cast<float>(config.sycl_contrast);
    sift_extractor::SyclExtractor context(image.cols, image.rows, options);
    features = extract_context(image, config, context);
  }
#endif
  if (features.positions.size() > 32768)
    throw std::runtime_error("Feature export exceeds scorer capacity; no records were truncated");
  cv::Mat positions(static_cast<int>(features.positions.size()), 2, CV_32F);
  for (size_t index = 0; index < features.positions.size(); ++index) {
    positions.at<float>(static_cast<int>(index), 0) = features.positions[index].x;
    positions.at<float>(static_cast<int>(index), 1) = features.positions[index].y;
  }
  if (features.positions.empty()) features.descriptors = cv::Mat(0, 128, CV_32F);
  if (features.descriptors.rows != positions.rows || features.descriptors.cols != 128 ||
      features.descriptors.type() != CV_32F)
    throw std::runtime_error("Invalid exported descriptor matrix");
  for (int index = 0; index < positions.rows; ++index) {
    const auto &point = features.positions[static_cast<size_t>(index)];
    if (!std::isfinite(point.x) || !std::isfinite(point.y) || point.x < 0 ||
        point.x >= image.cols || point.y < 0 || point.y >= image.rows ||
        !cv::checkRange(features.descriptors.row(index)) ||
        cv::norm(features.descriptors.row(index), cv::NORM_L2) <= 0.0)
      throw std::runtime_error("Invalid exported feature position or descriptor");
  }
  cv::FileStorage output(argv[3], cv::FileStorage::WRITE | cv::FileStorage::FORMAT_JSON);
  if (!output.isOpened()) throw std::runtime_error("Cannot write feature export");
  output << "diagnostic_only" << 1 << "backend" << backend << "input" << argv[2]
         << "configuration_file" << argv[4] << "width" << image.cols << "height" << image.rows
         << "resized" << 0 << "feature_limit" << config.nfeatures
         << "parameters_equivalent" << 0 << "capacity" << 32768
         << "octaves_automatic" << static_cast<int>(backend == "opencv")
         << "sycl_layers_fixed" << 5 << "sycl_scale_up" << 0
         << "octaves" << config.octaves << "intervals" << config.octave_layers
         << "sigma" << config.sigma << "opencl_contrast" << config.opencl_contrast
         << "sycl_initial_blur" << config.sycl_init_blur << "sycl_contrast" << config.sycl_contrast
         << "opencv_contrast" << config.contrast << "edge_threshold" << config.edge
         << "positions" << positions << "descriptors" << features.descriptors;
  return 0;
}

int score_external(char **argv) {
  if (std::filesystem::file_size(argv[4]) > 1024 * 1024)
    throw std::runtime_error("Pair report exceeds 1 MiB");
  cv::FileStorage pair(argv[4], cv::FileStorage::READ);
  if (!pair.isOpened()) throw std::runtime_error("Cannot read pair report");
  const int width = static_cast<int>(pair["width"]);
  const int height = static_cast<int>(pair["height"]);
  if (width <= 0 || width > 3840 || height <= 0 || height > 2160)
    throw std::runtime_error("Invalid pair dimensions");
  const bool projective = !pair["homography"].empty();
  if (projective == !pair["affine"].empty())
    throw std::runtime_error("Pair requires exactly one affine or homography transform");
  const auto node = pair[projective ? "homography" : "affine"];
  const int rows = projective ? 3 : 2;
  if (!node.isMap() || !node["rows"].isInt() || !node["cols"].isInt() ||
      static_cast<int>(node["rows"]) != rows || static_cast<int>(node["cols"]) != 3 ||
      !node["dt"].isString() || static_cast<std::string>(node["dt"]) != "d" ||
      !node["data"].isSeq() || node["data"].size() != static_cast<size_t>(rows * 3))
    throw std::runtime_error("Invalid pair transform matrix shape or type");
  cv::Mat transform;
  node >> transform;
  if (transform.rows != rows || transform.cols != 3 || transform.type() != CV_64F ||
      !cv::checkRange(transform))
    throw std::runtime_error("Pair transform must contain finite float64 values");
  if (projective) {
    const double coefficient_norm = cv::norm(transform, cv::NORM_INF);
    if (coefficient_norm == 0.0) throw std::runtime_error("Zero homography");
    transform /= coefficient_norm;
    if (!cv::checkRange(transform))
      throw std::runtime_error("Homography normalization exceeds numeric range");
    cv::Mat singular_values;
    cv::SVD::compute(transform, singular_values);
    if (singular_values.at<double>(2) <=
        3.0 * std::numeric_limits<double>::epsilon() * singular_values.at<double>(0))
      throw std::runtime_error("Numerically singular homography");
  }
  const auto first = read_external(argv[2], width, height);
  const auto second = read_external(argv[3], width, height);
  cv::FileStorage output(argv[5], cv::FileStorage::WRITE | cv::FileStorage::FORMAT_JSON);
  if (!output.isOpened()) throw std::runtime_error("Cannot write external quality report");
  output << "diagnostic_only" << 1 << "parameters_equivalent" << 0
         << "pair_report" << argv[4] << "first_features_file" << argv[2]
         << "second_features_file" << argv[3] << "ratio_threshold" << 0.8
          << "inlier_threshold_px" << 3.0
          << "geometry_model" << (projective ? "homography" : "affine");
        report(output, "quality", first, second, transform);
  return 0;
}

} // namespace

int main(int argc, char **argv) {
  if (argc < 2 || argc > 6) {
    std::cerr << "Usage: validate_sift_pair <image> [output.json [iterations [config.json [sycl-only|sycl-reuse|sycl-context|all-context|opencl-only|quality-export]]]]\n"
          << "  --export-features IMAGE OUTPUT CONFIG opencl|sycl|opencv\n"
          << "  --score-external FIRST SECOND GEOMETRY OUTPUT\n";
    return 2;
  }
  try {
    if (argc == 6 && std::strcmp(argv[1], "--export-features") == 0)
      return export_features(argv);
    if (argc == 6 && std::strcmp(argv[1], "--score-external") == 0)
      return score_external(argv);
    const bool quality_export = argc == 6 && std::strcmp(argv[5], "quality-export") == 0;
    int timing_iterations = 0;
    if (argc >= 4) {
#ifndef SIFT_VALIDATE_SYCL
      throw std::runtime_error("Timing comparison requires both OpenCL and SYCL");
#else
      const auto parsed = std::from_chars(argv[3], argv[3] + std::strlen(argv[3]),
                                           timing_iterations);
      if (parsed.ec != std::errc{} || *parsed.ptr != '\0' ||
          (quality_export ? timing_iterations != 0 : timing_iterations < 1 || timing_iterations > 100))
        throw std::runtime_error("Iterations must be 0 for quality-export, otherwise 1 to 100");
#endif
    }
    if (argc == 6 && std::strcmp(argv[5], "sycl-only") != 0 &&
        std::strcmp(argv[5], "sycl-reuse") != 0 && std::strcmp(argv[5], "sycl-context") != 0 &&
        std::strcmp(argv[5], "all-context") != 0 && std::strcmp(argv[5], "opencl-only") != 0 && !quality_export)
      throw std::runtime_error("Unsupported comparison mode");
    const bool opencl_only = argc == 6 && std::strcmp(argv[5], "opencl-only") == 0;
    const auto config = load_configuration(argc >= 5 ? argv[4] : nullptr);
    cv::setNumThreads(config.cpu_threads);
    cv::ocl::setUseOpenCL(false);
    cv::Mat first = cv::imread(argv[1], cv::IMREAD_GRAYSCALE);
    if (first.empty()) throw std::runtime_error("Cannot read input image");
    const cv::Size original_size = first.size();
    if (config.width) {
      cv::resize(first, first, cv::Size(config.width, config.height), 0, 0, cv::INTER_AREA);
    } else if (first.cols > 640 || first.rows > 480) {
      const double factor = std::min(640.0 / first.cols, 480.0 / first.rows);
      cv::resize(first, first, cv::Size(), factor, factor, cv::INTER_AREA);
    }
    const cv::Mat affine = cv::getRotationMatrix2D(
      cv::Point2f((first.cols - 1) * 0.5f, (first.rows - 1) * 0.5f), config.rotation, config.scale);
    cv::Mat second;
    cv::warpAffine(first, second, affine, first.size(), cv::INTER_LINEAR,
                     cv::BORDER_CONSTANT);
    if (config.blur_sigma > 0.0)
      cv::GaussianBlur(second, second, cv::Size(), config.blur_sigma);
    if (config.gain != 1.0 || config.bias != 0.0)
      second.convertTo(second, CV_8U, config.gain, config.bias);
    if (quality_export) {
      if (!cv::imwrite(std::string(argv[2]) + ".first.pgm", first) ||
          !cv::imwrite(std::string(argv[2]) + ".second.pgm", second))
        throw std::runtime_error("Cannot export quality image pair");
    }
#ifdef SIFT_VALIDATE_SYCL
    InitSycl(0);
    const auto sycl_device = GetSyclQueue().get_device();
    if (!sycl_device.is_gpu() ||
        sycl_device.get_info<sycl::info::device::vendor_id>() != 0x8086)
      throw std::runtime_error("Comparison requires an Intel GPU, not CPU fallback");
    const bool all_context = quality_export || (argc == 6 && std::strcmp(argv[5], "all-context") == 0);
    std::unique_ptr<sift_extractor::SyclExtractor> comparison_context;
    double context_setup_ms = 0.0;
    if (all_context) {
      const auto start = std::chrono::steady_clock::now();
      sift_extractor::SyclExtractorOptions options;
      options.octaves = config.octaves;
      options.initial_blur = config.sycl_init_blur;
      options.contrast_threshold = static_cast<float>(config.sycl_contrast);
      comparison_context = std::make_unique<sift_extractor::SyclExtractor>(first.cols, first.rows, options);
      context_setup_ms = std::chrono::duration<double, std::milli>(
          std::chrono::steady_clock::now() - start).count();
    }
    const auto comparison_sycl = [&](const cv::Mat &gray) {
      return comparison_context ? extract_context(gray, config, *comparison_context) : extract_sycl(gray, config);
    };
    const auto first_sycl = comparison_sycl(first);
    const auto second_sycl = comparison_sycl(second);
    if (argc == 6 && !all_context && !opencl_only) {
      const bool context_mode = std::strcmp(argv[5], "sycl-context") == 0;
      const bool reuse = std::strcmp(argv[5], "sycl-reuse") == 0 || context_mode;
      SyclStorage workspace;
      SyclStorage *retained = reuse ? &workspace : nullptr;
      std::unique_ptr<sift_extractor::SyclExtractor> context;
      const auto selected_extract = [&](const cv::Mat &gray) {
        return context ? extract_context(gray, config, *context) : extract_sycl(gray, config, retained);
      };
      FeatureSet reused_first;
      FeatureSet reused_second;
      double first_workspace_frame_ms = 0.0;
      if (reuse) {
        const auto start = std::chrono::steady_clock::now();
        if (context_mode) {
          sift_extractor::SyclExtractorOptions options;
          options.octaves = config.octaves;
          options.initial_blur = config.sycl_init_blur;
          options.contrast_threshold = static_cast<float>(config.sycl_contrast);
          context = std::make_unique<sift_extractor::SyclExtractor>(first.cols, first.rows, options);
        }
        reused_first = selected_extract(first);
        first_workspace_frame_ms = std::chrono::duration<double, std::milli>(
            std::chrono::steady_clock::now() - start).count();
        reused_second = selected_extract(second);
        const auto blank = selected_extract(cv::Mat::zeros(first.size(), CV_8U));
        if (!blank.positions.empty())
          throw std::runtime_error("Reused workspace retained features on a blank frame");
        reused_first = selected_extract(first);
        if (reused_first.positions.size() != first_sycl.positions.size() ||
            reused_second.positions.size() != second_sycl.positions.size())
          throw std::runtime_error("Workspace reuse changed feature counts");
      }
      std::vector<double> samples;
      std::vector<std::vector<double>> stage_samples(context_mode ? 3 : 6);
      for (int iteration = -3; iteration < timing_iterations; ++iteration) {
        const auto start = std::chrono::steady_clock::now();
        const auto features = selected_extract(first);
        const auto end = std::chrono::steady_clock::now();
        if (features.positions.size() != first_sycl.positions.size())
          throw std::runtime_error("Isolated SYCL feature count changed");
        if (iteration >= 0) {
          samples.push_back(std::chrono::duration<double, std::milli>(end - start).count());
          for (size_t stage = 0; stage < stage_samples.size(); ++stage)
            stage_samples[stage].push_back(features.stage_ms[stage]);
        }
      }
      cv::FileStorage isolated(argv[2], cv::FileStorage::WRITE | cv::FileStorage::FORMAT_JSON);
      if (!isolated.isOpened()) throw std::runtime_error("Cannot open isolated report");
        const auto release_start = std::chrono::steady_clock::now();
        workspace.release();
        context.reset();
        const double release_ms = std::chrono::duration<double, std::milli>(
          std::chrono::steady_clock::now() - release_start).count();
        isolated << "diagnostic_only" << 1 << "mode" << argv[5]
               << "device" << sycl_device.get_info<sycl::info::device::name>()
               << "width" << first.cols << "height" << first.rows
               << "iterations" << timing_iterations << "warmups" << 3
               << "logging_included" << 1 << "workspace_reused" << static_cast<int>(reuse)
               << "steady_state_excludes_workspace_setup_and_release" << static_cast<int>(reuse)
               << "first_workspace_frame_ms" << first_workspace_frame_ms
               << "workspace_release_ms" << release_ms
               << "blank_then_textured_reuse_checked" << static_cast<int>(reuse)
               << "first_workspace_frame_excludes_process_and_queue_initialization" << 1;
      report_latency(isolated, "end_to_end", samples);
      const char *names[] = {"float_conversion", "image_allocation_and_upload",
          "feature_and_scratch_allocation", "extract_and_wait",
          "host_descriptor_validation_and_selection", "cleanup"};
      const char *context_names[] = {"float_conversion", "context_extract_and_host_output",
                                     "feature_selection_and_adapter"};
      for (size_t stage = 0; stage < stage_samples.size(); ++stage)
        report_latency(isolated, context_mode ? context_names[stage] : names[stage], stage_samples[stage]);
            report(isolated, "quality", reuse ? reused_first : first_sycl,
              reuse ? reused_second : second_sycl, affine);
            if (reuse) report(isolated, "per_call_quality", first_sycl, second_sycl, affine);
      return 0;
    }
#endif
    sift_extractor::detail::OpenCLDoGExtrema extractor;
    const auto first_opencl = extract_opencl(extractor, first, config);
    const auto second_opencl = extract_opencl(extractor, second, config);
    const auto first_opencv = extract_opencv(first, config);
    const auto second_opencv = extract_opencv(second, config);
#ifdef SIFT_VALIDATE_SYCL
    std::vector<double> opencl_samples;
    std::vector<double> sycl_samples;
    std::vector<double> cpu_samples;
    if (timing_iterations) {
      const auto measure = [&](int backend) {
        const auto start = std::chrono::steady_clock::now();
        const auto features = backend == 0 ? extract_opencl(extractor, first, config) :
          backend == 1 ? comparison_sycl(first) : extract_opencv(first, config);
        const auto end = std::chrono::steady_clock::now();
        const auto expected = backend == 0 ? first_opencl.positions.size() :
            backend == 1 ? first_sycl.positions.size() : first_opencv.positions.size();
        if (features.positions.size() != expected)
          throw std::runtime_error("Feature count changed during timing repetitions");
        return std::chrono::duration<double, std::milli>(end - start).count();
      };
      for (int iteration = -3; iteration < timing_iterations; ++iteration) {
        double samples[3]{};
        for (int offset = 0; offset < (opencl_only ? 1 : 3); ++offset) {
          const int backend = opencl_only ? 0 : (iteration + 3 + offset) % 3;
          samples[backend] = measure(backend);
        }
        if (iteration >= 0) {
          opencl_samples.push_back(samples[0]);
          if (!opencl_only) {
            sycl_samples.push_back(samples[1]);
            cpu_samples.push_back(samples[2]);
          }
        }
      }
    }
    const auto context_release_start = std::chrono::steady_clock::now();
    comparison_context.reset();
    const double context_release_ms = std::chrono::duration<double, std::milli>(
      std::chrono::steady_clock::now() - context_release_start).count();
#endif
    cv::FileStorage output(argc >= 3 ? argv[2] : ".json", cv::FileStorage::WRITE |
      (argc == 2 ? cv::FileStorage::MEMORY : 0) | cv::FileStorage::FORMAT_JSON);
    if (!output.isOpened()) throw std::runtime_error("Cannot open JSON report");
    output << "diagnostic_only" << 1 << "external_gpu_reference_available" << 0
          << "timing_mode" << (quality_export ? "quality_only" : (opencl_only ? "opencl_only" : "rotating_all"))
           << "performance_measured" << (timing_iterations ? 1 : 0)
           << "release_performance_gate" << 0 << "parameters_equivalent" << 0
           << "input" << argv[1] << "width" << first.cols << "height" << first.rows
           << "original_width" << original_size.width << "original_height" << original_size.height
           << "resized_workload" << static_cast<int>(first.size() != original_size)
          << "rotation_degrees" << config.rotation << "scale_factor" << config.scale
          << "gain" << config.gain << "bias" << config.bias << "blur_sigma" << config.blur_sigma
          << "affine" << affine
          << "prototype_octaves" << config.octaves << "prototype_intervals" << config.octave_layers
          << "prototype_base_sigma" << config.sigma << "prototype_contrast" << config.opencl_contrast
          << "prototype_hessian_ratio_limit" << (config.edge + 1) * (config.edge + 1) / config.edge
          << "reference" << "OpenCV CPU SIFT configured baseline"
          << "reference_opencv_version" << CV_VERSION
          << "cpu_threads" << cv::getNumThreads()
          << "cpu_optimized_code_enabled" << static_cast<int>(cv::useOptimized())
          << "ratio_threshold" << 0.8 << "inlier_threshold_px" << 3.0;
            output << "configuration" << "{" << "nfeatures" << config.nfeatures
              << "nOctaveLayers" << config.octave_layers << "contrastThreshold" << config.contrast
              << "edgeThreshold" << config.edge << "sigma" << config.sigma
              << "cpuThreads" << config.cpu_threads << "}";
            output << "gpu_nfeatures_semantics" << "response_ranked_post_extraction_cap_not_compute_limit"
              << "contrast_thresholds_equivalent" << 0;
    report(output, "opencl_prototype", first_opencl, second_opencl, affine);
  #ifdef SIFT_VALIDATE_SYCL
    output << "sycl_lifecycle" << (all_context ? "library_context_steady_state" : "per_call")
           << "sycl_context_setup_ms" << context_setup_ms
           << "sycl_context_release_ms" << context_release_ms
           << "sycl_device" << sycl_device.get_info<sycl::info::device::name>()
         << "sycl_driver" << sycl_device.get_info<sycl::info::device::driver_version>()
           << "sycl_compute_units" << static_cast<int>(sycl_device.get_info<sycl::info::device::max_compute_units>())
           << "sycl_max_clock_mhz" << static_cast<int>(sycl_device.get_info<sycl::info::device::max_clock_frequency>())
         << "sycl_octaves" << config.octaves << "sycl_init_blur" << config.sycl_init_blur
         << "sycl_contrast" << config.sycl_contrast << "sycl_scale_up" << 0
         << "sycl_octave_layers_fixed" << 5
         << "sycl_unsupported_requested_controls" << "nOctaveLayers,edgeThreshold,sigma"
         << "sycl_capacity" << 32768;
    report(output, "sycl_reference", first_sycl, second_sycl, affine);
    if (timing_iterations) {
      output << "timing" << "{" << "iterations" << timing_iterations
              << "warmups_per_backend" << 3 << "rotating_backend_order" << static_cast<int>(!opencl_only)
             << "scope" << (all_context ?
            "single_image_conversion_context_input_validation_upload_extract_owned_features_adapter_and_logging" :
            "single_image_conversion_allocation_per_call_setup_transfers_extract_host_descriptors_and_logging")
                  << "excludes" << "image_io_transform_matching_and_initial_gpu_detector_construction"
             << "tops_normalization" << "not_applied_precision_and_bandwidth_unverified";
                const double opencl_ms = report_latency(output, "opencl", opencl_samples);
                if (!opencl_only) {
                const double sycl_ms = report_latency(output, "sycl", sycl_samples);
                const double cpu_ms = report_latency(output, "opencv_cpu", cpu_samples);
                output << "cpu_over_opencl_latency_ratio" << cpu_ms / opencl_ms
                  << "cpu_over_sycl_latency_ratio" << cpu_ms / sycl_ms;
                }
                output << "speedup_quality_qualified" << 0;
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