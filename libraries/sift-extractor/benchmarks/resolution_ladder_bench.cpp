// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
//
// Resolution-ladder / octave / threshold benchmarks for OpenCV CPU SIFT,
// Intel OpenCL extract, and SYCL extract+match. One authoritative markdown
// schema merges CudaSift (Features/Extract/Match/Total/FPS) with
// complete-gpu-sift Detect/Match/Total FPS; side-by-side @ SXGA/1080p is the
// cross-backend detail view (no separate pipeline-summary block).

#include "sift_extractor/opencl_extractor.hpp"
#include "sift_extractor/opencl_matcher.hpp"
#include "syclSift.h"

#include <opencv2/core.hpp>
#include <opencv2/features2d.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <sstream>
#include <string>
#include <unistd.h>
#include <vector>

namespace {

struct Row {
  std::string label;   // resolution or sweep key (for tables)
  std::string backend; // opencv / opencl / sycl
  int width = 0;
  int height = 0;
  int features = 0;
  double upload_ms = 0.0;
  double extract_ms = 0.0;
  double match_ms = -1.0; // <0 means N/A
  bool ok = true;
  std::string error;
};

class SilenceStdout {
public:
  SilenceStdout() {
    fflush(stdout);
    saved_ = dup(STDOUT_FILENO);
    const int devnull = open("/dev/null", O_WRONLY);
    if (saved_ >= 0 && devnull >= 0) {
      dup2(devnull, STDOUT_FILENO);
      close(devnull);
    } else if (devnull >= 0) {
      close(devnull);
    }
  }
  ~SilenceStdout() {
    fflush(stdout);
    if (saved_ >= 0) {
      dup2(saved_, STDOUT_FILENO);
      close(saved_);
    }
  }
  SilenceStdout(const SilenceStdout &) = delete;
  SilenceStdout &operator=(const SilenceStdout &) = delete;

private:
  int saved_ = -1;
};

double median(std::vector<double> values) {
  if (values.empty())
    return 0.0;
  std::sort(values.begin(), values.end());
  const auto n = values.size();
  if (n % 2 == 1)
    return values[n / 2];
  return 0.5 * (values[n / 2 - 1] + values[n / 2]);
}

double total_ms(const Row &row) {
  double total = row.upload_ms + row.extract_ms;
  if (row.match_ms >= 0.0)
    total += row.match_ms;
  return total;
}

cv::Mat load_gray(const std::string &path) {
  cv::Mat image = cv::imread(path, cv::IMREAD_GRAYSCALE);
  if (image.empty())
    throw std::runtime_error("failed to load image: " + path);
  return image;
}

cv::Mat resize_f32(const cv::Mat &src, int width, int height) {
  cv::Mat resized, f32;
  cv::resize(src, resized, cv::Size(width, height));
  resized.convertTo(f32, CV_32FC1);
  return f32;
}

std::vector<float> mat_to_vector(const cv::Mat &f32) {
  std::vector<float> pixels(static_cast<std::size_t>(f32.cols) * f32.rows);
  if (f32.isContinuous()) {
    std::memcpy(pixels.data(), f32.ptr<float>(), pixels.size() * sizeof(float));
  } else {
    for (int y = 0; y < f32.rows; ++y)
      std::memcpy(pixels.data() + static_cast<std::size_t>(y) * f32.cols,
                  f32.ptr<float>(y), static_cast<std::size_t>(f32.cols) * sizeof(float));
  }
  return pixels;
}

Row bench_opencv(const cv::Mat &src, int width, int height, int octaves,
                 double contrast, int warmup, int runs) {
  Row row;
  row.backend = "opencv";
  row.width = width;
  row.height = height;
  try {
    cv::Mat gray_u8;
    cv::Mat f32 = resize_f32(src, width, height);
    f32.convertTo(gray_u8, CV_8U);
    // OpenCV nOctaveLayers is intervals; octave count is automatic from size.
    // Keep contrastThreshold as OpenCV's native knob (not SYCL thresh scale).
    (void)octaves;
    auto sift = cv::SIFT::create(0, 3, contrast, 10.0, 1.6);

    for (int i = 0; i < warmup; ++i) {
      std::vector<cv::KeyPoint> kps;
      cv::Mat desc;
      sift->detectAndCompute(gray_u8, cv::noArray(), kps, desc);
    }

    std::vector<double> extract_times;
    std::vector<cv::KeyPoint> keypoints;
    cv::Mat descriptors;
    for (int i = 0; i < runs; ++i) {
      keypoints.clear();
      descriptors.release();
      const auto start = std::chrono::steady_clock::now();
      sift->detectAndCompute(gray_u8, cv::noArray(), keypoints, descriptors);
      const auto end = std::chrono::steady_clock::now();
      extract_times.push_back(
          std::chrono::duration<double, std::milli>(end - start).count());
    }
    row.extract_ms = median(extract_times);
    row.features = static_cast<int>(keypoints.size());
    row.upload_ms = 0.0; // host path; no device upload

    if (row.features > 10 && !descriptors.empty()) {
      cv::BFMatcher matcher(cv::NORM_L2);
      std::vector<double> match_times;
      for (int i = 0; i < runs; ++i) {
        std::vector<std::vector<cv::DMatch>> knn;
        const auto start = std::chrono::steady_clock::now();
        matcher.knnMatch(descriptors, descriptors, knn, 2);
        const auto end = std::chrono::steady_clock::now();
        match_times.push_back(
            std::chrono::duration<double, std::milli>(end - start).count());
      }
      row.match_ms = median(match_times);
    } else {
      row.match_ms = -1.0;
    }
  } catch (const std::exception &error) {
    row.ok = false;
    row.error = error.what();
  }
  return row;
}

Row bench_opencl(const cv::Mat &src, int width, int height, int octaves,
                 float contrast, int warmup, int runs) {
  Row row;
  row.backend = "opencl";
  row.width = width;
  row.height = height;
  try {
    cv::Mat f32 = resize_f32(src, width, height);
    auto pixels = mat_to_vector(f32);
    sift_extractor::OpenCLExtractor extractor;
    sift_extractor::OpenCLExtractorOptions options;
    options.octaves = octaves;
    options.intervals = 3;
    options.base_sigma = 1.6f;
    options.contrast_threshold = contrast;
    options.edge_limit = 10.0f;
    options.max_features = 0;

    std::vector<sift_extractor::SiftFeature> features;
    for (int i = 0; i < warmup; ++i) {
      features = extractor.extract(pixels.data(), width, height, pixels.size(),
                                   options);
    }

    std::vector<double> extract_times;
    for (int i = 0; i < runs; ++i) {
      const auto start = std::chrono::steady_clock::now();
      features = extractor.extract(pixels.data(), width, height, pixels.size(),
                                   options);
      const auto end = std::chrono::steady_clock::now();
      extract_times.push_back(
          std::chrono::duration<double, std::milli>(end - start).count());
    }
    row.extract_ms = median(extract_times);
    row.features = static_cast<int>(features.size());
    row.upload_ms = 0.0; // included in extract (host→device inside extractor)

    if (row.features > 10 && extractor.has_resident_match()) {
      // Extract→match residency: same context/queue, no host descriptor re-upload.
      for (int i = 0; i < warmup; ++i)
        (void)extractor.match_last_self();
      std::vector<double> match_times;
      for (int i = 0; i < runs; ++i) {
        const auto start = std::chrono::steady_clock::now();
        (void)extractor.match_last_self();
        const auto end = std::chrono::steady_clock::now();
        match_times.push_back(
            std::chrono::duration<double, std::milli>(end - start).count());
      }
      row.match_ms = median(match_times);
    } else {
      row.match_ms = -1.0;
    }
  } catch (const std::exception &error) {
    row.ok = false;
    row.error = error.what();
  }
  return row;
}

Row bench_sycl(const cv::Mat &src, int width, int height, int octaves,
               float contrast, double init_blur, int warmup, int runs) {
  Row row;
  row.backend = "sycl";
  row.width = width;
  row.height = height;
  try {
    SilenceStdout silence;
    cv::Mat f32 = resize_f32(src, width, height);
    const int pitch = iAlignUp(width, 128);
    std::vector<float> packed(static_cast<std::size_t>(pitch) * height, 0.0f);
    for (int y = 0; y < height; ++y)
      std::memcpy(packed.data() + static_cast<std::size_t>(y) * pitch,
                  f32.ptr<float>(y),
                  static_cast<std::size_t>(width) * sizeof(float));

    SyclImage image;
    image.Allocate(width, height, pitch, true);
    std::memcpy(image.h_data, packed.data(),
                packed.size() * sizeof(float));

    SiftData data{};
    InitSiftData(data, 32768, true, true);
    float *scratch = AllocSiftTempMemory(width, height, octaves, false);
    if (!image.d_data || !data.d_data || !scratch)
      throw std::runtime_error("SYCL allocation failed");

    auto &queue = GetSyclQueue();
    for (int i = 0; i < warmup; ++i) {
      queue.memcpy(image.d_data, packed.data(), packed.size() * sizeof(float))
          .wait();
      ExtractSift(data, image, octaves, init_blur, contrast, 0.0f, false,
                  scratch);
      queue.wait();
    }

    std::vector<double> upload_times;
    for (int i = 0; i < runs; ++i) {
      const auto start = std::chrono::steady_clock::now();
      queue.memcpy(image.d_data, packed.data(), packed.size() * sizeof(float))
          .wait();
      const auto end = std::chrono::steady_clock::now();
      upload_times.push_back(
          std::chrono::duration<double, std::milli>(end - start).count());
    }
    row.upload_ms = median(upload_times);

    std::vector<double> extract_times;
    for (int i = 0; i < runs; ++i) {
      queue.memcpy(image.d_data, packed.data(), packed.size() * sizeof(float))
          .wait();
      const auto start = std::chrono::steady_clock::now();
      ExtractSift(data, image, octaves, init_blur, contrast, 0.0f, false,
                  scratch);
      queue.wait();
      const auto end = std::chrono::steady_clock::now();
      extract_times.push_back(
          std::chrono::duration<double, std::milli>(end - start).count());
    }
    row.extract_ms = median(extract_times);
    row.features = data.numPts;

    if (data.numPts > 10) {
      std::vector<double> match_times;
      for (int i = 0; i < runs; ++i) {
        const auto start = std::chrono::steady_clock::now();
        MatchSiftData(data, data);
        const auto end = std::chrono::steady_clock::now();
        match_times.push_back(
            std::chrono::duration<double, std::milli>(end - start).count());
      }
      row.match_ms = median(match_times);
    } else {
      row.match_ms = -1.0;
    }

    FreeSiftTempMemory(scratch);
    FreeSiftData(data);
  } catch (const std::exception &error) {
    row.ok = false;
    row.error = error.what();
  }
  return row;
}

void print_device() {
  try {
    auto device = GetSyclQueue().get_device();
    std::cout << "\n## Hardware Target\n\n";
    std::cout << "| Spec | Value |\n| --- | --- |\n";
    std::cout << "| GPU | " << device.get_info<sycl::info::device::name>()
              << " |\n";
    std::cout << "| Vendor | " << device.get_info<sycl::info::device::vendor>()
              << " |\n";
    std::cout << "| Driver | "
              << device.get_info<sycl::info::device::driver_version>()
              << " |\n";
    std::cout << "| Compute units | "
              << device.get_info<sycl::info::device::max_compute_units>()
              << " |\n";
    std::cout << "| Global memory (MB) | "
              << (device.get_info<sycl::info::device::global_mem_size>() /
                  (1024 * 1024))
              << " |\n";
  } catch (const std::exception &error) {
    std::cout << "\n## Hardware Target\n\nDevice query failed: " << error.what()
              << "\n";
  }
}

void print_fps_cell(double ms) {
  if (ms < 0.0) {
    std::cout << "—";
    return;
  }
  const double fps = ms > 0.0 ? 1000.0 / ms : 0.0;
  std::cout << std::fixed << std::setprecision(0) << fps;
}

// Authoritative row: CudaSift Features/Extract/Match/Total/FPS plus
// complete-gpu-sift Detect/Match/Total FPS. Side-by-side uses the same schema.
void print_detail_header(bool with_backend) {
  if (with_backend)
    std::cout << "| Size | Backend | Features | Extract (ms) | Detect FPS | "
                 "Match (ms) | Match FPS | Total (ms) | Total FPS |\n"
              << "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | "
                 "---: |\n";
  else
    std::cout << "| Resolution | Size | Features | Extract (ms) | Detect FPS | "
                 "Match (ms) | Match FPS | Total (ms) | Total FPS |\n"
              << "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | "
                 "---: |\n";
}

void print_detail_row(const Row &row, bool with_backend,
                      const char *backend_override = nullptr) {
  char size[32];
  std::snprintf(size, sizeof(size), "%dx%d", row.width, row.height);
  if (!row.ok) {
    if (with_backend)
      std::cout << "| " << size << " | "
                << (backend_override ? backend_override : row.backend)
                << " | ERR | ERR | ERR | ERR | ERR | ERR | ERR |\n";
    else
      std::cout << "| " << row.label << " | " << size
                << " | ERR | ERR | ERR | ERR | ERR | ERR | ERR |\n";
    return;
  }
  const double tot = total_ms(row);
  if (with_backend) {
    std::cout << "| " << size << " | "
              << (backend_override ? backend_override : row.backend) << " | "
              << row.features << " | " << std::fixed << std::setprecision(2)
              << row.extract_ms << " | ";
  } else {
    std::cout << "| " << row.label << " | " << size << " | " << row.features
              << " | " << std::fixed << std::setprecision(2) << row.extract_ms
              << " | ";
  }
  print_fps_cell(row.extract_ms);
  std::cout << " | ";
  if (row.match_ms < 0.0)
    std::cout << "—";
  else
    std::cout << std::setprecision(2) << row.match_ms;
  std::cout << " | ";
  print_fps_cell(row.match_ms);
  std::cout << " | " << std::setprecision(2) << tot << " | ";
  print_fps_cell(tot);
  std::cout << " |\n";
}

void print_resolution_table(const std::string &title,
                            const std::vector<Row> &rows) {
  std::cout << "\n### " << title << "\n\n";
  print_detail_header(/*with_backend=*/false);
  for (const auto &row : rows)
    print_detail_row(row, /*with_backend=*/false);
}

// CudaSift README columns: Features / Extract / Match / Total / FPS
void print_classic_ladder_table(const std::string &title,
                                const std::vector<Row> &rows) {
  std::cout << "\n### " << title << "\n\n";
  std::cout << "| Resolution | Size | Features | Extract (ms) | Match (ms) | "
               "Total (ms) | FPS |\n";
  std::cout << "| --- | --- | ---: | ---: | ---: | ---: | ---: |\n";
  for (const auto &row : rows) {
    char size[32];
    std::snprintf(size, sizeof(size), "%dx%d", row.width, row.height);
    if (!row.ok) {
      std::cout << "| " << row.label << " | " << size
                << " | ERR | ERR | ERR | ERR | ERR |\n";
      continue;
    }
    const double tot = total_ms(row);
    const double fps = tot > 0.0 ? 1000.0 / tot : 0.0;
    std::cout << "| " << row.label << " | " << size << " | " << row.features
              << " | " << std::fixed << std::setprecision(2) << row.extract_ms
              << " | ";
    if (row.match_ms < 0.0)
      std::cout << "—";
    else
      std::cout << std::setprecision(2) << row.match_ms;
    std::cout << " | " << std::setprecision(2) << tot << " | "
              << std::setprecision(0) << fps << " |\n";
  }
}

void print_side_by_side(const std::vector<Row> &opencv_rows,
                        const std::vector<Row> &opencl_rows,
                        const std::vector<Row> &sycl_rows, bool include_opencv,
                        bool include_opencl, bool include_sycl) {
  std::cout << "\n### Side-by-side @ SXGA / 1080p\n\n";
  print_detail_header(/*with_backend=*/true);
  auto find_row = [](const std::vector<Row> &rows, int w,
                     int h) -> const Row * {
    for (const auto &row : rows)
      if (row.width == w && row.height == h)
        return &row;
    return nullptr;
  };
  for (auto size : {std::pair<int, int>{1280, 960}, {1920, 1080}}) {
    if (include_opencv)
      if (const Row *row = find_row(opencv_rows, size.first, size.second))
        print_detail_row(*row, true, "OpenCV");
    if (include_opencl)
      if (const Row *row = find_row(opencl_rows, size.first, size.second))
        print_detail_row(*row, true, "OpenCL");
    if (include_sycl)
      if (const Row *row = find_row(sycl_rows, size.first, size.second))
        print_detail_row(*row, true, "SYCL");
  }
}

void print_sweep_table(const std::string &title, const char *key_header,
                       const std::vector<std::pair<std::string, Row>> &rows) {
  std::cout << "\n### " << title << "\n\n";
  std::cout << "| " << key_header << " | Features | Extract (ms) |\n";
  std::cout << "| --- | ---: | ---: |\n";
  for (const auto &entry : rows) {
    const auto &row = entry.second;
    if (!row.ok) {
      std::cout << "| " << entry.first << " | ERR | ERR |\n";
      continue;
    }
    std::cout << "| " << entry.first << " | " << row.features << " | "
              << std::fixed << std::setprecision(2) << row.extract_ms << " |\n";
  }
}

std::string json_escape(const std::string &text) {
  std::string out;
  for (char c : text) {
    if (c == '"' || c == '\\')
      out.push_back('\\');
    out.push_back(c);
  }
  return out;
}

void append_row_json(std::ostream &out, const Row &row, bool comma) {
  out << (comma ? ",\n" : "\n");
  out << "    {\"backend\":\"" << json_escape(row.backend) << "\",\"label\":\""
      << json_escape(row.label) << "\",\"width\":" << row.width
      << ",\"height\":" << row.height << ",\"features\":" << row.features
      << ",\"upload_ms\":" << row.upload_ms << ",\"extract_ms\":" << row.extract_ms
      << ",\"match_ms\":" << row.match_ms << ",\"total_ms\":" << total_ms(row)
      << ",\"ok\":" << (row.ok ? "true" : "false") << ",\"error\":\""
      << json_escape(row.error) << "\"}";
}

} // namespace

int main(int argc, char **argv) {
  if (argc < 2) {
    std::fprintf(
        stderr,
        "Usage: %s IMAGE [warmup] [runs] [json_out] [--sycl-only|--opencl-only] "
        "[--sxga-1080]\n"
        "  IMAGE: grayscale fixture (e.g. data/img1.png)\n"
        "  Env overrides: SIFT_OPENCL_CONTRAST SIFT_SYCL_CONTRAST "
        "SIFT_OPENCV_CONTRAST\n",
        argv[0]);
    return 2;
  }
  const std::string image_path = argv[1];
  const int warmup = argc > 2 ? std::atoi(argv[2]) : 20;
  const int runs = argc > 3 ? std::atoi(argv[3]) : 50;
  const char *json_out = nullptr;
  bool sycl_only = false;
  bool opencl_only = false;
  bool sxga_1080_only = false;
  for (int i = 4; i < argc; ++i) {
    if (std::strcmp(argv[i], "--sycl-only") == 0)
      sycl_only = true;
    else if (std::strcmp(argv[i], "--opencl-only") == 0)
      opencl_only = true;
    else if (std::strcmp(argv[i], "--sxga-1080") == 0)
      sxga_1080_only = true;
    else if (!json_out && argv[i][0] != '-')
      json_out = argv[i];
  }
  if (sycl_only && opencl_only) {
    std::fprintf(stderr, "Choose at most one of --sycl-only / --opencl-only\n");
    return 2;
  }
  const bool run_opencv = !sycl_only && !opencl_only;
  const bool run_opencl = !sycl_only;
  const bool run_sycl = !opencl_only;

  const int octaves = 5;
  const auto env_float = [](const char *name, float fallback) {
    const char *raw = std::getenv(name);
    if (!raw || !*raw) return fallback;
    char *end = nullptr;
    const float value = std::strtof(raw, &end);
    if (end == raw || *end != '\0' || !(value > 0.0f)) return fallback;
    return value;
  };
  const auto env_double = [](const char *name, double fallback) {
    const char *raw = std::getenv(name);
    if (!raw || !*raw) return fallback;
    char *end = nullptr;
    const double value = std::strtod(raw, &end);
    if (end == raw || *end != '\0' || !(value > 0.0)) return fallback;
    return value;
  };
  const float sycl_contrast = env_float("SIFT_SYCL_CONTRAST", 3.0f);
  const float opencl_contrast =
      env_float("SIFT_OPENCL_CONTRAST", 1.0f); // OpenCL diagnostic scale (≠ SYCL)
  const double opencv_contrast = env_double("SIFT_OPENCV_CONTRAST", 0.04);
  const double sycl_init_blur = 1.0;

  cv::Mat src = load_gray(image_path);

  struct Resolution {
    int w;
    int h;
    const char *name;
  };
  const std::vector<Resolution> resolutions =
      sxga_1080_only
          ? std::vector<Resolution>{{1280, 960, "SXGA"}, {1920, 1080, "1080p"}}
          : std::vector<Resolution>{
                {640, 480, "VGA"},      {1280, 720, "720p"},
                {1280, 960, "SXGA"},    {1920, 1080, "1080p"},
                {2560, 1440, "1440p"},  {3840, 2160, "4K UHD"},
            };

  if (sycl_only)
    std::cout << "# SYCL resolution-ladder comparison\n";
  else if (opencl_only)
    std::cout << "# OpenCL resolution-ladder comparison\n";
  else
    std::cout << "# OpenCV / OpenCL / SYCL resolution-ladder comparison\n";
  std::cout << "\nFixture: `" << image_path << "` (resized per resolution)\n";
  std::cout << "Protocol: warmup=" << warmup << " runs=" << runs
            << " (median). Octaves=" << octaves;
  if (run_sycl)
    std::cout << ". SYCL contrast=" << sycl_contrast
              << " initBlur=" << sycl_init_blur;
  if (run_opencl)
    std::cout << ". OpenCL contrast=" << opencl_contrast;
  if (run_opencv)
    std::cout << ". OpenCV contrastThreshold=" << opencv_contrast;
  std::cout << ".\n";
  if (opencl_only || sycl_only) {
    std::cout << "Classic ladder columns: Features / Extract / Match / Total / "
                 "FPS (Total FPS = 1000/(upload+extract[+match])).\n";
  } else {
    std::cout
        << "Columns: Features / Extract / Match / Total (CudaSift ladder) plus "
           "Detect FPS / Match FPS / Total FPS (complete-gpu-sift). "
           "Detect FPS=1000/Extract; Match FPS=1000/Match; "
           "Total FPS=1000/(upload+extract[+match]).\n";
  }
  if (run_opencl) {
    std::cout << "OpenCL Match = extract→match residency (same context; no host "
                 "descriptor re-upload → tiled kernel → readback).\n";
  }
  if (run_opencv || (run_opencl && run_sycl)) {
    std::cout
        << "Parameters are **not** algorithm-equivalent across backends.\n";
  }

  print_device();

  std::vector<Row> opencv_rows, opencl_rows, sycl_rows;
  for (const auto &res : resolutions) {
    std::cerr << "resolution " << res.name << " " << res.w << "x" << res.h
              << std::endl;
    if (run_opencv) {
      auto ocv = bench_opencv(src, res.w, res.h, octaves, opencv_contrast,
                              warmup, runs);
      ocv.label = res.name;
      opencv_rows.push_back(ocv);
    }
    if (run_opencl) {
      auto ocl = bench_opencl(src, res.w, res.h, octaves, opencl_contrast,
                              warmup, runs);
      ocl.label = res.name;
      opencl_rows.push_back(ocl);
    }
    if (run_sycl) {
      auto sy = bench_sycl(src, res.w, res.h, octaves, sycl_contrast,
                           sycl_init_blur, warmup, runs);
      sy.label = res.name;
      sycl_rows.push_back(sy);
    }
  }

  if (run_opencv)
    print_resolution_table(
        "OpenCV CPU SIFT (detectAndCompute + BFMatcher self-match)",
        opencv_rows);
  if (opencl_only) {
    print_classic_ladder_table(
        "OpenCL extract + OpenCLMatcher (5 octaves, contrast=1.0)", opencl_rows);
  } else if (run_opencl) {
    print_resolution_table("OpenCL extract + OpenCLMatcher self-match",
                           opencl_rows);
  }
  if (sycl_only) {
    print_classic_ladder_table(
        "SYCL extract + MatchSiftData (5 octaves, threshold=3.0)", sycl_rows);
  } else if (run_sycl) {
    print_resolution_table(
        "SYCL extract + MatchSiftData (5 octaves, threshold=3.0)", sycl_rows);
  }

  if (!opencl_only && !sycl_only)
    print_side_by_side(opencv_rows, opencl_rows, sycl_rows, run_opencv,
                       run_opencl, run_sycl);

  if (sxga_1080_only) {
    if (json_out) {
      std::ofstream out(json_out);
      out << std::setprecision(9);
      out << "{\n  \"fixture\":\"" << json_escape(image_path)
          << "\",\n  \"warmup\":" << warmup << ",\"runs\":" << runs
          << ",\"octaves\":" << octaves
          << ",\"opencl_contrast\":" << opencl_contrast
          << ",\"sycl_contrast\":" << sycl_contrast
          << ",\"opencv_contrast\":" << opencv_contrast
          << ",\n  \"rows\":[";
      bool comma = false;
      for (const auto &row : opencv_rows) {
        append_row_json(out, row, comma);
        comma = true;
      }
      for (const auto &row : opencl_rows) {
        append_row_json(out, row, comma);
        comma = true;
      }
      for (const auto &row : sycl_rows) {
        append_row_json(out, row, comma);
        comma = true;
      }
      out << "\n  ]\n}\n";
    }
    return 0;
  }

  // Octave sweep @ 1080p (CudaSift-style Features / Extract)
  std::vector<std::pair<std::string, Row>> ocv_oct, ocl_oct, sy_oct;
  for (int oct = 3; oct <= 6; ++oct) {
    std::cerr << "octave sweep " << oct << std::endl;
    if (run_opencv) {
      auto ocv =
          bench_opencv(src, 1920, 1080, oct, opencv_contrast, warmup, runs);
      ocv_oct.push_back({std::to_string(oct), ocv});
    }
    if (run_opencl) {
      auto ocl =
          bench_opencl(src, 1920, 1080, oct, opencl_contrast, warmup, runs);
      ocl_oct.push_back({std::to_string(oct), ocl});
    }
    if (run_sycl) {
      auto sy = bench_sycl(src, 1920, 1080, oct, sycl_contrast, sycl_init_blur,
                           warmup, runs);
      sy_oct.push_back({std::to_string(oct), sy});
    }
  }
  if (run_opencl)
    print_sweep_table("Octave Comparison — OpenCL (1080p, contrast=1.0)",
                      "Octaves", ocl_oct);
  if (run_sycl)
    print_sweep_table("Octave Comparison — SYCL (1080p, threshold=3.0)",
                      "Octaves", sy_oct);
  if (run_opencv)
    print_sweep_table(
        "Octave comparison — OpenCV (1080p; octave count automatic; "
        "column is unused request)",
        "Requested octaves", ocv_oct);

  // Threshold / contrast sweep @ 1080p, 5 octaves
  std::vector<std::pair<std::string, Row>> ocl_thr, sy_thr, ocv_thr;
  const float gpu_thresholds[] = {1.0f, 2.0f, 3.0f, 5.0f, 10.0f};
  for (float thr : gpu_thresholds) {
    std::cerr << "threshold sweep gpu " << thr << std::endl;
    if (run_opencl) {
      auto ocl = bench_opencl(src, 1920, 1080, 5, thr, warmup, runs);
      std::ostringstream key;
      key << std::fixed << std::setprecision(1) << thr;
      ocl_thr.push_back({key.str(), ocl});
    }
    if (run_sycl) {
      auto sy =
          bench_sycl(src, 1920, 1080, 5, thr, sycl_init_blur, warmup, runs);
      std::ostringstream key;
      key << std::fixed << std::setprecision(1) << thr;
      sy_thr.push_back({key.str(), sy});
    }
  }
  if (run_opencv) {
    const double ocv_thresholds[] = {0.01, 0.02, 0.04, 0.06, 0.10};
    for (double thr : ocv_thresholds) {
      std::cerr << "threshold sweep opencv " << thr << std::endl;
      auto ocv = bench_opencv(src, 1920, 1080, 5, thr, warmup, runs);
      std::ostringstream key;
      key << std::fixed << std::setprecision(2) << thr;
      ocv_thr.push_back({key.str(), ocv});
    }
  }
  if (run_opencl)
    print_sweep_table("Threshold Comparison — OpenCL (1080p, 5 octaves)",
                      "Contrast", ocl_thr);
  if (run_sycl)
    print_sweep_table("Threshold Comparison — SYCL (1080p, 5 octaves)",
                      "Threshold", sy_thr);
  if (run_opencv)
    print_sweep_table("Threshold comparison — OpenCV (1080p; contrastThreshold)",
                      "contrastThreshold", ocv_thr);

  if (json_out) {
    std::ofstream out(json_out);
    out << std::setprecision(6) << std::fixed;
    out << "{\n  \"fixture\":\"" << json_escape(image_path) << "\",\n";
    out << "  \"warmup\":" << warmup << ",\"runs\":" << runs
        << ",\"octaves\":" << octaves << ",\"sycl_only\":"
        << (sycl_only ? "true" : "false") << ",\"opencl_only\":"
        << (opencl_only ? "true" : "false") << ",\n";
    out << "  \"knobs\":{\"sycl_contrast\":" << sycl_contrast
        << ",\"opencl_contrast\":" << opencl_contrast
        << ",\"opencv_contrastThreshold\":" << opencv_contrast
        << ",\"sycl_init_blur\":" << sycl_init_blur << "},\n";
    out << "  \"resolution\":[";
    bool first = true;
    for (const auto &row : opencv_rows) {
      append_row_json(out, row, !first);
      first = false;
    }
    for (const auto &row : opencl_rows)
      append_row_json(out, row, true);
    for (const auto &row : sycl_rows)
      append_row_json(out, row, true);
    out << "\n  ]\n}\n";
  }
  return 0;
}
