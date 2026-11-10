// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
//
// Honest OpenCV DIS disparity on MPI Sintel training + KITTI 2015 training.
// Compares SDK DIS (CPU / OpenCL) against OpenCV DIS at matched presets.
// Does not invent parity — prints deltas vs PLAN §8 gates.

#include "optical_flow_sdk/metrics.hpp"
#include "optical_flow_sdk/opencv_adapter.hpp"
#include "optical_flow_sdk/optical_flow.hpp"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

#include <opencv2/core.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>
#include <opencv2/video/tracking.hpp>

namespace fs = std::filesystem;

namespace {

optical_flow_sdk::FlowField flow_from_mat(const cv::Mat &flow32fc2) {
  return optical_flow_sdk::opencv::to_flow_field(flow32fc2);
}

optical_flow_sdk::FlowField read_kitti_flow_png(const fs::path &path) {
  const cv::Mat png = cv::imread(path.string(), cv::IMREAD_UNCHANGED);
  if (png.empty() || png.type() != CV_16UC3)
    throw std::runtime_error("failed to read KITTI flow PNG: " + path.string());
  optical_flow_sdk::FlowField flow;
  flow.allocate(png.cols, png.rows);
  for (int y = 0; y < png.rows; ++y) {
    for (int x = 0; x < png.cols; ++x) {
      const cv::Vec3w p = png.at<cv::Vec3w>(y, x);
      const float valid = static_cast<float>(p[0]);
      if (valid < 0.5f) {
        flow.dx(x, y) = std::numeric_limits<float>::quiet_NaN();
        flow.dy(x, y) = std::numeric_limits<float>::quiet_NaN();
        continue;
      }
      flow.dx(x, y) = (static_cast<float>(p[2]) - 32768.0f) / 64.0f;
      flow.dy(x, y) = (static_cast<float>(p[1]) - 32768.0f) / 64.0f;
    }
  }
  return flow;
}

cv::Mat to_gray(const cv::Mat &bgr_or_gray) {
  if (bgr_or_gray.channels() == 1)
    return bgr_or_gray;
  cv::Mat gray;
  cv::cvtColor(bgr_or_gray, gray, cv::COLOR_BGR2GRAY);
  return gray;
}

struct PairResult {
  std::string id;
  optical_flow_sdk::EpeStats sdk_vs_gt;
  optical_flow_sdk::EpeStats ocv_vs_gt;
  optical_flow_sdk::EpeStats sdk_vs_ocv;
  double fl_all_sdk = 0.0;
  double fl_all_ocv = 0.0;
  std::size_t fl_count = 0;
};

void accumulate_fl(const optical_flow_sdk::FlowField &pred, const optical_flow_sdk::FlowField &gt,
                   std::size_t &bad, std::size_t &count) {
  for (int y = 0; y < pred.height; ++y) {
    for (int x = 0; x < pred.width; ++x) {
      const float gu = gt.dx(x, y);
      const float gv = gt.dy(x, y);
      if (!std::isfinite(gu) || !std::isfinite(gv))
        continue;
      const float pu = pred.dx(x, y);
      const float pv = pred.dy(x, y);
      if (!std::isfinite(pu) || !std::isfinite(pv))
        continue;
      const double epe = std::sqrt(static_cast<double>((pu - gu) * (pu - gu) + (pv - gv) * (pv - gv)));
      const double mag = std::sqrt(static_cast<double>(gu * gu + gv * gv));
      ++count;
      if (epe > 3.0 && epe > 0.05 * mag)
        ++bad;
    }
  }
}

// Mask predictions to GT-valid pixels so pairwise EPE ignores unlabeled sky/etc.
optical_flow_sdk::FlowField mask_to_gt_valid(const optical_flow_sdk::FlowField &pred,
                                             const optical_flow_sdk::FlowField &gt) {
  optical_flow_sdk::FlowField out = pred;
  for (int y = 0; y < gt.height; ++y) {
    for (int x = 0; x < gt.width; ++x) {
      if (!std::isfinite(gt.dx(x, y)) || !std::isfinite(gt.dy(x, y))) {
        out.dx(x, y) = std::numeric_limits<float>::quiet_NaN();
        out.dy(x, y) = std::numeric_limits<float>::quiet_NaN();
      }
    }
  }
  return out;
}

PairResult eval_pair(const std::string &id, const cv::Mat &prev_gray, const cv::Mat &next_gray,
                     const optical_flow_sdk::FlowField &gt, optical_flow_sdk::OpticalFlow &sdk,
                     cv::Ptr<cv::DISOpticalFlow> ocv, bool kitti_fl) {
  cv::Mat sdk_mat;
  optical_flow_sdk::opencv::calc(sdk, prev_gray, next_gray, sdk_mat);
  const optical_flow_sdk::FlowField sdk_flow = flow_from_mat(sdk_mat);

  cv::Mat ocv_mat;
  ocv->calc(prev_gray, next_gray, ocv_mat);
  const optical_flow_sdk::FlowField ocv_flow = flow_from_mat(ocv_mat);

  const optical_flow_sdk::FlowField sdk_m = mask_to_gt_valid(sdk_flow, gt);
  const optical_flow_sdk::FlowField ocv_m = mask_to_gt_valid(ocv_flow, gt);

  PairResult r;
  r.id = id;
  r.sdk_vs_gt = optical_flow_sdk::endpoint_error(sdk_m, gt, 0);
  r.ocv_vs_gt = optical_flow_sdk::endpoint_error(ocv_m, gt, 0);
  r.sdk_vs_ocv = optical_flow_sdk::endpoint_error(sdk_m, ocv_m, 0);
  if (kitti_fl) {
    std::size_t bad_s = 0, bad_o = 0, n = 0, n2 = 0;
    accumulate_fl(sdk_m, gt, bad_s, n);
    accumulate_fl(ocv_m, gt, bad_o, n2);
    r.fl_count = n;
    r.fl_all_sdk = n ? (100.0 * static_cast<double>(bad_s) / static_cast<double>(n)) : 0.0;
    r.fl_all_ocv = n2 ? (100.0 * static_cast<double>(bad_o) / static_cast<double>(n2)) : 0.0;
  }
  return r;
}

// OpenCV exposes ULTRAFAST / FAST / MEDIUM. Map SDK Slow -> MEDIUM.
int ocv_preset_fixed(optical_flow_sdk::Preset p) {
  switch (p) {
  case optical_flow_sdk::Preset::Fast:
    return cv::DISOpticalFlow::PRESET_FAST;
  case optical_flow_sdk::Preset::Medium:
    return cv::DISOpticalFlow::PRESET_MEDIUM;
  case optical_flow_sdk::Preset::Slow:
    return cv::DISOpticalFlow::PRESET_MEDIUM;
  }
  return cv::DISOpticalFlow::PRESET_MEDIUM;
}

struct Agg {
  double sum_sdk_gt = 0, sum_ocv_gt = 0, sum_pair = 0;
  double sum_s0_sdk = 0, sum_s0_ocv = 0, sum_s0_pair = 0;
  double sum_s1_sdk = 0, sum_s1_ocv = 0, sum_s1_pair = 0;
  double sum_s2_sdk = 0, sum_s2_ocv = 0, sum_s2_pair = 0;
  double sum_fl_sdk = 0, sum_fl_ocv = 0;
  std::size_t n = 0, n_fl = 0;
  void add(const PairResult &r, bool kitti) {
    sum_sdk_gt += r.sdk_vs_gt.mean;
    sum_ocv_gt += r.ocv_vs_gt.mean;
    sum_pair += r.sdk_vs_ocv.mean;
    sum_s0_sdk += r.sdk_vs_gt.mean_s0_10;
    sum_s0_ocv += r.ocv_vs_gt.mean_s0_10;
    sum_s0_pair += r.sdk_vs_ocv.mean_s0_10;
    sum_s1_sdk += r.sdk_vs_gt.mean_s10_40;
    sum_s1_ocv += r.ocv_vs_gt.mean_s10_40;
    sum_s1_pair += r.sdk_vs_ocv.mean_s10_40;
    sum_s2_sdk += r.sdk_vs_gt.mean_s40p;
    sum_s2_ocv += r.ocv_vs_gt.mean_s40p;
    sum_s2_pair += r.sdk_vs_ocv.mean_s40p;
    ++n;
    if (kitti && r.fl_count) {
      sum_fl_sdk += r.fl_all_sdk;
      sum_fl_ocv += r.fl_all_ocv;
      ++n_fl;
    }
  }
};

void print_agg(const char *title, const Agg &a, bool kitti) {
  if (!a.n) {
    std::cout << title << ": no pairs\n";
    return;
  }
  const double inv = 1.0 / static_cast<double>(a.n);
  const double pair = a.sum_pair * inv;
  const double sdk = a.sum_sdk_gt * inv;
  const double ocv = a.sum_ocv_gt * inv;
  const double abs_d = std::fabs(sdk - ocv);
  const double rel = (ocv > 1e-9) ? (100.0 * abs_d / ocv) : 0.0;
  const double pair_s0 = a.sum_s0_pair * inv;
  const double pair_s1 = a.sum_s1_pair * inv;
  const double pair_s2 = a.sum_s2_pair * inv;
  std::cout << title << " pairs=" << a.n << "\n"
            << "  EPE vs GT: sdk=" << sdk << " opencv=" << ocv << " abs_diff=" << abs_d
            << " rel%=" << rel << "\n"
            << "  EPE sdk vs opencv (parity): all=" << pair << " s0-10=" << pair_s0
            << " s10-40=" << pair_s1 << " s40+=" << pair_s2 << "\n";
  // PLAN §8: mean EPE difference vs OpenCV <= max(0.05px, 2% relative).
  const double gate = std::max(0.05, 0.02 * std::max(ocv, 1e-6));
  const bool gate_pair = pair <= gate;
  const bool gate_s0 = pair_s0 <= std::max(0.05, 0.02 * std::max(a.sum_s0_ocv * inv, 1e-6));
  const bool gate_s1 = pair_s1 <= std::max(0.05, 0.02 * std::max(a.sum_s1_ocv * inv, 1e-6));
  const bool gate_s2 = pair_s2 <= std::max(0.05, 0.02 * std::max(a.sum_s2_ocv * inv, 1e-6));
  std::cout << "  pairwise gate (<= max(0.05px, 2%)): all=" << (gate_pair ? "PASS" : "FAIL")
            << " s0-10=" << (gate_s0 ? "PASS" : "FAIL") << " s10-40=" << (gate_s1 ? "PASS" : "FAIL")
            << " s40+=" << (gate_s2 ? "PASS" : "FAIL") << " (need <=" << gate << ", got " << pair
            << ")\n";
  (void)abs_d;
  (void)rel;
  if (kitti && a.n_fl) {
    const double fl_s = a.sum_fl_sdk / static_cast<double>(a.n_fl);
    const double fl_o = a.sum_fl_ocv / static_cast<double>(a.n_fl);
    const double fl_d = std::fabs(fl_s - fl_o);
    std::cout << "  Fl-all%: sdk=" << fl_s << " opencv=" << fl_o << " abs_diff=" << fl_d
              << " gate(<=0.5pp)=" << (fl_d <= 0.5 ? "PASS" : "FAIL") << "\n";
  }
}

std::vector<fs::path> list_sorted(const fs::path &dir, const std::string &ext) {
  std::vector<fs::path> out;
  if (!fs::exists(dir))
    return out;
  for (const auto &e : fs::directory_iterator(dir)) {
    if (!e.is_regular_file())
      continue;
    if (e.path().extension() == ext)
      out.push_back(e.path());
  }
  std::sort(out.begin(), out.end());
  return out;
}

void run_sintel(const fs::path &root, optical_flow_sdk::Backend backend,
                optical_flow_sdk::Preset preset, int max_pairs) {
  // Accept either training/{clean,final,flow} or MPI-Sintel/training/...
  std::vector<fs::path> bases = {root / "training", root / "MPI-Sintel" / "training",
                                 root / "MPI-Sintel-complete" / "training"};
  fs::path train;
  for (const auto &b : bases) {
    if (fs::exists(b / "clean") && fs::exists(b / "flow")) {
      train = b;
      break;
    }
  }
  if (train.empty()) {
    std::cout << "Sintel training tree not found under " << root << "\n";
    return;
  }

  optical_flow_sdk::OpticalFlow sdk(backend, preset);
  auto ocv = cv::DISOpticalFlow::create(ocv_preset_fixed(preset));
  Agg clean_agg, final_agg;

  for (const char *pass : {"clean", "final"}) {
    Agg *agg = (std::string(pass) == "clean") ? &clean_agg : &final_agg;
    int used = 0; // budget applies per pass (Clean and Final each get max_pairs)
    std::vector<fs::path> seqs;
    for (const auto &seq : fs::directory_iterator(train / pass)) {
      if (seq.is_directory())
        seqs.push_back(seq.path());
    }
    std::sort(seqs.begin(), seqs.end());
    // Round-robin across sequences so --max-pairs is not biased to alley_*.
    std::size_t round = 0;
    bool any = true;
    while (any && (max_pairs <= 0 || used < max_pairs)) {
      any = false;
      for (const auto &seq_path : seqs) {
        if (max_pairs > 0 && used >= max_pairs)
          break;
        const std::string seq_name = seq_path.filename().string();
        auto frames = list_sorted(seq_path, ".png");
        const fs::path flow_dir = train / "flow" / seq_name;
        if (!fs::exists(flow_dir) || round + 1 >= frames.size())
          continue;
        const std::size_t i = round;
        const fs::path flo = flow_dir / (frames[i].stem().string() + ".flo");
        if (!fs::exists(flo))
          continue;
        any = true;
        const cv::Mat prev = to_gray(cv::imread(frames[i].string(), cv::IMREAD_COLOR));
        const cv::Mat next = to_gray(cv::imread(frames[i + 1].string(), cv::IMREAD_COLOR));
        if (prev.empty() || next.empty())
          continue;
        const auto gt = optical_flow_sdk::read_flo(flo.string());
        const auto r =
            eval_pair(pass + std::string("/") + seq_name + "/" + frames[i].stem().string(), prev,
                      next, gt, sdk, ocv, false);
        agg->add(r, false);
        ++used;
        if ((used % 10) == 0) {
          std::cout << "  sintel " << pass << " progress pairs=" << used << std::endl;
        }
      }
      ++round;
    }
  }
  std::cout << "=== Sintel backend=" << optical_flow_sdk::backend_name(backend)
            << " preset=" << optical_flow_sdk::preset_name(preset) << " ===\n";
  print_agg("Sintel Clean", clean_agg, false);
  print_agg("Sintel Final", final_agg, false);
}

void run_kitti(const fs::path &root, optical_flow_sdk::Backend backend,
               optical_flow_sdk::Preset preset, int max_pairs) {
  fs::path img = root / "training" / "image_2";
  fs::path flow = root / "training" / "flow_occ";
  if (!fs::exists(img) || !fs::exists(flow)) {
    std::cout << "KITTI training tree not found under " << root << "\n";
    return;
  }
  optical_flow_sdk::OpticalFlow sdk(backend, preset);
  auto ocv = cv::DISOpticalFlow::create(ocv_preset_fixed(preset));
  Agg agg;
  auto imgs = list_sorted(img, ".png");
  int used = 0;
  for (const auto &p : imgs) {
    const std::string name = p.filename().string(); // 000000_10.png
    if (name.size() < 7 || name.substr(name.size() - 6) != "10.png")
      continue;
    if (max_pairs > 0 && used >= max_pairs)
      break;
    const std::string id = name.substr(0, 6);
    const fs::path next = img / (id + "_11.png");
    const fs::path gt_path = flow / (id + "_10.png");
    if (!fs::exists(next) || !fs::exists(gt_path))
      continue;
    const cv::Mat prev = to_gray(cv::imread(p.string(), cv::IMREAD_COLOR));
    const cv::Mat nxt = to_gray(cv::imread(next.string(), cv::IMREAD_COLOR));
    if (prev.empty() || nxt.empty())
      continue;
    const auto gt = read_kitti_flow_png(gt_path);
    const auto r = eval_pair(id, prev, nxt, gt, sdk, ocv, true);
    agg.add(r, true);
    ++used;
    if ((used % 10) == 0) {
      std::cout << "  kitti progress pairs=" << used << std::endl;
    }
  }
  std::cout << "=== KITTI backend=" << optical_flow_sdk::backend_name(backend)
            << " preset=" << optical_flow_sdk::preset_name(preset) << " ===\n";
  print_agg("KITTI train", agg, true);
}

void usage() {
  std::cerr
      << "usage: parity_opencv_datasets --sintel DIR --kitti DIR [--backend cpu|opencl]\n"
         "       [--preset fast|medium|slow] [--max-pairs N]\n";
}

} // namespace

int main(int argc, char **argv) {
  using optical_flow_sdk::Backend;
  using optical_flow_sdk::Preset;
  fs::path sintel, kitti;
  Backend backend = Backend::Cpu;
  Preset preset = Preset::Medium;
  int max_pairs = 0;
  for (int i = 1; i < argc; ++i) {
    const std::string a = argv[i];
    auto need = [&](const char *flag) -> std::string {
      if (i + 1 >= argc)
        throw std::runtime_error(std::string("missing value for ") + flag);
      return argv[++i];
    };
    if (a == "--sintel")
      sintel = need("--sintel");
    else if (a == "--kitti")
      kitti = need("--kitti");
    else if (a == "--backend")
      backend = optical_flow_sdk::backend_from_name(need("--backend"));
    else if (a == "--preset")
      preset = optical_flow_sdk::preset_from_name(need("--preset"));
    else if (a == "--max-pairs")
      max_pairs = std::stoi(need("--max-pairs"));
    else if (a == "--help") {
      usage();
      return 0;
    } else {
      usage();
      return EXIT_FAILURE;
    }
  }
  if (sintel.empty() && kitti.empty()) {
    usage();
    return EXIT_FAILURE;
  }
  std::cout << "note: SDK DIS matches OpenCV pyramid/mean-norm; variational refine disabled "
               "(GPU Jacobi regresses Fl-all vs DIS-only).\n"
               "PLAN §8 pairwise EPE<=max(0.05px,2%) is a hard classical-equivalence bar.\n";
  if (!sintel.empty())
    run_sintel(sintel, backend, preset, max_pairs);
  if (!kitti.empty())
    run_kitti(kitti, backend, preset, max_pairs);
  return 0;
}
