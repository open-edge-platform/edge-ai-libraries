// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// VA surface → OpenCL import → calc_device E2E.
// Requires working libva iHD (vainfo --display drm) and cl_intel_va_api_media_sharing.
// Build with OPTICALFLOW_ENABLE_OPENCL=ON and libva available.

#include "optical_flow_sdk/opencl_optical_flow.hpp"
#include "optical_flow_sdk/version.hpp"

#include <va/va.h>
#include <va/va_drm.h>

#include <fcntl.h>
#include <unistd.h>

#include <algorithm>
#include <cmath>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

#if !OPTICALFLOW_HAS_OPENCL
#error "Build with -DOPTICALFLOW_ENABLE_OPENCL=ON"
#endif

namespace {

void check_va(VAStatus st, const char *op) {
  if (st != VA_STATUS_SUCCESS)
    throw std::runtime_error(std::string(op) + " failed: " + std::to_string(st));
}

struct VaSurfacePair {
  VADisplay dpy = nullptr;
  int drm_fd = -1;
  VASurfaceID prev = VA_INVALID_SURFACE;
  VASurfaceID next = VA_INVALID_SURFACE;
  int width = 0;
  int height = 0;

  ~VaSurfacePair() {
    if (dpy) {
      if (prev != VA_INVALID_SURFACE)
        vaDestroySurfaces(dpy, &prev, 1);
      if (next != VA_INVALID_SURFACE)
        vaDestroySurfaces(dpy, &next, 1);
      vaTerminate(dpy);
    }
    if (drm_fd >= 0)
      close(drm_fd);
  }
};

VaSurfacePair make_shifted_nv12(int w, int h, int dx) {
  VaSurfacePair v;
  v.width = w;
  v.height = h;
  v.drm_fd = open("/dev/dri/renderD128", O_RDWR);
  if (v.drm_fd < 0)
    throw std::runtime_error("open /dev/dri/renderD128 failed");
  v.dpy = vaGetDisplayDRM(v.drm_fd);
  if (!v.dpy)
    throw std::runtime_error("vaGetDisplayDRM failed");
  int major = 0, minor = 0;
  check_va(vaInitialize(v.dpy, &major, &minor), "vaInitialize");

  VASurfaceID ids[2];
  check_va(vaCreateSurfaces(v.dpy, VA_RT_FORMAT_YUV420, w, h, ids, 2, nullptr, 0),
           "vaCreateSurfaces");
  v.prev = ids[0];
  v.next = ids[1];

  auto upload = [&](VASurfaceID sid, const std::vector<std::uint8_t> &y) {
    VAImage image;
    check_va(vaDeriveImage(v.dpy, sid, &image), "vaDeriveImage");
    void *p = nullptr;
    check_va(vaMapBuffer(v.dpy, image.buf, &p), "vaMapBuffer");
    auto *base = static_cast<std::uint8_t *>(p);
    for (int row = 0; row < h; ++row)
      std::memcpy(base + image.offsets[0] + row * image.pitches[0], y.data() + row * w, w);
    // Neutral chroma.
    if (image.num_planes > 1) {
      const int ch = h / 2;
      const int cw = image.pitches[1];
      std::memset(base + image.offsets[1], 128, static_cast<std::size_t>(ch) * cw);
    }
    check_va(vaUnmapBuffer(v.dpy, image.buf), "vaUnmapBuffer");
    check_va(vaDestroyImage(v.dpy, image.image_id), "vaDestroyImage");
  };

  std::vector<std::uint8_t> prev(static_cast<std::size_t>(w) * h);
  std::vector<std::uint8_t> next(prev.size());
  for (int y = 0; y < h; ++y) {
    for (int x = 0; x < w; ++x) {
      const float fx = 0.21f * x, fy = 0.17f * y;
      const float val = 128.0f + 60.0f * std::sin(fx) * std::cos(fy);
      prev[static_cast<std::size_t>(y) * w + x] =
          static_cast<std::uint8_t>(std::clamp(val, 0.0f, 255.0f));
    }
  }
  for (int y = 0; y < h; ++y) {
    for (int x = 0; x < w; ++x) {
      const int sx = std::clamp(x - dx, 0, w - 1);
      next[static_cast<std::size_t>(y) * w + x] = prev[static_cast<std::size_t>(y) * w + sx];
    }
  }
  upload(v.prev, prev);
  upload(v.next, next);
  return v;
}

} // namespace

int main() {
  using namespace optical_flow_sdk;
  constexpr int kW = 64;
  constexpr int kH = 48;
  constexpr int kDx = 2;

  try {
    auto surfaces = make_shifted_nv12(kW, kH, kDx);
    // Must bind VA display before first OpenCL context creation.
    opencl_set_va_display(surfaces.dpy);

    OpenCLOpticalFlow of(Preset::Fast);
    if (!of.supports_va_media_sharing()) {
      std::cerr << "cl_intel_va_api_media_sharing not available\n";
      return 2;
    }

    auto d_prev = of.create_u8_image(kW, kH);
    auto d_next = of.create_u8_image(kW, kH);
    auto d_flow = of.create_flow_buffer(kW, kH);

    of.import_va_surface_luma(static_cast<std::uint32_t>(surfaces.prev), d_prev);
    of.import_va_surface_luma(static_cast<std::uint32_t>(surfaces.next), d_next);
    of.calc_device(d_prev, d_next, d_flow);

    FlowField flow;
    of.download_flow(d_flow, flow);
    double epe = 0.0;
    int n = 0;
    for (int y = 8; y < kH - 8; ++y) {
      for (int x = 8; x < kW - 8; ++x) {
        const double eu = flow.dx(x, y) - kDx;
        const double ev = flow.dy(x, y);
        epe += std::sqrt(eu * eu + ev * ev);
        ++n;
      }
    }
    epe /= n;
    std::cout << "va_e2e path=import_va_surface_luma+calc_device EPE=" << epe
              << " sample=" << flow.dx(kW / 2, kH / 2) << "," << flow.dy(kW / 2, kH / 2) << "\n";
    if (epe > 1.5) {
      std::cerr << "VA E2E EPE too high\n";
      return 1;
    }
    std::cout << "PASS\n";
    return 0;
  } catch (const std::exception &ex) {
    std::cerr << "VA E2E failed: " << ex.what() << "\n";
    return 3;
  }
}
