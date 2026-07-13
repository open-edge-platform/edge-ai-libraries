# Benchmarking

ViPPET provides two benchmarking modes for evaluating AI inference pipeline performance on Intel® hardware:

- **Performance Testing** — Run one or more pipelines with a fixed number of streams and measure throughput
  (FPS), system utilization, and optionally latency in real time.
- **Density Testing** — Automatically find the maximum number of concurrent streams that maintain a target
  FPS floor, using an exponential-growth and binary-search algorithm. Density testing supports two modes:
  - **Classic mode** — All pipelines share a single search variable (total stream count) distributed
    according to per-pipeline `stream_rate` ratios.
  - **Mixed mode** — Exactly two pipelines: one is pinned to a fixed stream count, the other is
    incremented by the same algorithm. See
    [Stream Density Testing](./benchmarking/density-testing.md) for details.

Both modes share a common execution configuration and report results through the same job management system.

## Key concepts

| Concept             | Description                                                                                                 |
|---------------------|-------------------------------------------------------------------------------------------------------------|
| **Total FPS**       | Aggregate frames per second across all active streams                                                       |
| **Per Stream FPS**  | Average FPS per individual stream (Total FPS ÷ stream count)                                                |
| **FPS Floor**       | Minimum acceptable per-stream FPS used as the pass/fail threshold in density testing                        |
| **Stream Rate**     | Percentage of total streams allocated to each pipeline in classic density mode (must sum to 100%)           |
| **Fixed Streams**   | Pinned stream count for one pipeline in mixed density mode; the other pipeline is incremented by the search |
| **Output Mode**     | Controls whether output video is saved to file, streamed live, or disabled                                  |
| **Latency Metrics** | Optional end-to-end pipeline latency measurement (avg/min/max) reported per interval                        |

## Workflow overview

1. **Configure** — Select pipelines, set stream counts or density parameters, and choose output options.
2. **Run** — Start the test; ViPPET creates a job and begins executing pipelines as subprocesses.
3. **Monitor** — Real-time system metrics (CPU, GPU, NPU, memory, power) and pipeline metrics (FPS)
   are displayed in the dashboard while the job runs.
4. **Review results** — When the job completes, view final FPS and output videos in the job detail view.

<!--hide_directive
:::{toctree}
:hidden:

./benchmarking/performance-testing
./benchmarking/density-testing
./benchmarking/managing-jobs

:::
hide_directive-->