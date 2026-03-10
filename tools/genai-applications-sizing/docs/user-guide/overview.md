# Generative AI Hardware Sizing Tool - Overview

## Overview

The **Generative AI Hardware Sizing Tool** is a comprehensive performance benchmarking and profiling framework designed to evaluate Generative AI applications running on Intel hardware platforms. This tool enables performance engineers and developers to:

- **Measure and analyze** the performance characteristics of AI applications under various load conditions
- **Size hardware requirements** accurately based on real-world usage patterns
- **Collect resource utilization metrics** (CPU, GPU, NPU, memory) during application execution
- **Generate detailed performance reports** with statistical analysis and visualizations

The framework currently supports three main application types:
1. **ChatQnA (Modular)** - Question-answering chatbot with RAG (Retrieval-Augmented Generation)
2. **ChatQnA (Core)** - Simplified core ChatQnA implementation
3. **Video Summary & Search** - Video content analysis, summarization, and semantic search

The tool leverages **Locust**, a powerful load testing framework, to simulate concurrent users and measure application performance under realistic workload conditions.

---

## Key Features

### 1. **Multi-Application Support**
- **ChatQnA Applications**: Test text-based conversational AI with document retrieval capabilities
  - Streaming chat API with token-level metrics (TTFT, ITL, TPS)
  - Document upload and RAG context management
  - Support for both modular and core architectures
- **Video Applications**: Benchmark video processing pipelines
  - Video summarization with frame-level analysis
  - Semantic video search with embedding generation
  - Support for multiple video codecs and resolutions

### 2. **Comprehensive Performance Metrics**

#### Chat API Metrics:
- **Latency**: End-to-end request response time
- **TTFT (Time to First Token)**: Time until the first token is generated
- **ITL (Inter-Token Latency)**: Average time between consecutive tokens
- **TPS (Tokens Per Second)**: Token generation throughput
- **Input/Output Token Counts**: Request and response token statistics
- **Throughput**: Requests processed per second

#### Video Summary Metrics:
- **Video Upload Time**: Time to upload video file to server
- **Time to First Frame Summary**: Latency to first frame summary generation
- **Video Summarization Duration**: Total time to summarize entire video
- **Summarization FPS**: Frames processed per second during summarization
- **Video metadata**: File size, duration, resolution, FPS, codecs

#### Video Search Metrics:
- **Video Upload Time**: Time to upload video files
- **Embedding Creation Time**: Time to generate video embeddings
- **Embeddings Creation FPS**: Frame extraction and embedding generation rate
- **Query Search Duration**: Time to execute semantic search queries
- **Search Throughput**: Queries processed per second

### 3. **Resource Utilization Monitoring**
When enabled, the tool automatically:
- Deploys a Docker-based metrics collection service
- Monitors CPU, GPU (Intel discrete GPUs), NPU usage
- Tracks memory consumption and PCM (Performance Counter Monitor) metrics
- Parses QMASSA metrics
- Generates visual graphs of resource utilization over time

### 4. **Flexible Configuration System**
- **YAML-based configuration** for easy customization
- **Profile definitions** for different test scenarios (small, medium, large inputs)
- **Modular API enablement** - enable/disable specific APIs independently
- **Customizable sampling parameters** for video processing
- **Support for custom prompts and queries**

### 5. **Statistical Analysis & Reporting**
For each metric, the tool calculates:
- Average, Minimum, Maximum values
- Percentiles: p99, p90, p75
- Individual request metrics (JSON format)
- Summary metrics (CSV format)
- Response content saved for validation

### 6. **Production-Ready Design**
- Docker containerization support
- Error handling and graceful degradation
- Comprehensive logging throughout execution
- Modular architecture for easy extension
- Python 3.11 based implementation

---

## Technical Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     profile-runner.py (Entry Point)              │
│                  Command-line argument parser                    │
└───────────────────────┬─────────────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
        ▼               ▼               ▼
┌───────────────┐ ┌───────────┐ ┌─────────────────────┐
│  ChatQnA      │ │  ChatQnA  │ │ Video Summary/      │
│  Modular      │ │  Core     │ │ Search              │
└───────┬───────┘ └─────┬─────┘ └──────────┬──────────┘
        │               │                   │
        │               │                   │
        ▼               ▼                   ▼
┌────────────────────────────────────────────────────────┐
│           Common Utilities (common/utils.py)            │
│  - Configuration management                             │
│  - Metrics calculation and reporting                    │
│  - Video processing utilities                           │
│  - Performance tool integration                         │
└────────────────────────────────────────────────────────┘
        │
        ▼
┌────────────────────────────────────────────────────────┐
│              Locust Load Testing Engine                 │
│  - User simulation                                      │
│  - Concurrent request execution                         │
│  - Response streaming handling                          │
└────────────────────────────────────────────────────────┘
        │
        ▼
┌────────────────────────────────────────────────────────┐
│           Target GenAI Application APIs                 │
│  - Chat endpoint (streaming)                            │
│  - Document upload endpoint                             │
│  - Video upload/summary/search endpoints                │
└────────────────────────────────────────────────────────┘
```

### Directory Structure

```
.
├── profile-runner.py          # Main entry point
├── requirements.txt           # Python dependencies
├── Dockerfile                 # Container image definition
├── README.md                  # Project documentation
│
├── common/                    # Shared utilities
│   ├── __init__.py
│   └── utils.py              # Core utility functions
│
├── profiles/                  # Test configurations
│   ├── profiles.yaml         # Input profile definitions
│   ├── chatqna-config.yaml   # ChatQnA modular config
│   ├── chatqna-core-config.yaml
│   ├── video-search-config.yaml
│   └── video-summary-config.yaml
│
├── data/                      # Test input files
│   ├── file1.txt
│   ├── file2.txt
│   └── *.mp4                 # Video files
│
├── src/                       # Application-specific modules
│   ├── chatqna_modular/
│   │   ├── chatqna_performance.py
│   │   ├── locust_files/     # Locust test definitions
│   │   │   ├── chat.py
│   │   │   ├── document.py
│   │   │   └── stream_log.py
│   │   └── utilities/        # Helper functions
│   │
│   ├── chatqna_core/
│   │   ├── chatqna_core_performance.py
│   │   ├── locust_files/
│   │   └── utilities/
│   │
│   └── video_summary_search/
│       ├── vss_performance.py
│       ├── locust_files/
│       │   ├── video_summary.py
│       │   └── video_search.py
│       └── utilities/
│
├── reports/                   # Generated performance reports
│   └── <app>_<timestamp>/    # Timestamped report directories
│       ├── chat/             # Chat API metrics
│       ├── summary/          # Video summary metrics
│       ├── search/           # Video search metrics
│       ├── responses/        # API response content
│       └── perf_tool_logs/   # Resource utilization metrics
│
└── performance-tools/         # Intel performance monitoring (cloned at runtime)
    ├── docker/               # Metrics collector Docker setup
    └── benchmark-scripts/    # Parsing and visualization scripts
```

### Component Details

#### 1. **profile-runner.py** (Main Controller)
- Entry point for all benchmarking operations
- Parses command-line arguments:
  - `--app`: Application to test (chatqna, chatqna_core, video_summary_search)
  - `--input`: Path to configuration YAML file
  - `--users`: Number of concurrent users to simulate
  - `--request_count`: Total requests per user
  - `--spawn_rate`: User spawn rate per second
  - `--host_ip`: Target application server IP
  - `--collect_resource_metrics`: Enable/disable resource monitoring
- Routes execution to appropriate application module

#### 2. **Configuration System** (profiles/)
- **profiles.yaml**: Defines input profiles with varying sizes and modalities
  - Text profiles: small (100 words), medium (220 tokens)
  - Video profiles: single video, multiple videos
  - Customizable prompts, queries, and payloads
  
- **Application configs**: Define API endpoints and settings
  - Global settings: report directory, performance tool repo
  - API-specific settings: endpoints, service names, input profiles
  - Enable/disable individual APIs

#### 3. **Common Utilities** (common/utils.py)
Core functionality used across all applications:
- **Configuration Management**:
  - `read_yaml_config()`: Parse YAML configuration files
  - `get_global_config()`, `get_stream_log_config()`, etc.
  - `get_profile_details()`: Extract profile information

- **Metrics Collection**:
  - `calculate_metrics()`: Statistical analysis (avg, min, max, percentiles)
  - `write_metrics()`, `write_metrics_to_csv()`: Save metrics to JSON/CSV
  - `write_video_summary_metrics()`, `write_video_search_metrics()`

- **Video Processing**:
  - `get_video_details()`: Extract video metadata (duration, FPS, codec)
  - `upload_video_file()`: Upload video to server
  - `embedding_video_file()`: Trigger embedding generation
  - `wait_for_video_summary_complete()`: Poll for completion

- **Performance Tool Integration**:
  - `start_perf_tool()`: Clone repo, start Docker metrics collector
  - `stop_perf_tool()`: Stop Docker container
  - `plot_graphs()`: Parse metrics and generate visualizations

- **API Helpers**:
  - `upload_document_before_conversation()`: Upload RAG documents
  - `delete_existing_docs()`: Clear previous documents
  - `get_response()`: Stream and save API responses

#### 4. **Locust Test Files** (src/*/locust_files/)
Each Locust file defines a `HttpUser` class with test tasks:

- **chat.py** (ChatQnA):
  ```python
  class ChatHwSize(HttpUser):
      @task
      def chat_hw_sizing(self):
          # Send POST request with prompt
          # Stream response chunks
          # Calculate TTFT, ITL, TPS metrics
          # Save response and metrics
  ```

- **document.py** (Document Upload):
  ```python
  class DocumentHwSize(HttpUser):
      @task
      def document_upload(self):
          # Upload document files
          # Measure upload latency
          # Calculate throughput
  ```

- **video_summary.py**:
  ```python
  class VideoSummaryHwSize(HttpUser):
      @task
      def summarize_video(self):
          # Upload video file
          # Trigger summarization with payload
          # Wait for completion
          # Calculate TTFT, duration, FPS
  ```

- **video_search.py**:
  ```python
  class VideoSearchHwSize(HttpUser):
      def on_start(self):
          # Upload all video files once
          # Generate embeddings
      
      @task
      def search_video(self):
          # Execute search queries cyclically
          # Measure search latency
  ```

#### 5. **Performance Monitoring** (performance-tools/)
External repository cloned at runtime:
- **Docker-based metrics collector**: Runs as background container
- **Scripts**:
  - `parse_qmassa_metrics_to_json.py`: Parse GPU profiling data
  - `usage_graph_plot.py`: Generate CPU/GPU/NPU usage graphs
- **Outputs**: CSV metrics, JSON parsed data, PNG/SVG graphs

#### 6. **Application Modules** (src/*)
Each application has a main performance function:

```python
def chatqna_modular_performance(users, request_count, spawn_rate, 
                                ip, input_file, collect_resource_metrics):
    # 1. Validate inputs
    # 2. Load configuration
    # 3. Create timestamped report directory
    # 4. Start performance tool (if enabled)
    # 5. Run Locust tests for enabled APIs
    # 6. Stop performance tool and generate graphs
```

### Data Flow

1. **Initialization**:
   ```
   User Command → profile-runner.py → Parse Arguments → Load Config
   ```

2. **Setup Phase**:
   ```
   Create Report Directory → Start Perf Tool → Upload Documents/Videos (if needed)
   ```

3. **Load Testing**:
   ```
   Locust Spawns Users → Each User Executes Tasks → Concurrent Requests
   ```

4. **Request Processing** (Chat API Example):
   ```
   Send POST /chat → Stream Response Chunks → Calculate TTFT
   → Continue Streaming → Calculate ITL → Response Complete
   → Calculate Latency, TPS → Save Metrics
   ```

5. **Metrics Collection**:
   ```
   Individual Request Metrics → Aggregate Statistics → Write JSON
   → Calculate Summary (Avg, Min, Max, Percentiles) → Write CSV
   ```

6. **Resource Monitoring** (Parallel):
   ```
   Metrics Collector Container → Poll System Resources → Log to CSV
   ```

7. **Cleanup & Reporting**:
   ```
   Stop Perf Tool → Parse Metrics → Generate Graphs → Final Report
   ```

### Technology Stack

- **Language**: Python 3.11
- **Load Testing**: Locust 2.42.5
- **HTTP Client**: requests 2.32.4
- **Data Processing**: 
  - numpy 2.2.6 (statistical calculations)
  - pandas 2.3.3 (data manipulation)
- **Video Processing**: 
  - opencv-python 4.12.0.88
  - moviepy 1.0.3
- **Visualization**: matplotlib 3.10.7
- **AI/ML**: transformers 4.57.1 (tokenization)
- **Configuration**: PyYAML 6.0.3
- **Containerization**: Docker (metrics collection)
- **Performance Monitoring**: Intel Retail Performance Tools

---

## How to Use the Application

### Prerequisites

1. **System Requirements**:
   - Linux operating system (tested on Ubuntu)
   - Python 3.11 or higher
   - Docker (for resource metrics collection)
   - Network access to target GenAI application

2. **Target Application**:
   - A running instance of ChatQnA or Video Summary/Search application
   - Known IP address and port numbers for API endpoints
   - API endpoints must be accessible from the host running this tool

### Installation

#### Option 1: Local Installation

```bash
# 1. Clone the repository
cd /path/to/workspace

# 2. Create and activate virtual environment
python3.11 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

#### Option 2: Docker Installation

```bash
# Build Docker image
docker build -t genai-hw-sizing:latest .

# Run container
docker run -it --network host \
    -v $(pwd)/profiles:/app/profiles \
    -v $(pwd)/data:/app/data \
    -v $(pwd)/reports:/app/reports \
    genai-hw-sizing:latest \
    --app=chatqna --input=profiles/chatqna-config.yaml --host_ip=<IP>
```

### Configuration

#### Step 1: Prepare Input Data

Place your test data in the `data/` directory:
```bash
# For ChatQnA: Text documents
cp your_document.txt data/

# For Video: Video files
cp your_video.mp4 data/
```

#### Step 2: Define Input Profiles

Edit `profiles/profiles.yaml` to define test scenarios:

```yaml
profiles:
  my_custom_profile:
    input_type: "text"
    input_size: "small"
    files:
      - name: "my_document.txt"
        path: "data/my_document.txt"
    prompt: "Your custom prompt here"
    max_tokens: "1024"
```

#### Step 3: Configure Application Settings

Edit the appropriate config file (e.g., `profiles/chatqna-config.yaml`):

```yaml
global:
  report_dir: 'reports'
  input_profiles_path: 'profiles/profiles.yaml'
  perf_tool_repo: 'https://github.com/intel-retail/performance-tools.git'

apis:
  stream_log:
    enabled: true
    service_name: 'chatqna'
    endpoints:
      chat: '8101/v1/chatqna/chat'      # Update port and path
      document: '8101/v1/dataprep/documents'
    input_profile: 'my_custom_profile'  # Reference your profile
```

### Running Benchmarks

#### Example 1: ChatQnA with 10 Concurrent Users

```bash
# Activate virtual environment
source venv/bin/activate

# Run benchmark
python profile-runner.py \
    --app=chatqna \
    --input=profiles/chatqna-config.yaml \
    --users=10 \
    --request_count=5 \
    --spawn_rate=2 \
    --host_ip=192.168.1.100 \
    --collect_resource_metrics=yes
```

**Parameters Explained**:
- `--app=chatqna`: Test ChatQnA modular application
- `--users=10`: Simulate 10 concurrent users
- `--request_count=5`: Each user sends 5 requests (total: 50 requests)
- `--spawn_rate=2`: Spawn 2 new users per second
- `--host_ip=192.168.1.100`: Target application server
- `--collect_resource_metrics=yes`: Enable CPU/GPU monitoring

#### Example 2: Video Summary without Resource Metrics

```bash
python profile-runner.py \
    --app=video_summary_search \
    --input=profiles/video-summary-config.yaml \
    --users=1 \
    --request_count=3 \
    --host_ip=<IP_ADDRESS_OF_APP_DEPLOYED> \
    --collect_resource_metrics=no
```

#### Example 3: Video Search with Multiple Videos

```bash
python profile-runner.py \
    --app=video_summary_search \
    --input=profiles/video-search-config.yaml \
    --users=1 \
    --request_count=10 \
    --host_ip=<IP_ADDRESS_OF_APP_DEPLOYED> \
    --collect_resource_metrics=yes
```

### Understanding Reports

After execution, reports are saved in timestamped directories:

```
reports/
└── chatqna_modular_20251125_125955/
    ├── chat/
    │   ├── chat_api_individual_metrics.json   # Per-request metrics
    │   ├── chat_api_summary_metrics.csv       # Statistical summary
    │   └── responses/
    │       └── chat_response_*.txt            # API responses
    │
    └── perf_tool_logs/                        # If resource metrics enabled
        ├── npu_usage.csv                      # NPU utilization
        ├── pcm.csv                            # CPU performance counters
        ├── qmassa1-*-parsed.json              # Parsed GPU metrics
        └── *.png                              # Usage graphs
```

#### Interpreting Metrics

**chat_api_summary_metrics.csv**:
```csv
Metric,Avg,Min,Max,p99,p90,p75
Request Latency (ms),2500.5,1800.2,3200.8,3100.5,2900.3,2700.1
Time to First Token (ms),450.3,350.1,600.5,580.2,520.4,490.3
Inter Token Latency (ms),25.5,20.1,35.8,34.5,30.2,28.1
Tokens Per Second,39.2,28.0,49.8,45.6,42.3,40.1
Throughput,4.5,NA,NA,NA,NA,NA
```

**Interpretation**:
- **Avg Request Latency**: 2.5 seconds average response time
- **TTFT**: Users wait ~450ms for first token
- **ITL**: ~25ms between tokens (smooth streaming)
- **TPS**: ~39 tokens/second generation rate
- **p99**: 99% of requests complete within shown time

### Advanced Usage

#### Custom Locust Parameters

For fine-grained control, you can directly run Locust:

```bash
cd src/chatqna_modular/locust_files

locust -f chat.py \
    --host=http://192.168.1.100 \
    --users=50 \
    --spawn-rate=5 \
    --run-time=5m \
    --chat_endpoint=8101/v1/chatqna/chat \
    --prompt="Your custom prompt" \
    --report_dir=../../reports/custom_test \
    --headless
```

#### Batch Testing Multiple Configurations

Create a shell script to test multiple scenarios:

```bash
#!/bin/bash

for users in 1 5 10 20 50; do
    echo "Testing with $users users..."
    python profile-runner.py \
        --app=chatqna \
        --input=profiles/chatqna-config.yaml \
        --users=$users \
        --request_count=10 \
        --spawn_rate=5 \
        --host_ip=192.168.1.100 \
        --collect_resource_metrics=yes
    
    sleep 60  # Wait between tests
done
```

#### Video Summarization with Custom Payloads

Modify sampling parameters in `profiles.yaml`:

```yaml
video_summary_custom:
  input_type: "video"
  files:
    - name: "my_video.mp4"
      path: "data/my_video.mp4"
  payload:
    '{"evam": {"evamPipeline": "video_ingestion"},
      "sampling": {
          "chunkDuration": 10,     # 10-second chunks
          "samplingFrame": 8,      # 8 frames per chunk
          "frameOverlap": 2,       # 2 frames overlap
          "multiFrame": 10         # 10 frames for multi-frame analysis
      },
      "prompts": {
          "framePrompt": "Describe the action in these frames...",
          "summaryMapPrompt": "Combine these summaries..."
      }
    }'
```

### Troubleshooting

#### Common Issues

1. **Connection Refused**:
   - Verify target application is running: `curl http://<IP>:<PORT>/health`
   - Check firewall rules: `sudo ufw status`
   - Ensure correct IP and port in config files

2. **Performance Tool Fails to Start**:
   - Check Docker is running: `docker ps`
   - Verify network connectivity: `ping github.com`
   - Manually clone repo: `git clone https://github.com/intel-retail/performance-tools.git`

3. **Out of Memory**:
   - Reduce `--users` or `--request_count`
   - Process videos in smaller batches
   - Increase system swap space

4. **Slow Video Processing**:
   - Check video codec compatibility
   - Reduce `samplingFrame` in payload
   - Use lower resolution videos for testing

#### Logs and Debugging

Enable verbose logging:
```python
# Add to profile-runner.py or relevant module
import logging
logging.basicConfig(level=logging.DEBUG)
```

Check Locust logs:
```bash
# Locust saves logs to stdout, redirect to file
python profile-runner.py ... 2>&1 | tee execution.log
```

### Best Practices

1. **Start Small**: Begin with 1 user, 1 request to validate configuration
2. **Gradual Scaling**: Increase load incrementally (1 → 5 → 10 → 20 users)
3. **Warm-up Period**: Discard first few requests (cold start effects)
4. **Resource Monitoring**: Always enable for production sizing
5. **Multiple Runs**: Execute 3-5 runs and average results
6. **Network Latency**: Run tool on same network as application
7. **Clean State**: Clear caches/restart services between major test runs

### Tips for Accurate Results

- **Consistent Environment**: Same hardware, OS, network conditions
- **Representative Data**: Use production-like documents/videos
- **Realistic Queries**: Base prompts on actual user queries
- **Peak Load Testing**: Test at expected maximum concurrency
- **Sustained Load**: Run for extended periods (5-30 minutes)
- **Bottleneck Identification**: Monitor all system resources during tests

---

## Summary

The Generative AI Hardware Sizing Tool provides a complete solution for:

✅ **Performance Benchmarking**: Accurate measurements of GenAI applications  
✅ **Hardware Sizing**: Data-driven infrastructure planning  
✅ **Resource Optimization**: Identify bottlenecks and optimize deployments  
✅ **Comparative Analysis**: Evaluate different configurations and models  
✅ **Production Readiness**: Validate applications meet SLA requirements  

With support for chat, document, and video AI workloads, comprehensive metrics collection, and automated resource monitoring, this tool enables informed decisions about hardware requirements and application optimization for Intel platforms.

For questions or contributions, refer to the repository's issue tracker or documentation.
