# How To Use ViPPET

The [gvapython modules article](./how-to-guides/use-gvapython-scripts.md) explains how to
add user-defined Python scripts that can be loaded as modules by the `gvapython` element.

The [video generator article](./how-to-guides/use-video-generator.md) explains how to
use the video generator to create composite videos from images stored in subdirectories.

The [pipeline configuration article](./how-to-guides/configure-pipelines.md) explains step-by-step how to configure
and test AI pipelines using ViPPET's Pipeline Builder, from creating a new pipeline, editing the pipeline elements,
to demonstrating running pipelines on both CPU and GPU to compare performance.

The [performance testing article](./how-to-guides/performance-testing.md) covers performance testing of single pipelines
as well as multiple pipelines running concurrently.

The [density testing article](./how-to-guides/density-testing.md) explains how to find the maximum sustainable stream
density for a target FPS floor.



### Performance Testing Capabilities

**Pipeline Testing Modes**:

- **Single Pipeline Testing**: Test individual AI pipelines with configurable stream counts to
  measure baseline performance. Users can specify the number of concurrent streams for
  comprehensive performance analysis.
- **Multi-Pipeline Concurrent Testing**: Evaluate system performance under complex workloads by
  running multiple different pipelines simultaneously. Each pipeline can be configured with its own
  stream count, simulating real-world deployment scenarios where multiple AI workloads compete for
  system resources.

**Testing Configuration Options**:

- **Output Video Validation** (*Keep pipeline output*): Capture and save processed video outputs
  during performance testing to verify that AI inference quality is maintained under load
  conditions.
- **Live Preview Validation** (*Enable live preview*): Monitor real-time video streams during
  testing to immediately detect visual artifacts, frame drops, or quality degradation as they
  occur.
- **Continuous Loop Testing** (*Run pipeline in loop*): Execute continuous testing cycles to
  evaluate system stability and performance consistency over extended periods.

**Real-Time Monitoring**:

During test execution, a metrics dashboard appears on the right side displaying real-time
performance data including Total FPS, Per Stream FPS, CPU frequency, GPU power usage, and memory
utilization. This enables immediate identification of bottlenecks and resource constraints.

### Density Testing

**Automated Stream Density Discovery**:
Determine the maximum number of concurrent streams your hardware can sustain while maintaining a minimum FPS
threshold.
The density test automatically scales up stream counts until performance drops below the specified `fps_floor`,
providing precise hardware capacity measurements.

**Multi-Pipeline Density Analysis**:
Test complex workload scenarios by running multiple different pipelines simultaneously with configurable stream
rate ratios.
For example, allocate 70% of streams to object detection and 30% to license plate recognition to simulate
real-world deployment conditions.

**FPS Floor Validation**:
Set minimum acceptable performance thresholds (for example, 30 FPS per stream)
and automatically discover the maximum sustainable workload.
This eliminates guesswork in capacity planning and ensures deployments meet performance requirements.

**Capacity Planning Support**:
Generate precise hardware sizing recommendations by measuring actual stream density under controlled conditions.
Results show exactly how many concurrent video streams each hardware configuration can process
while maintaining quality thresholds.


## Example: Real-Time License Plate Recognition (ALPR)

This use case mirrors a common smart city workload and can be reproduced in ViPPET to compare Intel® platforms for
license plate analytics.

**Goal**: Detect vehicles, localize license plates, and read plate text from live or recorded video in real time.

For the complete architecture, hardware variants (CPU/GPU/GPU+NPU), pipeline examples, and benchmark guidance, see:

- [License Plate Recognition Pipeline Guide](docs/user-guide/how-to-guides/license-plate-recognition-pipeline.md)

Use ViPPET's built-in **Performance Test** and **Density Test** to collect measured platform-specific throughput,
latency, utilization, and sustainable stream density.

<!--hide_directive
:::{toctree}
:maxdepth: 2
:hidden:

./how-to-guides/use-gvapython-scripts
./how-to-guides/use-video-generator
./how-to-guides/configure-pipelines
./how-to-guides/performance-testing
Run Density Tests <./how-to-guides/density-testing.md>
Use Plates Recognition <./how-to-guides/license-plate-recognition-pipeline.md>
Use LPR API <./how-to-guides/license-plate-recognition-api.md>

:::
hide_directive-->