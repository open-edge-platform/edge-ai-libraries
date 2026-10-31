//********************************************************//
// Intel SYCL/DPC++ SIFT extractor                       //
// SyclImage implementation                              //
//********************************************************//

#include "syclImage.h"
#include <cstdlib>
#include <cstdio>

// ---- Global SYCL queue -----------------------------------------------
static sycl::queue *g_queue = nullptr;

sycl::queue &GetSyclQueue() {
  if (!g_queue) {
    g_queue = new sycl::queue(
        sycl::default_selector_v,
        [](sycl::exception_list el) {
          for (auto &e : el) {
            try {
              std::rethrow_exception(e);
            } catch (sycl::exception &ex) {
              fprintf(stderr, "SYCL async error: %s\n", ex.what());
            }
          }
        },
        sycl::property::queue::in_order{});
  }
  return *g_queue;
}

// ---- Integer utilities -----------------------------------------------
int iDivUp(int a, int b) { return (a % b != 0) ? (a / b + 1) : (a / b); }
int iDivDown(int a, int b) { return a / b; }
int iAlignUp(int a, int b) { return (a % b != 0) ? (a - a % b + b) : a; }
int iAlignDown(int a, int b) { return a - a % b; }

// ---- SyclImage -------------------------------------------------------
SyclImage::SyclImage()
    : width(0), height(0), pitch(0), h_data(nullptr), d_data(nullptr),
      d_internalAlloc(false), h_internalAlloc(false) {}

SyclImage::~SyclImage() {
  auto &q = GetSyclQueue();
  if (d_internalAlloc && d_data != nullptr)
    sycl::free(d_data, q);
  if (h_internalAlloc && h_data != nullptr)
    free(h_data);
  d_data = nullptr;
  h_data = nullptr;
}

void SyclImage::Allocate(int w, int h, int p, bool withHost, float *devMem,
                         float *hostMem) {
  width = w;
  height = h;
  pitch = p;
  d_data = devMem;
  h_data = hostMem;
  if (!devMem) {
    auto &q = GetSyclQueue();
    d_data = sycl::malloc_device<float>((size_t)pitch * height, q);
    if (!d_data)
      fprintf(stderr, "SyclImage: failed to allocate device memory (%d floats)\n",
              pitch * height);
    d_internalAlloc = true;
  }
  if (withHost && !hostMem) {
    h_data = (float *)malloc(sizeof(float) * (size_t)pitch * height);
    if (!h_data)
      fprintf(stderr, "SyclImage: failed to allocate host memory\n");
    h_internalAlloc = true;
  }
}

double SyclImage::Download() {
  TimerGPU timer;
  auto &q = GetSyclQueue();
  if (d_data && h_data) {
    // h_data is packed (stride=width); d_data is pitched (stride=pitch).
    // Copy row by row when pitch != width.
    if (pitch == width) {
      q.memcpy(d_data, h_data, sizeof(float) * (size_t)width * height).wait();
    } else {
      for (int y = 0; y < height; ++y) {
        q.memcpy(d_data + (size_t)y * pitch, h_data + (size_t)y * width,
                 sizeof(float) * width);
      }
      q.wait();
    }
  }
  double t = timer.read();
#ifdef VERBOSE
  printf("Download time =               %.2f ms\n", t);
#endif
  return t;
}

double SyclImage::Readback() {
  TimerGPU timer;
  auto &q = GetSyclQueue();
  if (d_data && h_data) {
    if (pitch == width) {
      q.memcpy(h_data, d_data, sizeof(float) * (size_t)width * height).wait();
    } else {
      for (int y = 0; y < height; ++y) {
        q.memcpy(h_data + (size_t)y * width, d_data + (size_t)y * pitch,
                 sizeof(float) * width);
      }
      q.wait();
    }
  }
  double t = timer.read();
#ifdef VERBOSE
  printf("Readback time =               %.2f ms\n", t);
#endif
  return t;
}
