# Generative AI Hardware Sizing Tool

A comprehensive performance benchmarking and profiling framework designed to evaluate Generative AI applications running on Intel hardware platforms.

---

## Overview

The **Generative AI Hardware Sizing Tool** is a production-ready performance profiling suite that enables performance engineers and developers to accurately measure, analyze, and optimize AI applications on Intel hardware. This framework provides detailed performance metrics, resource utilization monitoring, and statistical analysis to support hardware sizing decisions for GenAI workloads.

### Key Capabilities

- **Performance Benchmarking**: Measure latency, throughput, and token generation metrics under realistic workload conditions
- **Hardware Sizing**: Determine optimal hardware configurations based on performance requirements and resource utilization
- **Multi-Application Support**: Benchmark ChatQnA conversational AI and video processing pipelines
- **Resource Monitoring**: Track CPU, GPU, NPU, and memory utilization with optional Docker-based metrics collection
- **Detailed Reporting**: Generate comprehensive reports with statistical analysis, JSON-formatted metrics, and visualization graphs
- **Load Testing**: Simulate concurrent users using the industry-standard Locust framework

---

## Use Cases

### 1. **ChatQnA Performance Profiling**
- Benchmark Retrieval-Augmented Generation (RAG) chatbot applications
- Measure streaming chat API performance with token-level metrics (TTFT, ITL, TPS)
- Test document upload and processing workflows
- Profile both modular and core ChatQnA architectures
- Support for concurrent user simulation and sustained load testing

### 2. **Video Processing Pipeline Optimization**
- Benchmark video summarization performance across different video formats and resolutions
- Profile semantic video search with embedding generation metrics
- Measure frame extraction and embedding creation throughput
- Optimize video codec handling and frame sampling strategies

### 3. **Hardware Capacity Planning**
- Size CPU, GPU, and memory requirements for production deployments
- Compare performance across different Intel hardware configurations
- Identify bottlenecks and optimization opportunities
- Generate baseline metrics for performance regression testing

### 4. **Load and Stress Testing**
- Simulate multiple concurrent users to measure system behavior under load
- Test API stability and error handling with sustained workloads
- Validate performance degradation curves and system limits
- Support warmup periods to stabilize metrics before formal testing

### 5. **Resource Utilization Analysis**
- Monitor CPU, GPU, NPU usage during application execution
- Track memory consumption and performance counter metrics
- Analyze resource efficiency for different workload configurations
- Identify resource-constrained vs. CPU-constrained bottlenecks

---

## Key Features

### 1. **Multi-Application Support**

#### ChatQnA Applications (Modular & Core)
- Streaming chat API with comprehensive token metrics
- Document upload and RAG context management
- Configurable prompt templates and document processing pipelines
- Support for both modular and simplified core architectures

**Supported Metrics:**
- Latency: End-to-end request response time
- TTFT (Time to First Token): Time until the first token is generated
- ITL (Inter-Token Latency): Average time between consecutive tokens
- TPS (Tokens Per Second): Token generation throughput
- Input/Output Token Counts: Request and response token statistics
- Throughput: Requests processed per second

#### Video Search and Summarization
- Video upload and processing workflows
- Frame-level summarization with LLM-powered analysis
- Semantic search with embedding generation
- Multi-query support for complex video understanding

**Supported Metrics:**
- Video upload time
- Time to first frame summary
- Summarization duration and FPS (frames per second)
- Embedding creation metrics
- Query search latency and throughput
- Video metadata (size, duration, resolution, codecs)

### 2. **Comprehensive Performance Metrics**
- **Latency Metrics**: p99, p90, p75 percentiles, average, min, max
- **Throughput Metrics**: Requests/queries per second, tokens per second
- **Token Metrics**: TTFT, ITL, TPS for streaming responses
- **Resource Metrics**: CPU%, GPU%, NPU%, memory consumption (when enabled)
- **Statistical Analysis**: Detailed distributions and outlier detection

### 3. **Resource Utilization Monitoring**
When enabled, automatically:
- Deploys Docker-based metrics collection service
- Monitors CPU and GPU (Intel discrete GPUs) usage
- Tracks memory consumption and Performance Counter Monitor (PCM) metrics
- Parses QMASSA metrics for detailed performance analysis
- Generates visual graphs of resource utilization over time

### 4. **Flexible YAML-Based Configuration**
- Profile-based test scenarios (small, medium, large inputs)
- Per-API enablement/disabling for modular architectures
- Customizable sampling parameters for video processing
- Support for custom prompts, documents, and queries
- Dynamic configuration loading and validation

### 5. **Statistical Analysis & Comprehensive Reporting**
For each metric, automatically calculates:
- Average, minimum, and maximum values
- Percentile analysis (p99, p90, p75)
- Individual request metrics (JSON format)
- Summary metrics (CSV format)
- Response content for validation and debugging

### 6. **Production-Ready Design**
- Python 3.11-based implementation
- Docker containerization support
- Comprehensive error handling and graceful degradation
- Modular architecture for easy extension
- Detailed logging throughout execution
- Fully automated performance collection and analysis

---

## Directory Structure

```
├── README.md                          # This file
├── Dockerfile                         # Docker container definition
├── requirements.txt                   # Python dependencies
├── profile-runner.py                  # Main entry point
├── common/
│   ├── __init__.py
│   └── utils.py                       # Shared utility functions for configuration, metrics, and reporting
├── data/
│   └── file.txt                       # Sample input data for testing
├── docs/
│   └── user-guide/
│       ├── overview.md                # Detailed technical overview
│       └── get-started.md             # Installation and setup guide
├── profiles/
│   ├── profiles.yaml                  # Input profile definitions
│   ├── chatqna-config.yaml            # ChatQnA modular configuration
│   ├── chatqna-core-config.yaml       # ChatQnA core configuration
│   ├── video-search-config.yaml       # Video search configuration
│   └── video-summary-config.yaml      # Video summarization configuration
└── src/
    ├── __init__.py
    ├── chat_question_and_answer/
    │   ├── __init__.py
    │   ├── chatqna_performance.py      # ChatQnA profiling orchestration
    │   ├── locust_files/               # Locust test scripts for ChatQnA
    │   │   ├── chat.py                 # Streaming chat API tests
    │   │   ├── document.py             # Document upload tests
    │   │   └── stream_log.py           # Streaming log utilities
    │   └── utilities/
    │       ├── jaeger.py               # Jaeger tracing utilities
    │       └── utils.py                # ChatQnA-specific helper functions
    ├── chat_question_and_answer_core/
    │   ├── __init__.py
    │   ├── chatqna_core_performance.py # ChatQnA core profiling orchestration
    │   ├── locust_files/               # Locust test scripts for ChatQnA core
    │   │   ├── document.py             # Document upload tests
    │   │   └── stream_log.py           # Streaming log utilities
    │   └── utilities/
    │       └── utils.py                # ChatQnA core-specific helper functions
    └── video_search_and_summarization/
        ├── __init__.py
        ├── vss_performance.py          # Video profiling orchestration
        ├── locust_files/               # Locust test scripts for video
        │   ├── video_search.py         # Video search tests
        │   └── video_summary.py        # Video summarization tests
        └── utilities/
            └── utils.py                # Video-specific helper functions
```

---

## Usage

### Prerequisites

#### System Requirements
- **CPU**: Intel processor (recommended)
- **RAM**: Minimum 8GB, 16GB+ recommended for video processing
- **Storage**: At least 10GB free space for reports and dependencies
- **Network**: Access to target GenAI application server
- **OS**: Linux (Ubuntu 20.04+ recommended)
- **Python**: Version 3.11 or higher
- **Docker**: Latest version (required only for resource metrics collection)

#### Software Dependencies
```
locust==2.42.5                    # Load testing framework
locust-plugins==5.0.0             # Locust plugins for enhanced metrics
numpy==2.2.6                      # Numerical computing
requests==2.32.4                  # HTTP client library
transformers==4.57.1              # Hugging Face transformers library
PyYAML==6.0.3                     # YAML configuration parsing
pandas==2.3.3                     # Data analysis and processing
matplotlib==3.10.7                # Data visualization
opencv-python==4.12.0.88          # Video processing
moviepy==1.0.3                    # Video editing and processing
```

### Installation

1. **Clone the Repository**
   ```bash
   git clone <repository-url>
   cd generative-ai-hardware-sizing
   ```

2. **Install Python Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Verify Installation**
   ```bash
   python profile-runner.py --help
   ```

### Quick Start

#### Example 1: Profile ChatQnA with Single User
```bash
python profile-runner.py \
  --app=chatqna \
  --input=profiles/chatqna-config.yaml \
  --users=1 \
  --request_count=10 \
  --host_ip=192.168.1.10
```

#### Example 2: Profile ChatQnA Core with Multiple Users and Resource Monitoring
```bash
python profile-runner.py \
  --app=chatqna_core \
  --input=profiles/chatqna-core-config.yaml \
  --users=5 \
  --request_count=100 \
  --spawn_rate=2 \
  --host_ip=192.168.1.10 \
  --collect_resource_metrics=yes
```

#### Example 3: Profile Video Summary and Search
```bash
python profile-runner.py \
  --app=video_summary_search \
  --input=profiles/video-search-config.yaml \
  --users=2 \
  --request_count=5 \
  --host_ip=192.168.1.10 \
  --collect_resource_metrics=yes \
  --warmup_time=30
```

### Command-Line Arguments

```
--app                      Application to profile
                          Options: chatqna, chatqna_core, video_summary_search
                          Default: chatqna

--input                    Path to configuration YAML file
                          Default: config.yaml

--users                    Number of concurrent users to simulate
                          Default: 1

--request_count            Total number of requests per user
                          Default: 1

--spawn_rate               Rate at which users are spawned per second
                          Default: 1

--host_ip                  IP address of the machine where the application is deployed
                          Required for proper testing

--collect_resource_metrics Enable collection of resource metrics (CPU, GPU, memory, etc.)
                          Options: yes, no
                          Default: no

--warmup_time              Duration in seconds for warmup requests before performance testing
                          Default: 0
```

### Configuration

Configuration files are YAML-based and located in the `profiles/` directory. Key configuration sections:

#### Global Configuration
```yaml
global:
  report_dir: "reports"              # Output directory for results
  perf_tool_repo: ""                 # Optional: performance tool repository
```

#### API Configuration
```yaml
apis:
  stream_log_api:
    enabled: true                    # Enable/disable chat API testing
    input_profile: "stream_log_small_text"
  document_api:
    enabled: true                    # Enable/disable document upload testing
    input_profile: "document_profile"
```

#### Video Configuration
```yaml
video:
  video_summary:
    enabled: true                    # Enable/disable video summarization
    input_profile: "video_summary_wsf"
  video_search:
    enabled: true                    # Enable/disable video search
    input_profile: "video_search_wsf"
```

### Understanding Results

#### Output Directory Structure
```
reports/
├── chatqna_modular_20240120_153022/
│   ├── chat_api_results.json         # Individual chat request metrics
│   ├── chat_api_summary.csv          # Aggregated chat metrics
│   ├── document_api_results.json     # Individual document upload metrics
│   ├── document_api_summary.csv      # Aggregated document metrics
│   ├── locust_report.html            # Locust HTML report
│   ├── resource_metrics.csv          # CPU, GPU, memory usage (if enabled)
│   └── graphs/
│       ├── latency.png               # Latency distribution graphs
│       ├── throughput.png            # Throughput graphs
│       ├── tokens_per_second.png     # Token generation rate graphs
│       └── resource_utilization.png  # CPU/GPU/memory usage graphs
```

#### Metric Interpretation

**Latency Metrics:**
- `TTFT (Time to First Token)`: Measures API responsiveness for streaming responses
- `ITL (Inter-Token Latency)`: Indicates token generation speed consistency
- `TPS (Tokens Per Second)`: Overall token generation throughput

**Throughput Metrics:**
- Requests processed per second
- Token generation rate
- Query response rate

**Resource Metrics:**
- CPU utilization percentage
- GPU utilization percentage
- Memory consumption (RSS)
- Performance counter metrics

### Common Use Cases

#### 1. Baseline Performance Measurement
```bash
python profile-runner.py \
  --app=chatqna \
  --input=profiles/chatqna-config.yaml \
  --users=1 \
  --request_count=100 \
  --host_ip=<target-ip>
```


#### 3. Video Processing Benchmark
```bash
python profile-runner.py \
  --app=video_summary_search \
  --input=profiles/video-search-config.yaml \
  --users=1 \
  --request_count=10 \
  --host_ip=<target-ip> \
  --collect_resource_metrics=yes
```


---

## Docker Support

### Building Docker Image
```bash
docker build -t gen-ai-hw-sizing:latest .
```

### Running with Docker
```bash
docker run --network host \
  gen-ai-hw-sizing:latest \
  --app=chatqna \
  --input=profiles/chatqna-config.yaml \
  --users=1 \
  --request_count=10 \
  --host_ip=192.168.1.10
```


---

## Architecture

### High-Level Flow

1. **Configuration Loading**: Parse YAML configuration files for test parameters
2. **API Discovery**: Identify enabled APIs/modules to profile
3. **Warmup (Optional)**: Execute warmup requests to stabilize metrics
4. **Performance Metrics Collection**: Start resource monitoring (if enabled)
5. **Load Testing**: Execute Locust-based tests with concurrent users
6. **Metrics Aggregation**: Collect and process performance data
7. **Analysis & Reporting**: Generate statistical analysis and visualizations
8. **Report Generation**: Create comprehensive output reports

### Technology Stack

- **Load Testing**: Locust (Python-based load testing framework)
- **Metrics Collection**: Custom Python scripts with Docker support
- **Data Analysis**: NumPy, Pandas for statistical calculations
- **Visualization**: Matplotlib for graph generation
- **Configuration**: PyYAML for flexible configuration management
- **Video Processing**: OpenCV, MoviePy for video analysis
- **HTTP Client**: Requests library for API testing

---

## Performance Considerations

### Optimization Tips

1. **Adjust User Spawn Rate**: Start with low spawn rates to avoid overwhelming the target application
2. **Request Count Strategy**: Use larger request counts for better statistical significance
3. **Warmup Period**: Include warmup time for applications that need initialization
4. **Resource Monitoring Overhead**: Enabling resource metrics collection adds slight overhead
5. **Video Profile Selection**: Choose appropriate video profiles based on your hardware capabilities

### Hardware Recommendations

| Workload Type | CPU Cores | RAM | GPU | Storage |
|---|---|---|---|---|
| ChatQnA (small scale) | 4+ | 8GB | Optional | 10GB |
| ChatQnA (medium scale) | 8+ | 16GB | Intel GPU | 20GB |
| ChatQnA (large scale) | 16+ | 32GB | Intel GPU | 50GB |
| Video Processing | 8+ | 16GB | Intel GPU (4GB+) | 100GB+ |

---

## Advanced Features

### Custom Profiles

Create custom profiles in `profiles/profiles.yaml`:

```yaml
profiles:
  custom_chat_profile:
    input_type: "text"
    input_size: "custom"
    prompt: "Your custom prompt here"
    max_tokens: "2048"
    expected_output_size: "large"

  custom_video_profile:
    input_type: "video"
    input_size: "large"
    files:
      - name: "custom_video.mp4"
        path: "data/custom_video.mp4"
    queries:
      - query: "Your custom query"
```

### Resource Metrics Interpretation

- **CPU Utilization**: Higher values indicate CPU-bound operations
- **GPU Utilization**: Shows GPU acceleration efficiency
- **Memory Usage**: Tracks application memory footprint
- **PCM Metrics**: Advanced performance counter data for detailed analysis

---

## Troubleshooting

### Common Issues

**Issue: Connection refused error**
- Ensure target application is running and accessible
- Verify correct IP address and port
- Check firewall rules

**Issue: Out of memory error**
- Reduce number of concurrent users
- Reduce request count
- Increase available system memory

**Issue: Resource metrics collection fails**
- Verify Docker is installed and running
- Check Docker daemon permissions
- Ensure sufficient disk space

**Issue: Video processing errors**
- Verify video file exists and is valid
- Check video codec compatibility
- Ensure sufficient disk space for processing


---

## Contributing

Contributions are welcome! Please ensure:
- Code follows Python PEP 8 style guide
- All tests pass
- Documentation is updated
- New features include appropriate metrics collection

---

## License

Copyright (C) 2024 Intel Corporation
SPDX-License-Identifier: Apache-2.0

---

## Support & Documentation

- **Detailed Technical Overview**: See [docs/user-guide/overview.md](docs/user-guide/overview.md)
- **Installation & Setup Guide**: See [docs/user-guide/get-started.md](docs/user-guide/get-started.md)
- **Configuration Profiles**: See [profiles/](profiles/) directory
- **Issue Reporting**: Submit issues with detailed logs and reproduction steps

---

## Acknowledgments

Built with support from the Intel AI Platform team to enable accurate performance profiling and hardware sizing for generative AI workloads on Intel hardware.

For questions or feedback, please contact the Intel generative AI team or submit issues to the project repository.
